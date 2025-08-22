"""
Comprehensive tests for the ISCC Hub sequencer.

Tests atomic sequencing, nonce uniqueness, timestamp monotonicity, and concurrent access.

IMPORTANT: pytest-django Transaction Behavior
==============================================
These tests use @pytest.mark.django_db(transaction=True) which is COUNTERINTUITIVE:

- transaction=True does NOT mean "wrap test in transaction"
- transaction=True means "use TransactionTestCase behavior" which:
  - Flushes the database between tests (slower but cleaner)
  - Does NOT wrap tests in transactions
  - Ensures autocommit=True and in_atomic_block=False

- transaction=False (the default) actually DOES wrap tests in transactions:
  - Uses TestCase behavior with transaction rollback
  - Results in in_atomic_block=True even though it says "False"
  - Will break sequencer tests because BEGIN IMMEDIATE needs clean state

The sequencer REQUIRES direct control over SQLite transactions via BEGIN IMMEDIATE,
so we MUST use transaction=True to avoid pytest-django's transaction wrapping.
"""

import os
import time
from binascii import unhexlify

import base58
import iscc_crypto as icr
import pytest
from django.conf import settings
from django.db import connection

from iscc_hub.exceptions import NonceError, SequencerError
from iscc_hub.iscc_id import IsccID
from iscc_hub.sequencer import sequence_iscc_delete, sequence_iscc_note
from tests.conftest import create_iscc_from_text

# Note: No clear_database fixture needed!
# With transaction=True, pytest-django uses TransactionTestCase behavior which
# flushes the database between tests automatically. This gives us:
# - Clean database state for each test
# - No transaction wrapping (autocommit=True, in_atomic_block=False)
# - Direct control over SQLite's BEGIN IMMEDIATE transactions


@pytest.mark.django_db(transaction=True)
def test_transaction_atomicity(full_iscc_note):
    """Test that transactions are atomic - all or nothing."""
    # Use the fixture note
    note = full_iscc_note

    # Temporarily break the note to cause a failure
    original_execute = connection.cursor().__class__.execute
    call_count = [0]

    def failing_execute(self, sql, params=None):
        call_count[0] += 1
        # Fail on the event insert
        if "INSERT INTO iscc_event" in sql:
            raise Exception("Simulated failure")
        return original_execute(self, sql, params)

    # Monkey-patch execute method
    connection.cursor().__class__.execute = failing_execute

    try:
        with pytest.raises(SequencerError):
            sequence_iscc_note(note)
    finally:
        # Restore original method
        connection.cursor().__class__.execute = original_execute

    # Verify nothing was committed
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM iscc_event")
        assert cursor.fetchone()[0] == 0


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)
def test_performance_benchmark():
    """Performance benchmark for sequencing operations."""
    num_operations = 100
    start_time = time.perf_counter()

    for i in range(num_operations):
        # Create unique note for each iteration
        text = f"Test content {i}"
        iscc_data = create_iscc_from_text(text)

        # Generate unique nonce for each note
        nonce_bytes = os.urandom(16)
        # Set first 12 bits to 001 (hub_id 1)
        nonce_bytes = bytes([0x00, 0x10]) + nonce_bytes[2:]
        nonce = nonce_bytes.hex()

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce,
            "timestamp": f"2025-01-15T12:00:{i % 60:02d}.000Z",
            "gateway": f"https://example.com/item{i}",
            "metahash": iscc_data["metahash"],
        }

        # Sign the note
        controller = f"did:web:example{i}.com"
        keypair = icr.key_generate(controller=controller)
        signed_note = icr.sign_json(note, keypair)

        sequence_iscc_note(signed_note)

    elapsed = time.perf_counter() - start_time
    throughput = num_operations / elapsed

    print(f"\nPerformance: {throughput:.1f} operations/sec")
    print(f"Average latency: {elapsed / num_operations * 1000:.2f} ms")

    # Basic performance assertion (adjust based on hardware)
    assert throughput > 50  # At least 50 ops/sec


@pytest.mark.django_db(transaction=True)
def test_hub_id_encoding(full_iscc_note):
    """Test that hub_id is correctly encoded in ISCC-ID."""
    _, iscc_id_bytes = sequence_iscc_note(full_iscc_note)

    # Decode the ISCC-ID
    iscc_id = IsccID(iscc_id_bytes)

    # Check hub_id matches settings
    assert iscc_id.hub_id == settings.ISCC_HUB_ID


