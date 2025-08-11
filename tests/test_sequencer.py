"""
Tests for the sequencer module.
"""

import threading
import time
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import OperationalError, connection

from iscc_hub.iscc_id import IsccID
from iscc_hub.models import Event, IsccDeclaration
from iscc_hub.sequencer import (
    RetryTransaction,
    SequencerError,
    create_event,
    delete_declaration,
    generate_iscc_id,
    get_last_iscc_id,
    materialize_declaration,
    sequence_declaration,
    sequence_declaration_with_retry,
)


@pytest.mark.django_db
def test_get_last_iscc_id_returns_none_for_empty_db():
    # type: () -> None
    """Test get_last_iscc_id returns None when no events exist."""
    result = get_last_iscc_id()
    assert result is None


@pytest.mark.django_db
def test_get_last_iscc_id_returns_latest_event(minimal_iscc_note):
    # type: (dict) -> None
    """Test get_last_iscc_id returns the last ISCC-ID."""
    # Create some events
    Event.objects.create(event_type=Event.EventType.CREATED, iscc_id=b"12345678", iscc_note=minimal_iscc_note)
    Event.objects.create(event_type=Event.EventType.CREATED, iscc_id=b"87654321", iscc_note=minimal_iscc_note)

    result = get_last_iscc_id()
    assert result == b"87654321"


@pytest.mark.django_db
def test_generate_iscc_id_first_id():
    # type: () -> None
    """Test generating the first ISCC-ID with no predecessor."""
    # Generate ISCC-ID
    iscc_id_bytes = generate_iscc_id(None)

    # Decode the ISCC-ID
    iscc_id = IsccID(iscc_id_bytes)
    assert iscc_id.hub_id == settings.ISCC_HUB_ID


@pytest.mark.django_db
def test_generate_iscc_id_monotonic_ordering():
    # type: () -> None
    """Test that ISCC-IDs are monotonically increasing."""
    # Create a previous ISCC-ID with current timestamp
    prev_timestamp_us = int(time.time() * 1_000_000)
    prev_iscc_id = IsccID.from_timestamp(prev_timestamp_us, settings.ISCC_HUB_ID)

    # Generate new ISCC-ID - should be at least prev + 1
    new_iscc_id_bytes = generate_iscc_id(prev_iscc_id.bytes_body)

    # New timestamp should be greater than previous
    new_iscc_id = IsccID(new_iscc_id_bytes)
    assert new_iscc_id.timestamp_micros > prev_timestamp_us


@pytest.mark.django_db
def test_generate_iscc_id_temporal_drift_raises_retry():
    # type: () -> None
    """Test that excessive temporal drift raises RetryTransaction."""
    # Create a previous ISCC-ID that's far in the future
    future_timestamp_us = int(time.time() * 1_000_000) + 2_000_000  # 2 seconds ahead
    future_iscc_id = IsccID.from_timestamp(future_timestamp_us, settings.ISCC_HUB_ID)

    with pytest.raises(RetryTransaction) as exc_info:
        generate_iscc_id(future_iscc_id.bytes_body)

    assert "Temporal drift" in str(exc_info.value)


@pytest.mark.django_db
def test_create_event(minimal_iscc_note):
    # type: (dict) -> None
    """Test creating an Event record."""
    iscc_id_bytes = b"12345678"

    event = create_event(minimal_iscc_note, iscc_id_bytes, Event.EventType.CREATED)

    assert event.seq is not None
    assert event.event_type == Event.EventType.CREATED
    assert event.iscc_id == iscc_id_bytes
    assert event.iscc_note == minimal_iscc_note
    assert Event.objects.filter(seq=event.seq).exists()


