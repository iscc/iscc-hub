"""
ISCC Hub Sequencer - Portable, database-agnostic atomic sequencing.

Provides single-writer sequencing of ISCC declarations and deletions that
preserves every architecture invariant on both SQLite and PostgreSQL:

- Gapless 0-based leaf indices (the LogRecord sequence has no holes).
- Strictly monotonic microsecond timestamps (the ISCC-ID clock never repeats).
- One atomic transaction per append (record + materialized view written together).
- One writer per Hub (a row lock on the singleton LogState row serializes writers;
  on SQLite the IMMEDIATE transaction mode provides the same serialization).

The locked primitive ``append_record`` reads the explicit counter and clock from
``LogState``, assigns the next index, ratchets the timestamp, (optionally) mints
the ISCC-ID, commits the canonical log-entry envelope to ``LogRecord``, and
updates the ``IsccDeclaration`` view. During the transition to the tlog-tiles log
it also dual-writes the legacy ``Event`` row consumed by the checkpoint subsystem.
"""

import time
from datetime import UTC, datetime

import blake3
import jcs
from django.conf import settings
from django.db import transaction

from iscc_hub.exceptions import NonceError, SequencerError
from iscc_hub.iscc_id import IsccID
from iscc_hub.models import Event, IsccDeclaration, LogRecord, LogState

# Reject a backward wall-clock jump larger than this (microseconds) instead of
# silently ratcheting through it and burning the 52-bit ISCC-ID timestamp budget.
TIMETRAVEL_BOUND_US = 100_000

# Published schema URI carried in the log-entry envelope (the Merkle-tree leaf).
LOG_ENTRY_SCHEMA = "http://purl.org/iscc/schema/iscc-log-entry-0.8.0.json"


def _jcs(obj):
    # type: (dict) -> bytes
    """JCS-canonicalize an object to UTF-8 bytes (no surrounding whitespace)."""
    canonical = jcs.canonicalize(obj)
    assert isinstance(canonical, bytes)  # jcs.canonicalize always returns bytes
    return canonical