@pytest.mark.django_db(transaction=True)
def test_timestamp_precision():
    """Test that timestamps have microsecond precision."""
    notes = []
    for i in range(5):
        # Create unique note for each iteration
        text = f"Test content {i}"
        iscc_data = create_iscc_from_text(text)

        # Generate unique nonce
        nonce_bytes = os.urandom(16)
        nonce_bytes = bytes([0x00, 0x10]) + nonce_bytes[2:]

        note = {
            "iscc_code": iscc_data["iscc"],
            "datahash": iscc_data["datahash"],
            "nonce": nonce_bytes.hex(),
            "timestamp": f"2025-01-15T12:00:{i:02d}.000Z",
        }

        # Sign the note
        keypair = icr.key_generate(controller=f"did:web:example{i}.com")
        signed_note = icr.sign_json(note, keypair)

        _, iscc_id = sequence_iscc_note(signed_note)
        notes.append(iscc_id)
        # Small delay to ensure different timestamps
        time.sleep(0.001)  # 1ms

    # Check that timestamps are different and have microsecond precision
    timestamps = [IsccID(iid).timestamp_micros for iid in notes]

    # All timestamps should be unique
    assert len(set(timestamps)) == len(timestamps)

    # Timestamps should have microsecond precision (not just millisecond)
    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i - 1]
        # Should be able to distinguish events less than 1ms apart
        assert diff > 0


def test_sequencer_error_inheritance():
    """Test that SequencerError inherits from Exception."""
    error = SequencerError("Test error")
    assert isinstance(error, Exception)
    assert str(error) == "Test error"


def test_nonce_error_inheritance():
    """Test that NonceError is properly structured for API responses."""
    error = NonceError("Test nonce conflict", is_reuse=True)
    assert isinstance(error, Exception)
    assert str(error) == "Test nonce conflict"
    assert error.code == "nonce_reuse"
    assert error.field == "nonce"


@pytest.mark.django_db(transaction=True)
def test_nonce_conflict_detection():
    """Test that duplicate nonces are rejected."""
    # Create and sequence first note with specific nonce
    nonce = "00100123456789abcdef0123456789ab"
    iscc_data1 = create_iscc_from_text("Test content 1")
    note1 = {
        "iscc_code": iscc_data1["iscc"],
        "datahash": iscc_data1["datahash"],
        "nonce": nonce,
        "timestamp": "2025-01-15T12:00:01.000Z",
    }
    keypair1 = icr.key_generate(controller="did:web:example1.com")
    signed_note1 = icr.sign_json(note1, keypair1)
    seq1, iscc_id1 = sequence_iscc_note(signed_note1)

    # Try to sequence another note with the same nonce
    iscc_data2 = create_iscc_from_text("Test content 2")
    note2 = {
        "iscc_code": iscc_data2["iscc"],
        "datahash": iscc_data2["datahash"],
        "nonce": nonce,  # Same nonce
        "timestamp": "2025-01-15T12:00:02.000Z",
    }
    keypair2 = icr.key_generate(controller="did:web:example2.com")
    signed_note2 = icr.sign_json(note2, keypair2)

    with pytest.raises(NonceError) as exc_info:
        sequence_iscc_note(signed_note2)

    assert "Nonce already used" in str(exc_info.value)

    # Verify only the first note was stored
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM iscc_event")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT COUNT(*) FROM iscc_event WHERE nonce = %s", (unhexlify("00100123456789abcdef0123456789ab"),)
        )
        assert cursor.fetchone()[0] == 1


@pytest.mark.django_db(transaction=True)
def test_rollback_on_generic_exception(monkeypatch, full_iscc_note):
    """Test that generic exceptions cause rollback and are wrapped."""
    note = full_iscc_note

    # Mock cursor.execute to raise a generic exception during INSERT
    original_execute = connection.cursor().__class__.execute

    def mock_execute(self, sql, params=None):
        if "INSERT INTO iscc_event" in sql:
            raise RuntimeError("Database connection lost")
        return original_execute(self, sql, params)

    monkeypatch.setattr(connection.cursor().__class__, "execute", mock_execute)

    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(note)

    assert "Sequencing failed: Database connection lost" in str(exc_info.value)

    # Verify the transaction was rolled back (no data inserted)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM iscc_event")
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db  # Use default behavior to test atomic block detection
def test_atomic_block_detection(full_iscc_note):
    """Test that sequencer detects and rejects calls within atomic blocks."""
    # When using default django_db (without transaction=True),
    # Django wraps the test in a transaction
    with pytest.raises(SequencerError):
        sequence_iscc_note(full_iscc_note)


@pytest.mark.django_db(transaction=True)
def test_begin_immediate_other_error(full_iscc_note, monkeypatch):
    """Test that non-transaction errors in BEGIN IMMEDIATE are re-raised."""
    original_execute = connection.cursor().__class__.execute

    def mock_execute(self, sql, params=None):
        if "BEGIN IMMEDIATE" in sql:
            raise Exception("Some other database error")
        return original_execute(self, sql, params)

    monkeypatch.setattr(connection.cursor().__class__, "execute", mock_execute)

    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(full_iscc_note)

    assert "Sequencing failed: Some other database error" in str(exc_info.value)


