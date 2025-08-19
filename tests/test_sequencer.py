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

import iscc_crypto as icr
import pytest
from django.conf import settings
from django.db import connection

from iscc_hub.iscc_id import IsccID
from iscc_hub.sequencer import (
    NonceConflictError,
    SequencerError,
    sequence_iscc_note,
)
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
        # Fail on the declaration insert (second insert)
        if "INSERT INTO iscc_declaration" in sql:
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

        cursor.execute("SELECT COUNT(*) FROM iscc_declaration")
        assert cursor.fetchone()[0] == 0


@pytest.mark.django_db(transaction=True)
def test_missing_required_fields():
    """Test that missing required fields raise appropriate errors."""
    # Note without nonce
    note = {
        "iscc_code": "ISCC:MEAJU7P6XBJ5SCNY",
        "datahash": "1e20b1234567890123456789012345678901234567890123456789012345678901",
        "timestamp": "2025-01-15T12:00:00.000Z",
        "signature": {
            "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
        },
    }

    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(note)

    assert "Missing required fields" in str(exc_info.value)


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


def test_nonce_conflict_error_inheritance():
    """Test that NonceConflictError inherits from SequencerError."""
    error = NonceConflictError("Test nonce conflict")
    assert isinstance(error, SequencerError)
    assert isinstance(error, Exception)
    assert str(error) == "Test nonce conflict"


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

    with pytest.raises(NonceConflictError) as exc_info:
        sequence_iscc_note(signed_note2)

    assert "Nonce already exists: 00100123456789abcdef0123456789ab" in str(exc_info.value)

    # Verify only the first note was stored
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM iscc_event")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT COUNT(*) FROM iscc_declaration WHERE nonce = %s", ("00100123456789abcdef0123456789ab",)
        )
        assert cursor.fetchone()[0] == 1


@pytest.mark.django_db(transaction=True)
def test_invalid_hub_id(monkeypatch, full_iscc_note):
    """Test that invalid hub_id raises SequencerError."""
    # Save original value
    original_hub_id = settings.ISCC_HUB_ID

    # Test hub_id > 4095
    monkeypatch.setattr(settings, "ISCC_HUB_ID", 4096)
    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(full_iscc_note)
    assert "Invalid hub_id: 4096" in str(exc_info.value)

    # Test negative hub_id
    monkeypatch.setattr(settings, "ISCC_HUB_ID", -1)
    # Need a fresh note with different nonce to avoid conflict
    iscc_data = create_iscc_from_text("Different content")
    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": "00100000000000000000000000000002",
        "timestamp": "2025-01-15T12:00:00.000Z",
    }
    keypair = icr.key_generate(controller="did:web:example.com")
    signed_note = icr.sign_json(note, keypair)

    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(signed_note)
    assert "Invalid hub_id: -1" in str(exc_info.value)

    # Restore original value
    monkeypatch.setattr(settings, "ISCC_HUB_ID", original_hub_id)


@pytest.mark.django_db(transaction=True)
def test_monotonic_timestamp_edge_case(monkeypatch, full_iscc_note):
    """Test timestamp monotonicity when system clock goes backward."""
    # First, insert a normal note
    seq1, iscc_id1 = sequence_iscc_note(full_iscc_note)

    # Parse the timestamp from the first ISCC-ID
    iscc_obj1 = IsccID(iscc_id1)
    first_timestamp_us = iscc_obj1.timestamp_micros

    # Mock time.time_ns to return an earlier time
    def mock_time_ns():
        # Return a time that's 1 second before the first timestamp
        return (first_timestamp_us - 1_000_000) * 1000  # microseconds to nanoseconds

    monkeypatch.setattr(time, "time_ns", mock_time_ns)

    # Create second note with different nonce - should still get monotonic timestamp
    iscc_data = create_iscc_from_text("Different content")
    note2 = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": "00100000000000000000000000000002",
        "timestamp": "2025-01-15T12:00:00.000Z",
    }
    keypair = icr.key_generate(controller="did:web:example2.com")
    signed_note2 = icr.sign_json(note2, keypair)
    seq2, iscc_id2 = sequence_iscc_note(signed_note2)

    # Parse the second timestamp
    iscc_obj2 = IsccID(iscc_id2)
    second_timestamp_us = iscc_obj2.timestamp_micros

    # Verify monotonic increase (should be first + 1)
    assert second_timestamp_us == first_timestamp_us + 1
    assert seq2 == seq1 + 1


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
    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(full_iscc_note)

    assert "cannot be called within an atomic block" in str(exc_info.value)


@pytest.mark.django_db(transaction=True)
def test_autocommit_check(full_iscc_note):
    """Test that sequencer checks for autocommit mode."""
    # Temporarily disable autocommit
    original_autocommit = connection.get_autocommit()
    try:
        connection.set_autocommit(False)

        with pytest.raises(SequencerError) as exc_info:
            sequence_iscc_note(full_iscc_note)

        assert "requires autocommit mode to be enabled" in str(exc_info.value)
    finally:
        # Restore autocommit
        connection.set_autocommit(original_autocommit)


@pytest.mark.django_db(transaction=True)
def test_transaction_within_transaction_error(full_iscc_note):
    """Test error handling when BEGIN IMMEDIATE fails due to existing transaction."""
    # Start a transaction manually
    with connection.cursor() as cursor:
        cursor.execute("BEGIN")

        try:
            with pytest.raises(SequencerError) as exc_info:
                sequence_iscc_note(full_iscc_note)

            assert "Cannot start transaction - already in a transaction" in str(exc_info.value)
        finally:
            # Clean up - rollback if transaction is still active
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass  # Transaction might already be rolled back


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