@pytest.mark.django_db
def test_materialize_declaration_creates_new(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test materializing a new declaration."""
    # Create an event
    event = Event.objects.create(
        event_type=Event.EventType.CREATED, iscc_id=b"12345678", iscc_note=minimal_iscc_note
    )

    actor = example_keypair.public_key
    declaration = materialize_declaration(event, minimal_iscc_note, actor)

    # IsccIDField returns string representation, compare using IsccID
    assert IsccID(declaration.iscc_id).bytes_body == b"12345678"
    assert declaration.event_seq == event.seq
    assert declaration.iscc_code == minimal_iscc_note["iscc_code"]
    assert declaration.datahash == minimal_iscc_note["datahash"]
    assert declaration.nonce == minimal_iscc_note["nonce"]
    assert declaration.actor == actor
    assert declaration.deleted is False


@pytest.mark.django_db
def test_materialize_declaration_updates_existing(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test materializing an update to existing declaration."""
    actor = example_keypair.public_key

    # Create initial declaration
    initial_event = Event.objects.create(
        event_type=Event.EventType.CREATED, iscc_id=b"12345678", iscc_note=minimal_iscc_note
    )
    initial_decl = materialize_declaration(initial_event, minimal_iscc_note, actor)
    initial_created_at = initial_decl.created_at

    # Create update event with new nonce
    updated_note = minimal_iscc_note.copy()
    updated_note["nonce"] = "111faa3f18c7b9407a48536a9b00c4cb"
    update_event = Event.objects.create(
        event_type=Event.EventType.UPDATED, iscc_id=b"12345678", iscc_note=updated_note
    )

    updated_decl = materialize_declaration(update_event, updated_note, actor)

    # IsccIDField returns string representation, compare using IsccID
    assert IsccID(updated_decl.iscc_id).bytes_body == b"12345678"
    assert updated_decl.event_seq == update_event.seq
    assert updated_decl.nonce == updated_note["nonce"]
    assert updated_decl.created_at == initial_created_at  # Created_at should not change


@pytest.mark.django_db
def test_materialize_declaration_marks_deleted(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test materializing a deletion."""
    actor = example_keypair.public_key

    # Create deletion event
    event = Event.objects.create(
        event_type=Event.EventType.DELETED, iscc_id=b"12345678", iscc_note=minimal_iscc_note
    )

    declaration = materialize_declaration(event, minimal_iscc_note, actor)

    assert declaration.deleted is True


@pytest.mark.django_db
def test_sequence_declaration_creates_new(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test sequencing a new declaration."""
    actor = example_keypair.public_key

    event, declaration = sequence_declaration(minimal_iscc_note, actor)

    assert event.event_type == Event.EventType.CREATED
    assert declaration.actor == actor
    assert declaration.iscc_code == minimal_iscc_note["iscc_code"]
    assert declaration.datahash == minimal_iscc_note["datahash"]
    assert declaration.nonce == minimal_iscc_note["nonce"]
    assert declaration.deleted is False

    # Verify ISCC-ID was generated
    iscc_id = IsccID(declaration.iscc_id)
    assert iscc_id.hub_id == settings.ISCC_HUB_ID


@pytest.mark.django_db
def test_sequence_declaration_updates_existing(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test sequencing an update to existing declaration."""
    actor = example_keypair.public_key

    # Create initial declaration
    initial_event, initial_decl = sequence_declaration(minimal_iscc_note, actor)

    # Update with new nonce
    updated_note = minimal_iscc_note.copy()
    updated_note["nonce"] = "222faa3f18c7b9407a48536a9b00c4cb"

    event, declaration = sequence_declaration(
        updated_note, actor, update_iscc_id=str(IsccID(initial_decl.iscc_id))
    )

    assert event.event_type == Event.EventType.UPDATED
    # Both declarations should have the same ISCC-ID (compare as bytes)
    assert IsccID(declaration.iscc_id).bytes_body == IsccID(initial_decl.iscc_id).bytes_body
    assert declaration.nonce == updated_note["nonce"]
    assert declaration.event_seq > initial_decl.event_seq


@pytest.mark.django_db
def test_sequence_declaration_handles_retry_transaction(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test that sequence_declaration retries on RetryTransaction."""
    actor = example_keypair.public_key

    # Create a future ISCC-ID that will trigger a retry (between 1-2 seconds)
    # This should trigger the retry logic but eventually succeed
    future_timestamp_us = int(time.time() * 1_000_000) + 1_200_000  # 1.2s ahead
    future_iscc_id = IsccID.from_timestamp(future_timestamp_us, settings.ISCC_HUB_ID)

    # Create an event with future timestamp
    Event.objects.create(
        event_type=Event.EventType.CREATED,
        iscc_id=future_iscc_id.bytes_body,
        iscc_note=minimal_iscc_note,
    )

    # This should succeed after retry
    event, declaration = sequence_declaration(minimal_iscc_note, actor)

    assert event is not None
    assert declaration is not None
    # Verify it generated a timestamp after the future one
    assert IsccID(event.iscc_id).timestamp_micros > future_timestamp_us


@pytest.mark.django_db
def test_sequence_declaration_handles_exception(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test that sequence_declaration handles exceptions properly."""
    actor = example_keypair.public_key

    # Create an invalid note that will cause an error
    invalid_note = minimal_iscc_note.copy()
    invalid_note["iscc_code"] = None  # This will cause an error

    with pytest.raises(SequencerError) as exc_info:
        sequence_declaration(invalid_note, actor)

    assert "Failed to sequence declaration" in str(exc_info.value)


@pytest.mark.django_db
def test_sequence_declaration_with_retry_handles_lock(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test retry mechanism for database locks."""
    actor = example_keypair.public_key

    # This should succeed normally
    event, declaration = sequence_declaration_with_retry(minimal_iscc_note, actor)

    assert event is not None
    assert declaration is not None


@pytest.mark.django_db
def test_delete_declaration_success(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test successful deletion of a declaration."""
    actor = example_keypair.public_key

    # Create a declaration
    event, declaration = sequence_declaration(minimal_iscc_note, actor)

    iscc_id_str = str(IsccID(declaration.iscc_id))

    # Delete it
    delete_event, deleted_decl = delete_declaration(iscc_id_str, actor)

    assert delete_event.event_type == Event.EventType.DELETED
    assert deleted_decl.deleted is True
    assert deleted_decl.event_seq == delete_event.seq


@pytest.mark.django_db
def test_delete_declaration_unauthorized(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test deletion fails for different actor."""
    actor = example_keypair.public_key

    # Create a declaration
    event, declaration = sequence_declaration(minimal_iscc_note, actor)

    iscc_id_str = str(IsccID(declaration.iscc_id))

    # Try to delete with different actor
    with pytest.raises(SequencerError) as exc_info:
        delete_declaration(iscc_id_str, "DifferentActor123")

    assert "owned by another actor" in str(exc_info.value)


@pytest.mark.django_db
def test_delete_declaration_not_found(example_keypair):
    # type: (object) -> None
    """Test deletion fails for non-existent ISCC-ID."""
    actor = example_keypair.public_key

    # Try to delete non-existent
    fake_iscc_id = str(IsccID.from_timestamp(1735689600_000_000, 1))

    with pytest.raises(SequencerError) as exc_info:
        delete_declaration(fake_iscc_id, actor)

    assert "not found" in str(exc_info.value)


@pytest.mark.django_db
def test_sequencer_error_inheritance():
    # type: () -> None
    """Test that SequencerError inherits from Exception."""
    error = SequencerError("Test error")
    assert isinstance(error, Exception)
    assert str(error) == "Test error"


@pytest.mark.django_db
def test_retry_transaction_inheritance():
    # type: () -> None
    """Test that RetryTransaction inherits from Exception."""
    error = RetryTransaction("Test retry")
    assert isinstance(error, Exception)
    assert str(error) == "Test retry"


@pytest.mark.django_db
def test_sequence_declaration_with_retry_sequencer_error(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test sequence_declaration_with_retry propagates SequencerError."""
    actor = example_keypair.public_key

    # Use invalid data to trigger SequencerError
    invalid_note = minimal_iscc_note.copy()
    invalid_note["iscc_code"] = None

    with pytest.raises(SequencerError) as exc_info:
        sequence_declaration_with_retry(invalid_note, actor)

    assert "Failed to sequence" in str(exc_info.value)


@pytest.mark.django_db
def test_delete_declaration_with_gateway_metahash(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test deletion preserves gateway and metahash in event."""
    actor = example_keypair.public_key

    # Create note with gateway and metahash
    note_with_extras = minimal_iscc_note.copy()
    note_with_extras["gateway"] = "https://example.com"
    note_with_extras["metahash"] = "1234567890abcdef"

    # Create a declaration
    event, declaration = sequence_declaration(note_with_extras, actor)

    iscc_id_str = str(IsccID(declaration.iscc_id))

    # Delete it
    delete_event, deleted_decl = delete_declaration(iscc_id_str, actor)

    # Check the event contains gateway and metahash
    assert delete_event.iscc_note["gateway"] == "https://example.com"
    assert delete_event.iscc_note["metahash"] == "1234567890abcdef"
    assert delete_event.event_type == Event.EventType.DELETED
    assert deleted_decl.deleted is True


@pytest.mark.django_db
def test_sequence_declaration_with_retry_database_lock(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test sequence_declaration_with_retry handles database locks with retry."""
    actor = example_keypair.public_key

    # Track calls to sequence_declaration
    call_count = [0]
    original_sequence = sequence_declaration

    def mock_sequence(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call raises database lock error
            raise OperationalError("database is locked")
        # Second call succeeds
        return original_sequence(*args, **kwargs)

    with patch("iscc_hub.sequencer.sequence_declaration", side_effect=mock_sequence):
        with patch("time.sleep"):  # Skip actual sleep
            event, declaration = sequence_declaration_with_retry(minimal_iscc_note, actor)

    assert event is not None
    assert declaration is not None
    assert call_count[0] == 2  # Verify it was called twice


@pytest.mark.django_db
def test_sequence_declaration_with_retry_max_attempts_exceeded():
    # type: () -> None
    """Test sequence_declaration_with_retry fails after max attempts."""
    from iscc_hub.sequencer import sequence_declaration_with_retry

    # Mock sequence_declaration to always raise database lock error
    def mock_sequence(*args, **kwargs):
        raise OperationalError("database is locked")

    with patch("iscc_hub.sequencer.sequence_declaration", side_effect=mock_sequence):
        with patch("time.sleep"):  # Skip actual sleep
            with pytest.raises(SequencerError) as exc_info:
                sequence_declaration_with_retry({}, "actor", max_retries=3)

            assert "Failed to sequence after 3 attempts" in str(exc_info.value)


@pytest.mark.django_db
def test_sequence_declaration_with_retry_unexpected_error(minimal_iscc_note, example_keypair):
    # type: (dict, object) -> None
    """Test sequence_declaration_with_retry handles unexpected errors."""
    actor = example_keypair.public_key

    # Mock sequence_declaration to raise an unexpected error
    def mock_sequence(*args, **kwargs):
        raise ValueError("Unexpected error")

    with patch("iscc_hub.sequencer.sequence_declaration", side_effect=mock_sequence):
        with pytest.raises(SequencerError) as exc_info:
            sequence_declaration_with_retry(minimal_iscc_note, actor)

        assert "Unexpected error during sequencing" in str(exc_info.value)


@pytest.mark.django_db
def test_sequence_declaration_with_retry_exhausts_retries():
    # type: () -> None
    """Test that sequence_declaration_with_retry exhausts all retries."""
    from iscc_hub.sequencer import sequence_declaration_with_retry

    # This test verifies the final line that raises after the loop
    # We need a scenario where we exit the loop normally without returning

    # Mock to track calls
    call_count = [0]

    def mock_sequence(*args, **kwargs):
        call_count[0] += 1
        # Always succeed but return None to simulate no valid result
        return None, None

    # Since sequence_declaration always returns a tuple, we need a different approach
    # The only way to reach the final line is if max_retries is 0
    with pytest.raises(SequencerError) as exc_info:
        sequence_declaration_with_retry({}, "actor", max_retries=0)

    assert "Failed to sequence after 0 attempts" in str(exc_info.value)