@pytest.mark.django_db(transaction=True)
def test_timetravel_prevention(full_iscc_note, monkeypatch):
    """Test that sequencer prevents time travel (line 71 coverage)."""
    # First, sequence a note to establish a timestamp
    seq1, iscc_id1 = sequence_iscc_note(full_iscc_note)

    # Create another note with different nonce
    import os

    nonce_bytes = os.urandom(16)
    nonce_bytes = bytes([0x00, 0x10]) + nonce_bytes[2:]

    note2 = full_iscc_note.copy()
    note2["nonce"] = nonce_bytes.hex()

    # Mock time.time_ns to return a value in the past
    def mock_time_ns():
        return 1000000000  # 1 second in nanoseconds (very far in the past)

    monkeypatch.setattr("iscc_hub.sequencer.time.time_ns", mock_time_ns)

    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(note2)

    assert "Timetravel not allowed" in str(exc_info.value)


@pytest.mark.django_db(transaction=True)
def test_microsecond_collision_handling(full_iscc_note, monkeypatch):
    """Test handling of same microsecond timestamp (line 73 coverage)."""
    # Sequence first note
    seq1, iscc_id1 = sequence_iscc_note(full_iscc_note)

    # Get the timestamp from the first ISCC-ID
    iscc_id_obj = IsccID(iscc_id1)
    first_timestamp_us = iscc_id_obj.timestamp_micros

    # Create another note with different nonce
    import os

    nonce_bytes = os.urandom(16)
    nonce_bytes = bytes([0x00, 0x10]) + nonce_bytes[2:]

    note2 = full_iscc_note.copy()
    note2["nonce"] = nonce_bytes.hex()

    # Mock time.time_ns to return exactly the same microsecond value
    def mock_time_ns():
        return first_timestamp_us * 1000  # Convert microseconds to nanoseconds

    monkeypatch.setattr("iscc_hub.sequencer.time.time_ns", mock_time_ns)

    # Sequence second note - should increment timestamp by 1 microsecond
    seq2, iscc_id2 = sequence_iscc_note(note2)

    # Verify timestamp was incremented by exactly 1 microsecond
    iscc_id_obj2 = IsccID(iscc_id2)
    assert iscc_id_obj2.timestamp_micros == first_timestamp_us + 1
    assert seq2 == seq1 + 1


# Tests for sequence_iscc_delete


@pytest.mark.django_db(transaction=True)
def test_sequence_iscc_delete_basic(full_iscc_note):
    """Test basic delete sequencing functionality."""
    # First create a declaration
    seq1, iscc_id1 = sequence_iscc_note(full_iscc_note)

    # Extract datahash from the note
    datahash_bytes = unhexlify(full_iscc_note["datahash"])

    # Create a delete note - use proper ISCC-ID string format
    delete_note = {
        "iscc_id": str(IsccID(iscc_id1)),
        "timestamp": "2025-01-15T12:00:01.000Z",
        "nonce": "00100123456789abcdef0123456789ff",  # Different nonce
    }

    # Sign the delete note with same keypair (for testing)
    keypair = icr.key_generate(controller="did:web:example.com")
    signed_delete = icr.sign_json(delete_note, keypair)

    # Sequence the delete
    seq2, iscc_id_returned = sequence_iscc_delete(signed_delete, datahash_bytes)

    # Verify sequence number incremented
    assert seq2 == seq1 + 1

    # Verify same ISCC-ID is used
    assert iscc_id_returned == iscc_id1

    # Verify event was created with DELETE type
    with connection.cursor() as cursor:
        cursor.execute("SELECT event_type, datahash FROM iscc_event WHERE seq = %s", (seq2,))
        row = cursor.fetchone()
        assert row[0] == 3  # EventType.DELETED
        assert row[1] == datahash_bytes


@pytest.mark.django_db(transaction=True)
def test_sequence_iscc_delete_nonce_uniqueness():
    """Test that delete events enforce nonce uniqueness."""
    # Create initial declaration
    iscc_data = create_iscc_from_text("Test content")
    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": "00100123456789abcdef0123456789ab",
        "timestamp": "2025-01-15T12:00:00.000Z",
    }
    keypair = icr.key_generate(controller="did:web:example.com")
    signed_note = icr.sign_json(note, keypair)
    seq1, iscc_id1 = sequence_iscc_note(signed_note)

    datahash_bytes = unhexlify(iscc_data["datahash"])

    # Create delete note with specific nonce
    delete_note = {
        "iscc_id": str(IsccID(iscc_id1)),
        "timestamp": "2025-01-15T12:00:01.000Z",
        "nonce": "00100123456789abcdef0123456789ff",
    }
    signed_delete1 = icr.sign_json(delete_note, keypair)

    # First delete should succeed
    seq2, _ = sequence_iscc_delete(signed_delete1, datahash_bytes)
    assert seq2 == 2

    # Try to use the same nonce again (different delete request)
    delete_note2 = {
        "iscc_id": str(IsccID(iscc_id1)),
        "timestamp": "2025-01-15T12:00:02.000Z",
        "nonce": "00100123456789abcdef0123456789ff",  # Same nonce
    }
    signed_delete2 = icr.sign_json(delete_note2, keypair)

    # Should fail with nonce error
    with pytest.raises(NonceError) as exc_info:
        sequence_iscc_delete(signed_delete2, datahash_bytes)

    assert "Nonce already used" in str(exc_info.value)


