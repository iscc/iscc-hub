"""
Tests for the portable, database-agnostic ISCC Hub sequencer.

Covers gapless indices, monotonic ISCC-ID timestamps, the timetravel guard,
nonce uniqueness, deletion handling, the canonical log-entry envelope, the
outermost-transaction guard, and real-thread concurrency.

IMPORTANT: pytest-django transaction behavior
==============================================
These tests use ``@pytest.mark.django_db(transaction=True)`` which is
counterintuitive but required:

- ``transaction=True`` does NOT wrap the test in a transaction. It uses
  TransactionTestCase behavior (flush between tests, ``autocommit=True``,
  ``in_atomic_block=False``).
- The sequencer's ``transaction.atomic(durable=True)`` must run as the
  outermost atomic block for the write lock (SQLite BEGIN IMMEDIATE /
  PostgreSQL FOR UPDATE) to serialize writers. The default
  ``@pytest.mark.django_db`` wraps the test in a testcase transaction, which
  the ``durable`` check is exempt from, so it would silently skip the lock.
"""

import threading
import time

import iscc_crypto as icr
import jcs
import pytest
from django.conf import settings
from django.db import IntegrityError, connection, transaction

from iscc_hub.exceptions import NonceError, SequencerError
from iscc_hub.iscc_id import IsccID
from iscc_hub.models import Event, IsccDeclaration, LogRecord, LogState
from iscc_hub.sequencer import LOG_ENTRY_SCHEMA, sequence_iscc_delete, sequence_iscc_note
from tests.conftest import create_iscc_from_text


def make_signed_note(text="Hello World!", nonce=None, timestamp="2025-01-15T12:00:00.000Z", keypair=None):
    # type: (str, str|None, str, icr.KeyPair|None) -> dict
    """Build and sign a minimal IsccNote with unique content for sequencing tests."""
    iscc_data = create_iscc_from_text(text)
    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": nonce or icr.create_nonce(settings.ISCC_HUB_ID),
        "timestamp": timestamp,
    }
    keypair = keypair or icr.key_generate(controller="did:web:example.com")
    return icr.sign_json(note, keypair)


def make_signed_delete(iscc_id_str, nonce=None, keypair=None):
    # type: (str, str|None, icr.KeyPair|None) -> dict
    """Build and sign a minimal IsccNoteDelete for the given ISCC-ID."""
    note = {"iscc_id": iscc_id_str, "nonce": nonce or icr.create_nonce(settings.ISCC_HUB_ID)}
    keypair = keypair or icr.key_generate(controller="did:web:example.com")
    return icr.sign_json(note, keypair)


# --- Gaplessness, indices, and the returned sequence number ---------------------------------------


@pytest.mark.django_db(transaction=True)
def test_gapless_zero_based_indices():
    """N sequential appends yield LogRecord indices 0..N-1 with no gaps."""
    n = 5
    seqs = []
    for i in range(n):
        seq, _ = sequence_iscc_note(make_signed_note(f"content {i}"))
        seqs.append(seq)

    indices = sorted(LogRecord.objects.values_list("index", flat=True))
    assert indices == list(range(n))
    # The returned sequence number is the 0-based leaf index itself.
    assert seqs == list(range(n))
    assert LogState.objects.get(pk=settings.ISCC_HUB_ID).tree_size == n


@pytest.mark.django_db(transaction=True)
def test_hub_id_encoding():
    """The minted ISCC-ID encodes the configured Hub-ID."""
    _, iscc_id_bytes = sequence_iscc_note(make_signed_note())
    assert IsccID(iscc_id_bytes).hub_id == settings.ISCC_HUB_ID


# --- Monotonic timestamps ----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_monotonic_timestamps():
    """Successive declarations have strictly increasing microsecond timestamps."""
    timestamps = []
    for i in range(5):
        _, iscc_id_bytes = sequence_iscc_note(make_signed_note(f"mono {i}"))
        timestamps.append(IsccID(iscc_id_bytes).timestamp_micros)
        time.sleep(0.001)

    for prev, nxt in zip(timestamps, timestamps[1:], strict=False):
        assert nxt > prev


@pytest.mark.django_db(transaction=True)
def test_microsecond_collision_advances_by_one(monkeypatch):
    """When the wall clock is stalled, the timestamp advances by exactly one microsecond."""
    seq1, iscc_id1 = sequence_iscc_note(make_signed_note("first"))
    first_us = IsccID(iscc_id1).timestamp_micros

    # Freeze the clock at the first record's microsecond.
    monkeypatch.setattr("iscc_hub.sequencer.time.time_ns", lambda: first_us * 1000)

    seq2, iscc_id2 = sequence_iscc_note(make_signed_note("second"))
    assert IsccID(iscc_id2).timestamp_micros == first_us + 1
    assert seq2 == seq1 + 1


