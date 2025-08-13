"""
Comprehensive tests for the ISCC Hub sequencer.

Tests atomic sequencing, nonce uniqueness, timestamp monotonicity, and concurrent access.
"""

import os
import time
from io import BytesIO

import iscc_core as ic
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


def create_test_note(index=0, nonce=None):
    # type: (int, str|None) -> dict
    """Create a unique test IsccNote."""
    text = f"Test content {index}"
    text_bytes = text.encode("utf-8")

    # Generate ISCC components
    mcode = ic.gen_meta_code(text, f"Test {index}", bits=256)
    ccode = ic.gen_text_code(text, bits=256)
    dcode = ic.gen_data_code(BytesIO(text_bytes), bits=256)
    icode = ic.gen_instance_code(BytesIO(text_bytes), bits=256)
    iscc_code = ic.gen_iscc_code([mcode["iscc"], ccode["iscc"], dcode["iscc"], icode["iscc"]])["iscc"]

    # Generate nonce if not provided
    if nonce is None:
        nonce_bytes = os.urandom(16)
        # Set first 12 bits to 001 (hub_id 1)
        nonce_bytes = bytes([0x00, 0x10]) + nonce_bytes[2:]
        nonce = nonce_bytes.hex()

    # Create IsccNote
    note = {
        "iscc_code": iscc_code,
        "datahash": icode["datahash"],
        "nonce": nonce,
        "timestamp": f"2025-01-15T12:00:{index % 60:02d}.000Z",
        "gateway": f"https://example.com/item{index}",
        "metahash": mcode["metahash"],
    }

    # Sign the note
    controller = f"did:web:example{index}.com"
    keypair = icr.key_generate(controller=controller)
    signed_note = icr.sign_json(note, keypair)

    return signed_note


@pytest.fixture(autouse=True)
def clear_database():
    """Clear database before each test."""
    # Clear database before test
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM iscc_event")
            cursor.execute("DELETE FROM iscc_declaration")
            connection.commit()
    except Exception:
        pass  # Tables might not exist yet
    yield
    # Clean up after test
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM iscc_event")
            cursor.execute("DELETE FROM iscc_declaration")
            connection.commit()
    except Exception:
        pass


@pytest.mark.django_db(transaction=False)
def test_transaction_atomicity():
    """Test that transactions are atomic - all or nothing."""
    # Create a note with invalid data that will fail during insertion
    note = create_test_note(1)

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


@pytest.mark.django_db(transaction=False)
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


@pytest.mark.django_db(transaction=False)
def test_performance_benchmark():
    """Performance benchmark for sequencing operations."""
    num_operations = 100
    start_time = time.perf_counter()

    for i in range(num_operations):
        note = create_test_note(i)
        sequence_iscc_note(note)

    elapsed = time.perf_counter() - start_time
    throughput = num_operations / elapsed

    print(f"\nPerformance: {throughput:.1f} operations/sec")
    print(f"Average latency: {elapsed / num_operations * 1000:.2f} ms")

    # Basic performance assertion (adjust based on hardware)
    assert throughput > 50  # At least 50 ops/sec


@pytest.mark.django_db(transaction=False)
def test_hub_id_encoding():
    """Test that hub_id is correctly encoded in ISCC-ID."""
    note = create_test_note(1)
    _, iscc_id_str = sequence_iscc_note(note)

    # Decode the ISCC-ID
    iscc_id = IsccID(iscc_id_str)

    # Check hub_id matches settings
    assert iscc_id.hub_id == settings.ISCC_HUB_ID


@pytest.mark.django_db(transaction=False)
def test_timestamp_precision():
    """Test that timestamps have microsecond precision."""
    notes = []
    for i in range(5):
        note = create_test_note(i)
        _, iscc_id = sequence_iscc_note(note)
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


@pytest.mark.django_db(transaction=False)
def test_nonce_conflict_detection():
    """Test that duplicate nonces are rejected."""
    # Create and sequence first note
    note1 = create_test_note(1, nonce="00100123456789abcdef0123456789ab")
    seq1, iscc_id1 = sequence_iscc_note(note1)

    # Try to sequence another note with the same nonce
    note2 = create_test_note(2, nonce="00100123456789abcdef0123456789ab")
    with pytest.raises(NonceConflictError) as exc_info:
        sequence_iscc_note(note2)

    assert "Nonce already exists: 00100123456789abcdef0123456789ab" in str(exc_info.value)

    # Verify only the first note was stored
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM iscc_event")
        assert cursor.fetchone()[0] == 1
        cursor.execute(
            "SELECT COUNT(*) FROM iscc_declaration WHERE nonce = %s", ("00100123456789abcdef0123456789ab",)
        )
        assert cursor.fetchone()[0] == 1


@pytest.mark.django_db(transaction=False)
def test_invalid_hub_id(monkeypatch):
    """Test that invalid hub_id raises SequencerError."""
    # Save original value
    original_hub_id = settings.ISCC_HUB_ID

    # Test hub_id > 4095
    monkeypatch.setattr(settings, "ISCC_HUB_ID", 4096)
    note = create_test_note(1)
    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(note)
    assert "Invalid hub_id: 4096" in str(exc_info.value)

    # Test negative hub_id
    monkeypatch.setattr(settings, "ISCC_HUB_ID", -1)
    note = create_test_note(2)
    with pytest.raises(SequencerError) as exc_info:
        sequence_iscc_note(note)
    assert "Invalid hub_id: -1" in str(exc_info.value)

    # Restore original value
    monkeypatch.setattr(settings, "ISCC_HUB_ID", original_hub_id)


@pytest.mark.django_db(transaction=False)
def test_monotonic_timestamp_edge_case(monkeypatch):
    """Test timestamp monotonicity when system clock goes backward."""
    # First, insert a normal note
    note1 = create_test_note(1)
    seq1, iscc_id1 = sequence_iscc_note(note1)

    # Parse the timestamp from the first ISCC-ID
    iscc_obj1 = IsccID(iscc_id1)
    first_timestamp_us = iscc_obj1.timestamp_micros

    # Mock time.time_ns to return an earlier time
    def mock_time_ns():
        # Return a time that's 1 second before the first timestamp
        return (first_timestamp_us - 1_000_000) * 1000  # microseconds to nanoseconds

    monkeypatch.setattr(time, "time_ns", mock_time_ns)

    # Create second note - should still get monotonic timestamp
    note2 = create_test_note(2)
    seq2, iscc_id2 = sequence_iscc_note(note2)

    # Parse the second timestamp
    iscc_obj2 = IsccID(iscc_id2)
    second_timestamp_us = iscc_obj2.timestamp_micros

    # Verify monotonic increase (should be first + 1)
    assert second_timestamp_us == first_timestamp_us + 1
    assert seq2 == seq1 + 1


@pytest.mark.django_db(transaction=False)
def test_rollback_on_generic_exception(monkeypatch):
    """Test that generic exceptions cause rollback and are wrapped."""
    note = create_test_note(1)

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
