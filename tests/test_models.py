"""
Tests for Django models.
"""

import pytest

from iscc_hub.models import Event


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_model_creation(minimal_iscc_note):
    # type: (dict) -> None
    """
    Test basic Event model creation.
    """
    event = Event.objects.create(iscc_id="ISCC:MEAJU3PC4ICWCTYI", iscc_note=minimal_iscc_note)

    assert event.seq == 1
    assert event.iscc_id == "ISCC:MEAJU3PC4ICWCTYI"
    assert event.event_type == Event.EventType.CREATED
    assert event.iscc_note == minimal_iscc_note
    assert event.timestamp is not None


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_gapless_sequence(minimal_iscc_note):
    # type: (dict) -> None
    """
    Test that Event model maintains gapless sequence numbers.
    """
    # Create multiple events
    event1 = Event.objects.create(iscc_id="ISCC:TEST1", iscc_note=minimal_iscc_note)
    event2 = Event.objects.create(iscc_id="ISCC:TEST2", iscc_note=minimal_iscc_note)
    event3 = Event.objects.create(iscc_id="ISCC:TEST3", iscc_note=minimal_iscc_note)

    # Verify sequence is gapless
    assert event1.seq == 1
    assert event2.seq == 2
    assert event3.seq == 3

    # Verify ordering
    events = list(Event.objects.all())
    assert events[0].seq == 1
    assert events[1].seq == 2
    assert events[2].seq == 3


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_types(minimal_iscc_note):
    # type: (dict) -> None
    """
    Test different event types.
    """
    # Test CREATED (default)
    created_event = Event.objects.create(iscc_id="ISCC:CREATED", iscc_note=minimal_iscc_note)
    assert created_event.event_type == Event.EventType.CREATED

    # Test UPDATED
    updated_event = Event.objects.create(
        event_type=Event.EventType.UPDATED, iscc_id="ISCC:UPDATED", iscc_note=minimal_iscc_note
    )
    assert updated_event.event_type == Event.EventType.UPDATED

    # Test DELETED
    deleted_event = Event.objects.create(
        event_type=Event.EventType.DELETED, iscc_id="ISCC:DELETED", iscc_note=minimal_iscc_note
    )
    assert deleted_event.event_type == Event.EventType.DELETED

    # Test integer values
    assert Event.EventType.CREATED == 1
    assert Event.EventType.UPDATED == 2
    assert Event.EventType.DELETED == 3


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_str_representation(minimal_iscc_note):
    # type: (dict) -> None
    """
    Test Event model string representation.
    """
    # Test CREATED event
    event = Event.objects.create(iscc_id="ISCC:TESTID", iscc_note=minimal_iscc_note)
    assert str(event) == "Event #1: Created ISCC:TESTID"

    # Test UPDATED event
    event2 = Event.objects.create(
        event_type=Event.EventType.UPDATED, iscc_id="ISCC:TESTID", iscc_note=minimal_iscc_note
    )
    assert str(event2) == "Event #2: Updated ISCC:TESTID"

    # Test DELETED event
    event3 = Event.objects.create(
        event_type=Event.EventType.DELETED, iscc_id="ISCC:TESTID", iscc_note=minimal_iscc_note
    )
    assert str(event3) == "Event #3: Deleted ISCC:TESTID"


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_non_unique_iscc_id(minimal_iscc_note, full_iscc_note):
    # type: (dict, dict) -> None
    """
    Test that multiple events can have the same ISCC-ID (for updates).
    """
    iscc_id = "ISCC:SAMEID"

    # Create multiple events with same ISCC-ID
    Event.objects.create(iscc_id=iscc_id, iscc_note=minimal_iscc_note)

    Event.objects.create(
        event_type=Event.EventType.UPDATED,
        iscc_id=iscc_id,
        iscc_note=full_iscc_note,  # Different note content for update
    )

    Event.objects.create(event_type=Event.EventType.DELETED, iscc_id=iscc_id, iscc_note=minimal_iscc_note)

    # Query all events for this ISCC-ID
    events = Event.objects.filter(iscc_id=iscc_id)
    assert events.count() == 3
    assert events[0].event_type == Event.EventType.CREATED
    assert events[1].event_type == Event.EventType.UPDATED
    assert events[2].event_type == Event.EventType.DELETED


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_indexes(minimal_iscc_note):
    # type: (dict) -> None
    """
    Test that indexes are properly applied.
    """
    # Create events to populate indexes
    for i in range(5):
        Event.objects.create(
            iscc_id=f"ISCC:TEST{i}",
            iscc_note=minimal_iscc_note,
            event_type=(i % 3) + 1,  # Cycle through event types
        )

    # Test queries that should use indexes
    # Query by iscc_id (indexed)
    results = Event.objects.filter(iscc_id="ISCC:TEST0")
    assert results.count() == 1

    # Query by event_type (indexed)
    results = Event.objects.filter(event_type=Event.EventType.CREATED)
    assert results.count() >= 1

    # Query by timestamp (indexed)
    first_event = Event.objects.first()
    results = Event.objects.filter(timestamp__gte=first_event.timestamp)
    assert results.count() == 5


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_model_meta():
    # type: () -> None
    """
    Test Event model Meta configuration.
    """
    # Test db_table
    assert Event._meta.db_table == "iscc_event"

    # Test ordering
    assert Event._meta.ordering == ["seq"]

    # Test verbose names
    assert Event._meta.verbose_name == "ISCC Event"
    assert Event._meta.verbose_name_plural == "ISCC Events"


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_type_choices():
    # type: () -> None
    """
    Test EventType choices configuration.
    """
    choices = Event.EventType.choices
    assert len(choices) == 3
    assert (1, "Created") in choices
    assert (2, "Updated") in choices
    assert (3, "Deleted") in choices

    # Test labels
    assert Event.EventType.CREATED.label == "Created"
    assert Event.EventType.UPDATED.label == "Updated"
    assert Event.EventType.DELETED.label == "Deleted"

    # Test values
    assert Event.EventType.CREATED.value == 1
    assert Event.EventType.UPDATED.value == 2
    assert Event.EventType.DELETED.value == 3


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_with_full_iscc_note(full_iscc_note):
    # type: (dict) -> None
    """
    Test Event model with full IsccNote including optional fields.
    """
    event = Event.objects.create(iscc_id="ISCC:FULLNOTE", iscc_note=full_iscc_note)

    assert event.seq == 1
    assert event.iscc_id == "ISCC:FULLNOTE"
    assert event.event_type == Event.EventType.CREATED
    assert event.iscc_note == full_iscc_note
    assert "units" in event.iscc_note
    assert "metahash" in event.iscc_note
    assert "gateway" in event.iscc_note