@pytest.mark.django_db(transaction=True)
def test_timetravel_prevention(monkeypatch):
    """A large backward wall-clock jump is rejected rather than ratcheted through."""
    sequence_iscc_note(make_signed_note("establish clock"))

    # Pretend the clock jumped to 1 second past the epoch (far in the past).
    monkeypatch.setattr("iscc_hub.sequencer.time.time_ns", lambda: 1_000_000_000)

    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(make_signed_note("from the past"))
    assert "Timetravel not allowed" in str(exc_info.value)


@pytest.mark.django_db(transaction=True)
def test_deletion_does_not_break_monotonicity(monkeypatch):
    """A deletion carrying an old ISCC-ID does not lower the mint clock for later declarations."""
    # An old declaration (clock one hour in the past).
    monkeypatch.setattr("iscc_hub.sequencer.time.time_ns", lambda: int((time.time() - 3600) * 1e9))
    _, old_iscc_id = sequence_iscc_note(make_signed_note("old"))
    old_us = IsccID(old_iscc_id).timestamp_micros

    # A recent declaration (real clock).
    monkeypatch.undo()
    _, recent_iscc_id = sequence_iscc_note(make_signed_note("recent"))
    recent_us = IsccID(recent_iscc_id).timestamp_micros
    assert recent_us > old_us

    # Delete the old declaration (reuses the old, lower ISCC-ID).
    _, returned = sequence_iscc_delete(make_signed_delete(str(IsccID(old_iscc_id))), b"\x1e\x20" + b"\x00" * 32)
    assert returned == old_iscc_id

    # A new declaration must still be monotonic relative to the recent one.
    _, new_iscc_id = sequence_iscc_note(make_signed_note("newest"))
    assert IsccID(new_iscc_id).timestamp_micros > recent_us


# --- Nonce uniqueness and rollback safety ------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_nonce_reuse_rejected():
    """A duplicate nonce is rejected with NonceError."""
    nonce = icr.create_nonce(settings.ISCC_HUB_ID)
    sequence_iscc_note(make_signed_note("one", nonce=nonce))

    with pytest.raises(NonceError) as exc_info:
        sequence_iscc_note(make_signed_note("two", nonce=nonce))
    assert "Nonce already used" in str(exc_info.value)
    assert exc_info.value.code == "nonce_reuse"


@pytest.mark.django_db(transaction=True)
def test_failed_append_reuses_index_and_clock():
    """A rejected append leaves tree_size/clock untouched; the next append reuses the index."""
    nonce = icr.create_nonce(settings.ISCC_HUB_ID)
    sequence_iscc_note(make_signed_note("one", nonce=nonce))

    state_before = LogState.objects.get(pk=settings.ISCC_HUB_ID)
    assert state_before.tree_size == 1
    saved_ts = state_before.last_timestamp_us

    # A nonce reuse fails before any write; the counter and clock are unchanged.
    with pytest.raises(NonceError):
        sequence_iscc_note(make_signed_note("dup", nonce=nonce))

    state_after = LogState.objects.get(pk=settings.ISCC_HUB_ID)
    assert state_after.tree_size == 1
    assert state_after.last_timestamp_us == saved_ts
    assert LogRecord.objects.count() == 1

    # The next valid append reuses index 1 (the one the failed attempt would have taken).
    seq, _ = sequence_iscc_note(make_signed_note("two"))
    assert seq == 1
    assert sorted(LogRecord.objects.values_list("index", flat=True)) == [0, 1]


@pytest.mark.django_db(transaction=True)
def test_failed_inner_write_rolls_back_the_whole_append():
    """A failure on a later in-transaction write rolls back LogRecord + Event + the counter.

    Drives a real (mock-free) IntegrityError on the THIRD write of the atomic append
    (IsccDeclaration.create), after LogRecord and the dual-written Event have already been
    inserted in the same transaction, and asserts that none of them — nor the LogState
    counter — survive, and that the index is not burned.
    """
    keypair = icr.key_generate()

    # Pre-seed an IsccDeclaration whose unique event_seq (1) collides with the value the first
    # append assigns (index 0 -> event_seq 1), so IsccDeclaration.create raises mid-transaction.
    IsccDeclaration.objects.create(
        iscc_id=bytes(IsccID.from_timestamp(123, settings.ISCC_HUB_ID)),
        event_seq=1,
        iscc_code="ISCC:KACWN77F73NA44D6EUG3S3QNJIL2BPPQFMW6ZX6CZNOKPAK23S2IJ2I",
        datahash="1e20" + "00" * 32,
        nonce="ff" * 16,
        pubkey=keypair.public_key,
    )

    with pytest.raises(IntegrityError):
        sequence_iscc_note(make_signed_note("atomic"))

    # Nothing from the failed append survives: no log record, no dual-written event, and the
    # lazily-created LogState row rolled back with the rest (the counter never advanced).
    assert LogRecord.objects.count() == 0
    assert Event.objects.count() == 0
    assert not LogState.objects.filter(pk=settings.ISCC_HUB_ID).exists()

    # The index was not burned: after clearing the conflict, the next append reuses index 0.
    IsccDeclaration.objects.all().delete()
    seq, _ = sequence_iscc_note(make_signed_note("atomic retry"))
    assert seq == 0