@pytest.mark.django_db(transaction=True)
def test_sequence_iscc_delete_atomicity(full_iscc_note):
    """Test that delete sequencing is atomic."""
    # Create initial declaration
    seq1, iscc_id1 = sequence_iscc_note(full_iscc_note)
    datahash_bytes = unhexlify(full_iscc_note["datahash"])

    # Create delete note
    delete_note = {
        "iscc_id": str(IsccID(iscc_id1)),
        "timestamp": "2025-01-15T12:00:01.000Z",
        "nonce": "00100123456789abcdef0123456789ee",
    }
    keypair = icr.key_generate(controller="did:web:example.com")
    signed_delete = icr.sign_json(delete_note, keypair)

    # Mock failure during INSERT
    original_execute = connection.cursor().__class__.execute

    def failing_execute(self, sql, params=None):
        if "INSERT INTO iscc_event" in sql and params and params[1] == 3:  # DELETE event type
            raise Exception("Simulated failure during delete")
        return original_execute(self, sql, params)

    connection.cursor().__class__.execute = failing_execute

    try:
        with pytest.raises(SequencerError) as exc_info:
            sequence_iscc_delete(signed_delete, datahash_bytes)

        assert "Sequencing failed: Simulated failure during delete" in str(exc_info.value)
    finally:
        connection.cursor().__class__.execute = original_execute

    # Verify no DELETE event was created
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM iscc_event WHERE event_type = 3")
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db(transaction=True)
def test_sequence_iscc_delete_with_empty_database():
    """Test delete sequencing fails with empty database."""
    # Create a delete note (edge case - no previous events)
    iscc_id_bytes = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    delete_note = {
        "iscc_id": str(IsccID(iscc_id_bytes)),
        "timestamp": "2025-01-15T12:00:00.000Z",
        "nonce": "00100123456789abcdef0123456789bb",
    }
    keypair = icr.key_generate(controller="did:web:example.com")
    signed_delete = icr.sign_json(delete_note, keypair)

    datahash_bytes = b"test_datahash_bytes"

    # Should fail with empty database
    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_delete(signed_delete, datahash_bytes)

    assert "No previous event found" in str(exc_info.value)

    # Verify no event was created
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM iscc_event")
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db(transaction=True)
def test_sequence_iscc_delete_rollback_exception(full_iscc_note):
    """Test that rollback exceptions are handled gracefully in delete."""
    # Create initial declaration
    seq1, iscc_id1 = sequence_iscc_note(full_iscc_note)
    datahash_bytes = unhexlify(full_iscc_note["datahash"])

    # Create delete note
    delete_note = {
        "iscc_id": str(IsccID(iscc_id1)),
        "timestamp": "2025-01-15T12:00:01.000Z",
        "nonce": "00100123456789abcdef0123456789aa",
    }
    keypair = icr.key_generate(controller="did:web:example.com")
    signed_delete = icr.sign_json(delete_note, keypair)

    # Mock both INSERT failure and ROLLBACK failure
    original_execute = connection.cursor().__class__.execute
    rollback_called = [False]

    def failing_execute(self, sql, params=None):
        if "INSERT INTO iscc_event" in sql and params and params[1] == 3:
            raise Exception("Insert failed")
        if "ROLLBACK" in sql:
            rollback_called[0] = True
            raise Exception("Rollback also failed")
        return original_execute(self, sql, params)

    connection.cursor().__class__.execute = failing_execute

    try:
        # Should still raise the original error even if rollback fails
        with pytest.raises(SequencerError) as exc_info:
            sequence_iscc_delete(signed_delete, datahash_bytes)

        assert "Sequencing failed: Insert failed" in str(exc_info.value)
        assert rollback_called[0]  # Verify rollback was attempted
    finally:
        # Always restore original execute method
        connection.cursor().__class__.execute = original_execute
        # Clean up any hanging transaction
        try:
            with connection.cursor() as cursor:
                cursor.execute("ROLLBACK")
        except Exception:
            pass
