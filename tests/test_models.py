"""
Tests for Django models.
"""

import iscc_crypto as icr
import pytest

from iscc_hub.models import Event, IsccDeclaration
from tests.conftest import generate_test_iscc_id


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_model_creation(minimal_iscc_note):
    # type: (dict) -> None
    """
    Test basic Event model creation.
    """
    # Extract pubkey from the signed note
    pubkey = minimal_iscc_note["signature"]["pubkey"]

    event = Event.objects.create(
        iscc_id="ISCC:MEAJU3PC4ICWCTYI",
        iscc_note=minimal_iscc_note,
        pubkey=pubkey,
        nonce=minimal_iscc_note["nonce"],
        datahash=minimal_iscc_note["datahash"],
    )

    assert event.seq == 1
    assert event.iscc_id == "ISCC:MEAJU3PC4ICWCTYI"
    assert event.event_type == Event.EventType.CREATED
    assert event.iscc_note == minimal_iscc_note
    assert event.event_time is not None


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_gapless_sequence(example_timestamp, example_keypair, example_iscc_data):
    # type: (str, object, dict) -> None
    """
    Test that Event model maintains gapless sequence numbers.
    """

    # Create multiple events with unique nonces
    def create_unique_event(seq):
        # Generate unique nonce for each event
        unique_nonce = f"{seq:03d}faa3f18c7b9407a48536a9b00c4cb"
        note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": unique_nonce,
            "timestamp": example_timestamp,
        }
        signed_note = icr.sign_json(note, example_keypair)

        # Extract pubkey from the signed note
        pubkey = signed_note["signature"]["pubkey"]

        return Event.objects.create(
            iscc_id=generate_test_iscc_id(seq=seq),
            nonce=unique_nonce,
            datahash=example_iscc_data["datahash"],
            pubkey=pubkey,
            iscc_note=signed_note,
        )

    event1 = create_unique_event(1)
    event2 = create_unique_event(2)
    event3 = create_unique_event(3)

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
def test_event_types(example_timestamp, example_keypair, example_iscc_data):
    # type: (str, object, dict) -> None
    """
    Test different event types.
    """

    # Helper function to create unique events
    def create_unique_event(seq, event_type=Event.EventType.CREATED):
        unique_nonce = f"{seq:03d}faa3f18c7b9407a48536a9b00c4cb"
        note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": unique_nonce,
            "timestamp": example_timestamp,
        }
        signed_note = icr.sign_json(note, example_keypair)

        # Extract pubkey from the signed note
        pubkey = signed_note["signature"]["pubkey"]

        return Event.objects.create(
            event_type=event_type,
            iscc_id=generate_test_iscc_id(seq=seq),
            nonce=unique_nonce,
            datahash=example_iscc_data["datahash"],
            pubkey=pubkey,
            iscc_note=signed_note,
        )

    # Test CREATED (default)
    created_event = create_unique_event(10)
    assert created_event.event_type == Event.EventType.CREATED

    # Test UPDATED
    updated_event = create_unique_event(11, Event.EventType.UPDATED)
    assert updated_event.event_type == Event.EventType.UPDATED

    # Test DELETED
    deleted_event = create_unique_event(12, Event.EventType.DELETED)
    assert deleted_event.event_type == Event.EventType.DELETED

    # Test integer values
    assert Event.EventType.CREATED == 1
    assert Event.EventType.UPDATED == 2
    assert Event.EventType.DELETED == 3


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_str_representation(example_timestamp, example_keypair, example_iscc_data):
    # type: (str, object, dict) -> None
    """
    Test Event model string representation.
    """

    # Helper function to create unique events
    def create_unique_event(seq, event_type=Event.EventType.CREATED):
        unique_nonce = f"{seq:03d}faa3f18c7b9407a48536a9b00c4cb"
        note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": unique_nonce,
            "timestamp": example_timestamp,
        }
        signed_note = icr.sign_json(note, example_keypair)

        # Extract pubkey from the signed note
        pubkey = signed_note["signature"]["pubkey"]

        return Event.objects.create(
            event_type=event_type,
            iscc_id=generate_test_iscc_id(seq=seq),
            nonce=unique_nonce,
            datahash=example_iscc_data["datahash"],
            pubkey=pubkey,
            iscc_note=signed_note,
        )

    # Test CREATED event
    test_id = generate_test_iscc_id(seq=20)
    event = create_unique_event(20)
    assert str(event) == f"Event #1: Created {test_id}"

    # Test UPDATED event
    event2 = create_unique_event(21, Event.EventType.UPDATED)
    test_id2 = generate_test_iscc_id(seq=21)
    assert str(event2) == f"Event #2: Updated {test_id2}"

    # Test DELETED event
    event3 = create_unique_event(22, Event.EventType.DELETED)
    test_id3 = generate_test_iscc_id(seq=22)
    assert str(event3) == f"Event #3: Deleted {test_id3}"


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_non_unique_iscc_id(example_timestamp, example_keypair, example_iscc_data):
    # type: (str, object, dict) -> None
    """
    Test that multiple events can have the same ISCC-ID (for updates).
    """
    iscc_id = generate_test_iscc_id(seq=30)

    # Helper function to create unique events
    def create_unique_event(seq, event_type=Event.EventType.CREATED, gateway=None, metahash=None, units=None):
        unique_nonce = f"{seq:03d}faa3f18c7b9407a48536a9b00c4cb"
        note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": unique_nonce,
            "timestamp": example_timestamp,
        }
        # Add optional fields for full note
        if gateway:
            note["gateway"] = gateway
        if metahash:
            note["metahash"] = metahash
        if units:
            note["units"] = units

        signed_note = icr.sign_json(note, example_keypair)

        # Extract pubkey from the signed note
        pubkey = signed_note["signature"]["pubkey"]

        return Event.objects.create(
            event_type=event_type,
            iscc_id=iscc_id,  # Same ISCC-ID for all events
            nonce=unique_nonce,
            datahash=example_iscc_data["datahash"],
            pubkey=pubkey,
            iscc_note=signed_note,
        )

    # Create multiple events with same ISCC-ID but different nonces
    create_unique_event(30)

    create_unique_event(
        31,
        Event.EventType.UPDATED,
        gateway="https://example.com/iscc_id/{iscc_id}/metadata",
        metahash=example_iscc_data.get("metahash"),
        units=example_iscc_data.get("units"),
    )

    create_unique_event(32, Event.EventType.DELETED)

    # Query all events for this ISCC-ID
    events = Event.objects.filter(iscc_id=iscc_id)
    assert events.count() == 3
    assert events[0].event_type == Event.EventType.CREATED
    assert events[1].event_type == Event.EventType.UPDATED
    assert events[2].event_type == Event.EventType.DELETED


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_indexes(example_timestamp, example_keypair, example_iscc_data):
    # type: (str, object, dict) -> None
    """
    Test that indexes are properly applied.
    """
    # Create events to populate indexes
    test_ids = []
    for i in range(5):
        test_id = generate_test_iscc_id(seq=40 + i)
        test_ids.append(test_id)
        unique_nonce = f"{40 + i:03d}faa3f18c7b9407a48536a9b00c4cb"
        note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": unique_nonce,
            "timestamp": example_timestamp,
        }
        signed_note = icr.sign_json(note, example_keypair)

        # Extract pubkey from the signed note
        pubkey = signed_note["signature"]["pubkey"]

        Event.objects.create(
            iscc_id=test_id,
            nonce=unique_nonce,
            datahash=example_iscc_data["datahash"],
            pubkey=pubkey,
            iscc_note=signed_note,
            event_type=(i % 3) + 1,  # Cycle through event types
        )

    # Test queries that should use indexes
    # Query by iscc_id (indexed)
    results = Event.objects.filter(iscc_id=test_ids[0])
    assert results.count() == 1

    # Query by event_type (indexed)
    results = Event.objects.filter(event_type=Event.EventType.CREATED)
    assert results.count() >= 1

    # Query by event_time (indexed)
    first_event = Event.objects.first()
    results = Event.objects.filter(event_time__gte=first_event.event_time)
    assert results.count() == 5

    # Test chronological ordering via iscc_id
    events = list(Event.objects.all())
    assert len(events) == 5
    # Events should be ordered by sequence


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_event_model_meta():
    # type: () -> None
    """
    Test Event model Meta configuration.
    """
    # Test db_table
    assert Event._meta.db_table == "iscc_event"

    # Test ordering (removed for admin flexibility)
    assert Event._meta.ordering == []

    # Test verbose names
    assert Event._meta.verbose_name == "Event"
    assert Event._meta.verbose_name_plural == "Events"


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
    # Extract pubkey from the signed note
    pubkey = full_iscc_note["signature"]["pubkey"]

    event = Event.objects.create(
        iscc_id=generate_test_iscc_id(seq=50),
        iscc_note=full_iscc_note,
        pubkey=pubkey,
        nonce=full_iscc_note["nonce"],
        datahash=full_iscc_note["datahash"],
    )

    assert event.seq == 1
    assert event.iscc_id == generate_test_iscc_id(seq=50)
    assert event.event_type == Event.EventType.CREATED
    assert event.iscc_note == full_iscc_note
    assert "units" in event.iscc_note
    assert "metahash" in event.iscc_note
    assert "gateway" in event.iscc_note