# --- Outermost-transaction guard ---------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_rejects_nested_atomic_block():
    """Sequencing inside another (non-testcase) atomic block raises (durable guard)."""
    note = make_signed_note("nested")
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            sequence_iscc_note(note)


# --- Deletion semantics ------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_deletion_appends_leaf_and_removes_declaration():
    """A deletion appends a deletion leaf, removes the declaration view row, and mints no ISCC-ID."""
    note = make_signed_note("to delete")
    seq1, iscc_id_bytes = sequence_iscc_note(note)
    iscc_id_str = str(IsccID(iscc_id_bytes))
    assert IsccDeclaration.objects.filter(iscc_id=iscc_id_bytes).exists()

    original_datahash = bytes.fromhex(note["datahash"])
    seq2, returned = sequence_iscc_delete(make_signed_delete(iscc_id_str), original_datahash)

    assert seq2 == seq1 + 1
    assert returned == iscc_id_bytes  # reused, not minted
    # The deletion leaf is present in the append-only log...
    deletion = LogRecord.objects.get(index=1)
    assert deletion.type == LogRecord.RecordType.DELETION
    assert deletion.iscc_id == iscc_id_str
    # ...but the current-state view no longer resolves the ISCC-ID.
    assert not IsccDeclaration.objects.filter(iscc_id=iscc_id_bytes).exists()
    assert LogState.objects.get(pk=settings.ISCC_HUB_ID).tree_size == 2


# --- Canonical log-entry envelope --------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_record_bytes_are_canonical_envelope():
    """LogRecord.record equals JCS({$schema, iscc_id, note}) byte-for-byte."""
    note = make_signed_note("envelope")
    _, iscc_id_bytes = sequence_iscc_note(note)
    record = LogRecord.objects.get(index=0)

    expected = jcs.canonicalize({"$schema": LOG_ENTRY_SCHEMA, "iscc_id": str(IsccID(iscc_id_bytes)), "note": note})
    assert bytes(record.record) == expected
    assert record.type == LogRecord.RecordType.DECLARATION


# --- Concurrency -------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_concurrent_appends_are_gapless_and_monotonic():
    """Concurrent writers produce a contiguous 0..M-1 index range with monotonic timestamps."""
    num = 8
    # Prepare signed notes up front so threads only exercise the sequencer.
    notes = [make_signed_note(f"thread {i}") for i in range(num)]
    barrier = threading.Barrier(num)
    errors = []

    def worker(note):
        # type: (dict) -> None
        try:
            barrier.wait()
            sequence_iscc_note(note)
        except Exception as exc:  # pragma: no cover - only on unexpected failure
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(note,)) for note in notes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    records = list(LogRecord.objects.order_by("index"))
    assert [r.index for r in records] == list(range(num))
    timestamps = [IsccID(bytes(IsccID(r.iscc_id))).timestamp_micros for r in records]
    for prev, nxt in zip(timestamps, timestamps[1:], strict=False):
        assert nxt > prev


# --- Model string representations --------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_logstate_and_logrecord_str():
    """LogState and LogRecord render readable string representations."""
    _, iscc_id_bytes = sequence_iscc_note(make_signed_note("repr"))
    state = LogState.objects.get(pk=settings.ISCC_HUB_ID)
    assert str(state) == f"LogState(hub={settings.ISCC_HUB_ID}, tree_size=1)"

    record = LogRecord.objects.get(index=0)
    assert str(record) == f"LogRecord #0: declaration {IsccID(iscc_id_bytes)}"


# --- Exception structure -----------------------------------------------------------------------


def test_sequencer_error_inheritance():
    """SequencerError is an Exception carrying its message."""
    error = SequencerError("boom")
    assert isinstance(error, Exception)
    assert str(error) == "boom"


def test_nonce_error_structure():
    """NonceError exposes the API error code and field for reuse."""
    error = NonceError("reuse", is_reuse=True)
    assert error.code == "nonce_reuse"
    assert error.field == "nonce"


# --- Performance smoke (slow) ------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_performance_benchmark():
    """Sequencing sustains a basic throughput floor."""
    num_operations = 100
    start = time.perf_counter()
    for i in range(num_operations):
        sequence_iscc_note(make_signed_note(f"perf {i}"))
    elapsed = time.perf_counter() - start
    throughput = num_operations / elapsed
    print(f"\nPerformance: {throughput:.1f} ops/sec ({elapsed / num_operations * 1000:.2f} ms/op)")
    assert throughput > 25
    assert LogRecord.objects.count() == num_operations