def append_record(note, record_type, iscc_id_bytes=None, datahash_bytes=None):
    # type: (dict, str, bytes|None, bytes|str|None) -> tuple[int, bytes]
    """
    Atomically append one record to the log under the single-writer lock.

    :param note: The verbatim signed note (IsccNote or IsccNoteDelete).
    :param record_type: LogRecord.RecordType value (declaration|deletion).
    :param iscc_id_bytes: 8-byte ISCC-ID to reuse (deletions); None mints a new one.
    :param datahash_bytes: Original datahash to record for deletions, as bytes or a hex
        string (HexField accepts both); None falls back to ``note["datahash"]``.
    :return: Tuple of (0-based leaf index, 8-byte ISCC-ID).
    :raises NonceError: If the nonce was already used.
    :raises SequencerError: On a disallowed backward wall-clock jump.
    """
    hub_id = int(settings.ISCC_HUB_ID)
    nonce_hex = note["nonce"]
    pubkey_mb = note["signature"]["pubkey"]

    # durable=True asserts this is the OUTERMOST transaction. On SQLite that is what makes
    # atomic() emit BEGIN IMMEDIATE — the write lock that serializes writers; nesting it would
    # skip that lock, so Django raises RuntimeError loudly rather than silently breaking the
    # gapless index / monotonic clock. (ATOMIC_REQUESTS must stay False for this to hold.)
    with transaction.atomic(durable=True):
        # The singleton LogState row is created lazily here rather than seeded in a migration,
        # because the test suite disables migrations (django_db_use_migrations=False). This is an
        # idempotent indexed-PK lookup and is race-safe under the write lock taken on the next line.
        LogState.objects.get_or_create(pk=hub_id)
        state = LogState.objects.select_for_update().get(pk=hub_id)

        # `index` is the 0-based leaf index (== seq) and the public return value.
        # `event_seq` is its 1-based form, used only for the transitional legacy
        # Event.seq / IsccDeclaration.event_seq dual-write removed in Change B.
        index = state.tree_size
        event_seq = index + 1

        now_us = time.time_ns() // 1000
        if now_us <= state.last_timestamp_us and (state.last_timestamp_us - now_us) > TIMETRAVEL_BOUND_US:
            raise SequencerError("Timetravel not allowed :)")
        ts = max(now_us, state.last_timestamp_us + 1)

        # Mint a fresh ISCC-ID for declarations via the canonical constructor (which
        # enforces the 52-bit timestamp / 12-bit hub-id ranges); reuse the provided one
        # for deletions.
        iscc_id_obj = IsccID.from_timestamp(ts, hub_id) if iscc_id_bytes is None else IsccID(iscc_id_bytes)
        id_bytes = bytes(iscc_id_obj)
        iscc_id_str = str(iscc_id_obj)

        # Nonce uniqueness is race-free here because this writer holds the lock.
        if LogRecord.objects.filter(nonce=nonce_hex).exists():
            raise NonceError("Nonce already used", is_reuse=True)

        event_dt = datetime.fromtimestamp(ts // 1_000_000, tz=UTC).replace(microsecond=ts % 1_000_000)
        datahash_value = datahash_bytes if datahash_bytes is not None else note["datahash"]

        # Canonical log-entry envelope: the immutable Merkle-tree leaf preimage.
        entry = {"$schema": LOG_ENTRY_SCHEMA, "iscc_id": iscc_id_str, "note": note}

        LogRecord.objects.create(
            index=index,
            record=_jcs(entry),
            iscc_id=id_bytes,
            type=record_type,
            nonce=nonce_hex,
            datahash=datahash_value,
            pubkey=pubkey_mb,
            event_time=event_dt,
        )

        # Transitional dual-write of the legacy Event consumed by the checkpoint
        # subsystem until Change B replaces it; preserves the BLAKE3 prev-chain.
        last_event = Event.objects.order_by("-seq").first()
        prev_hex = last_event.event_hash if last_event else blake3.blake3(b"").hexdigest()
        legacy_bytes = _jcs({"seq": event_seq, "iscc_id": iscc_id_str, "prev": prev_hex, "note": note})
        is_deletion = record_type == LogRecord.RecordType.DELETION
        Event.objects.create(
            seq=event_seq,
            event_type=Event.EventType.DELETED if is_deletion else Event.EventType.CREATED,
            iscc_id=id_bytes,
            nonce=nonce_hex,
            datahash=datahash_value,
            pubkey=pubkey_mb,
            event_data=legacy_bytes,
            event_hash=blake3.blake3(legacy_bytes).digest(),
        )

        # Maintain the materialized current-state view.
        if is_deletion:
            IsccDeclaration.objects.filter(iscc_id=id_bytes).delete()
        else:
            IsccDeclaration.objects.create(
                iscc_id=id_bytes,
                event_seq=event_seq,
                iscc_code=note["iscc_code"],
                datahash=note["datahash"],
                nonce=nonce_hex,
                pubkey=pubkey_mb,
                controller=note.get("signature", {}).get("controller", ""),
                gateway=note.get("gateway", ""),
                metahash=note.get("metahash"),
                redacted=False,
            )

        state.tree_size = index + 1
        state.last_timestamp_us = ts
        state.save(update_fields=["tree_size", "last_timestamp_us"])

    return index, id_bytes


def sequence_iscc_note(iscc_note):
    # type: (dict) -> tuple[int, bytes]
    """
    Atomically sequence a declaration, minting a new monotonic ISCC-ID.

    :param iscc_note: Pre-validated IsccNote dictionary.
    :return: Tuple of (0-based leaf index, iscc_id_bytes).
    :raises NonceError: If the nonce was already used.
    :raises SequencerError: On a disallowed backward wall-clock jump.
    """
    return append_record(iscc_note, LogRecord.RecordType.DECLARATION)


def sequence_iscc_delete(iscc_note_delete, original_datahash):
    # type: (dict, bytes|str) -> tuple[int, bytes]
    """
    Atomically sequence a deletion, reusing the original declaration's ISCC-ID.

    :param iscc_note_delete: Pre-validated IsccNoteDelete dictionary.
    :param original_datahash: Datahash from the original declaration, as bytes or a hex
        string (the API passes ``LogRecord.datahash``, which reads back as a hex string).
    :return: Tuple of (0-based leaf index, iscc_id_bytes).
    :raises NonceError: If the nonce was already used.
    :raises SequencerError: On a disallowed backward wall-clock jump.
    """
    iscc_id_bytes = bytes(IsccID(iscc_note_delete["iscc_id"]))
    return append_record(
        iscc_note_delete,
        LogRecord.RecordType.DELETION,
        iscc_id_bytes=iscc_id_bytes,
        datahash_bytes=original_datahash,
    )