# IsccDeclaration Model Tests


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_creation():
    # type: () -> None
    """
    Test basic IsccDeclaration model creation.
    """
    declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:MEAJU3PC4ICWCTYI",
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
    )

    assert declaration.iscc_id == "ISCC:MEAJU3PC4ICWCTYI"
    assert declaration.event_seq == 1
    assert declaration.deleted is False
    assert declaration.redacted is False
    assert declaration.gateway == ""
    assert declaration.metahash == ""
    assert declaration.updated_at is not None


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_with_optional_fields():
    # type: () -> None
    """
    Test IsccDeclaration with optional fields.
    """
    declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:MEAJU3PC4ICWCTYI",
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        gateway="https://gateway.example.com",
        metahash="1e20abcd1234567890abcdef1234567890abcdef1234567890abcdef12345678",
    )

    assert declaration.gateway == "https://gateway.example.com"
    assert declaration.metahash == "1e20abcd1234567890abcdef1234567890abcdef1234567890abcdef12345678"


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_str_representation():
    # type: () -> None
    """
    Test IsccDeclaration string representation.
    """
    # Test active declaration
    active_declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=60),
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        deleted=False,
    )
    assert str(active_declaration) == f"{generate_test_iscc_id(seq=60)} (active)"

    # Test deleted declaration
    deleted_declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=61),
        event_seq=2,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="001abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        deleted=True,
    )
    assert str(deleted_declaration) == f"{generate_test_iscc_id(seq=61)} (deleted)"


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_unique_constraints():
    # type: () -> None
    """
    Test unique constraints on IsccDeclaration.
    """
    # Create first declaration
    IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=70),
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
    )

    # Test iscc_id uniqueness (primary key)
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        IsccDeclaration.objects.create(
            iscc_id=generate_test_iscc_id(seq=70),  # Duplicate
            event_seq=2,
            iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
            datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
            nonce="001abcd1234567890abcdef123456789",
            actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        )

    # Test event_seq uniqueness
    with pytest.raises(IntegrityError):
        IsccDeclaration.objects.create(
            iscc_id=generate_test_iscc_id(seq=71),
            event_seq=1,  # Duplicate
            iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
            datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
            nonce="002abcd1234567890abcdef123456789",
            actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        )

    # Test nonce uniqueness
    with pytest.raises(IntegrityError):
        IsccDeclaration.objects.create(
            iscc_id=generate_test_iscc_id(seq=72),
            event_seq=3,
            iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
            datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
            nonce="000abcd1234567890abcdef123456789",  # Duplicate
            actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        )


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_soft_delete():
    # type: () -> None
    """
    Test soft delete functionality.
    """
    # Create declaration
    declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=80),
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
    )

    # Initially not deleted
    assert declaration.deleted is False

    # Soft delete
    declaration.deleted = True
    declaration.save()

    # Verify soft delete
    declaration = IsccDeclaration.objects.get(iscc_id=generate_test_iscc_id(seq=80))
    assert declaration.deleted is True

    # Verify filtering active declarations
    active_declarations = IsccDeclaration.objects.filter(deleted=False)
    assert generate_test_iscc_id(seq=80) not in [d.iscc_id for d in active_declarations]


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_redacted_field():
    # type: () -> None
    """
    Test redacted field functionality.
    """
    # Create declaration
    declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=81),
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        gateway="https://malicious.example.com",
    )

    # Initially not redacted (default value)
    assert declaration.redacted is False

    # Redact the declaration
    declaration.redacted = True
    declaration.save()

    # Verify redaction
    declaration = IsccDeclaration.objects.get(iscc_id=generate_test_iscc_id(seq=81))
    assert declaration.redacted is True

    # Verify filtering non-redacted declarations
    non_redacted = IsccDeclaration.objects.filter(redacted=False)
    assert generate_test_iscc_id(seq=81) not in [d.iscc_id for d in non_redacted]

    # Verify filtering redacted declarations
    redacted = IsccDeclaration.objects.filter(redacted=True)
    assert generate_test_iscc_id(seq=81) in [d.iscc_id for d in redacted]


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_redacted_and_deleted_combination():
    # type: () -> None
    """
    Test that redacted and deleted fields work independently.
    """
    # Create declaration
    declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=82),
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
    )

    # Both fields start as False
    assert declaration.deleted is False
    assert declaration.redacted is False

    # Set only redacted
    declaration.redacted = True
    declaration.save()
    declaration.refresh_from_db()
    assert declaration.deleted is False
    assert declaration.redacted is True

    # Set both deleted and redacted
    declaration.deleted = True
    declaration.save()
    declaration.refresh_from_db()
    assert declaration.deleted is True
    assert declaration.redacted is True

    # Query declarations with different combinations
    all_active = IsccDeclaration.objects.filter(deleted=False, redacted=False)
    deleted_only = IsccDeclaration.objects.filter(deleted=True, redacted=False)
    redacted_only = IsccDeclaration.objects.filter(deleted=False, redacted=True)
    both = IsccDeclaration.objects.filter(deleted=True, redacted=True)

    # Our declaration should only appear in the 'both' query
    assert generate_test_iscc_id(seq=82) not in [d.iscc_id for d in all_active]
    assert generate_test_iscc_id(seq=82) not in [d.iscc_id for d in deleted_only]
    assert generate_test_iscc_id(seq=82) not in [d.iscc_id for d in redacted_only]
    assert generate_test_iscc_id(seq=82) in [d.iscc_id for d in both]


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_indexes():
    # type: () -> None
    """
    Test that indexes work for efficient queries.
    """
    # Create multiple declarations
    for i in range(5):
        IsccDeclaration.objects.create(
            iscc_id=generate_test_iscc_id(seq=90 + i),
            event_seq=i + 1,
            iscc_code=f"ISCC:CODE{i % 2}",  # Two different codes
            datahash=f"1e20{'a' * 64}" if i % 2 == 0 else f"1e20{'b' * 64}",
            nonce=f"{i:03d}abcd1234567890abcdef123456789",
            actor=f"actor{i % 3}",  # Three different actors
            deleted=(i == 4),  # Last one is deleted
        )

    # Test indexed queries
    # Query by iscc_code
    results = IsccDeclaration.objects.filter(iscc_code="ISCC:CODE0")
    assert results.count() == 3

    # Query by datahash
    results = IsccDeclaration.objects.filter(datahash=f"1e20{'a' * 64}")
    assert results.count() == 3

    # Query by actor
    results = IsccDeclaration.objects.filter(actor="actor0")
    assert results.count() == 2

    # Query by actor and iscc_code
    results = IsccDeclaration.objects.filter(actor="actor0", iscc_code="ISCC:CODE0")
    assert results.count() == 1

    # Query active declarations
    results = IsccDeclaration.objects.filter(deleted=False)
    assert results.count() == 4

    # Query by event_seq
    results = IsccDeclaration.objects.filter(event_seq=3)
    assert results.count() == 1


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_update():
    # type: () -> None
    """
    Test updating an IsccDeclaration (full replacement).
    """
    # Create initial declaration
    declaration = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=100),
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="actor1",
        gateway="https://old.gateway.com",
    )

    original_updated_at = declaration.updated_at

    # Add small delay to ensure timestamp changes (Windows timing precision issue)
    import time

    time.sleep(0.001)

    # Simulate full replacement update
    declaration.event_seq = 2
    declaration.iscc_code = "ISCC:NEWCODE"
    declaration.datahash = "1e20ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    declaration.actor = "actor2"
    declaration.gateway = "https://new.gateway.com"
    declaration.save()

    # Verify updates
    declaration = IsccDeclaration.objects.get(iscc_id=generate_test_iscc_id(seq=100))
    assert declaration.event_seq == 2
    assert declaration.iscc_code == "ISCC:NEWCODE"
    assert declaration.datahash == "1e20ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    assert declaration.actor == "actor2"
    assert declaration.gateway == "https://new.gateway.com"
    assert declaration.updated_at > original_updated_at  # auto_now should update


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_model_meta():
    # type: () -> None
    """
    Test IsccDeclaration model Meta configuration.
    """
    # Test db_table
    assert IsccDeclaration._meta.db_table == "iscc_declaration"

    # Test verbose names
    assert IsccDeclaration._meta.verbose_name == "Declaration"
    assert IsccDeclaration._meta.verbose_name_plural == "Declarations"

    # Test primary key
    pk_field = IsccDeclaration._meta.pk
    assert pk_field.name == "iscc_id"

    # Test indexes exist (checking they're defined, not their actual behavior)
    index_fields = []
    for index in IsccDeclaration._meta.indexes:
        index_fields.append(index.fields)

    # Verify expected indexes are present
    assert ["iscc_code", "-iscc_id"] in index_fields
    assert ["datahash", "-iscc_id"] in index_fields
    assert ["actor", "-iscc_id"] in index_fields
    assert ["actor", "iscc_code"] in index_fields
    assert ["actor", "datahash"] in index_fields
    assert ["deleted", "-iscc_id"] in index_fields
    assert ["redacted", "-iscc_id"] in index_fields
    assert ["event_seq", "deleted"] in index_fields


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_duplicate_content_allowed():
    # type: () -> None
    """
    Test that the same actor can declare the same content multiple times.
    This verifies no database constraints prevent duplicate declarations.
    """
    actor = "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1"
    iscc_code = "ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ"
    datahash = "1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c"

    # Create first declaration
    declaration1 = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=110),
        event_seq=1,
        iscc_code=iscc_code,
        datahash=datahash,
        nonce="000abcd1234567890abcdef123456789",
        actor=actor,
    )

    # Create second declaration with same actor, iscc_code, and datahash
    # This should succeed as we removed unique constraints
    declaration2 = IsccDeclaration.objects.create(
        iscc_id=generate_test_iscc_id(seq=111),
        event_seq=2,
        iscc_code=iscc_code,  # Same code
        datahash=datahash,  # Same hash
        nonce="001abcd1234567890abcdef123456789",  # Different nonce
        actor=actor,  # Same actor
    )

    # Verify both exist
    assert declaration1.iscc_id == generate_test_iscc_id(seq=110)
    assert declaration2.iscc_id == generate_test_iscc_id(seq=111)

    # Query declarations by actor and iscc_code
    declarations = IsccDeclaration.objects.filter(actor=actor, iscc_code=iscc_code)
    assert declarations.count() == 2
