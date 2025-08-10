"""
Tests for Django models.
"""

from datetime import datetime

import pytest
from django.utils import timezone

from iscc_hub.models import Event, IsccDeclaration


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


# IsccDeclaration Model Tests


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_creation():
    # type: () -> None
    """
    Test basic IsccDeclaration model creation.
    """
    now = timezone.now()
    declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:MEAJU3PC4ICWCTYI",
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        declared_at=now,
        created_at=now,
    )

    assert declaration.iscc_id == "ISCC:MEAJU3PC4ICWCTYI"
    assert declaration.event_seq == 1
    assert declaration.deleted is False
    assert declaration.gateway == ""
    assert declaration.metahash == ""
    assert declaration.updated_at is not None


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_with_optional_fields():
    # type: () -> None
    """
    Test IsccDeclaration with optional fields.
    """
    now = timezone.now()
    declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:MEAJU3PC4ICWCTYI",
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        gateway="https://gateway.example.com",
        metahash="1e20abcd1234567890abcdef1234567890abcdef1234567890abcdef12345678",
        declared_at=now,
        created_at=now,
    )

    assert declaration.gateway == "https://gateway.example.com"
    assert declaration.metahash == "1e20abcd1234567890abcdef1234567890abcdef1234567890abcdef12345678"


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_str_representation():
    # type: () -> None
    """
    Test IsccDeclaration string representation.
    """
    now = timezone.now()

    # Test active declaration
    active_declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:ACTIVE123",
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        declared_at=now,
        created_at=now,
        deleted=False,
    )
    assert str(active_declaration) == "ISCC:ACTIVE123 (active)"

    # Test deleted declaration
    deleted_declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:DELETED123",
        event_seq=2,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="001abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        declared_at=now,
        created_at=now,
        deleted=True,
    )
    assert str(deleted_declaration) == "ISCC:DELETED123 (deleted)"


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_unique_constraints():
    # type: () -> None
    """
    Test unique constraints on IsccDeclaration.
    """
    now = timezone.now()

    # Create first declaration
    IsccDeclaration.objects.create(
        iscc_id="ISCC:TEST1",
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        declared_at=now,
        created_at=now,
    )

    # Test iscc_id uniqueness (primary key)
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        IsccDeclaration.objects.create(
            iscc_id="ISCC:TEST1",  # Duplicate
            event_seq=2,
            iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
            datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
            nonce="001abcd1234567890abcdef123456789",
            actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
            declared_at=now,
            created_at=now,
        )

    # Test event_seq uniqueness
    with pytest.raises(IntegrityError):
        IsccDeclaration.objects.create(
            iscc_id="ISCC:TEST2",
            event_seq=1,  # Duplicate
            iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
            datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
            nonce="002abcd1234567890abcdef123456789",
            actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
            declared_at=now,
            created_at=now,
        )

    # Test nonce uniqueness
    with pytest.raises(IntegrityError):
        IsccDeclaration.objects.create(
            iscc_id="ISCC:TEST3",
            event_seq=3,
            iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
            datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
            nonce="000abcd1234567890abcdef123456789",  # Duplicate
            actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
            declared_at=now,
            created_at=now,
        )


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_soft_delete():
    # type: () -> None
    """
    Test soft delete functionality.
    """
    now = timezone.now()

    # Create declaration
    declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:SOFTDELETE",
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        declared_at=now,
        created_at=now,
    )

    # Initially not deleted
    assert declaration.deleted is False

    # Soft delete
    declaration.deleted = True
    declaration.save()

    # Verify soft delete
    declaration = IsccDeclaration.objects.get(iscc_id="ISCC:SOFTDELETE")
    assert declaration.deleted is True

    # Verify filtering active declarations
    active_declarations = IsccDeclaration.objects.filter(deleted=False)
    assert "ISCC:SOFTDELETE" not in [d.iscc_id for d in active_declarations]


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_indexes():
    # type: () -> None
    """
    Test that indexes work for efficient queries.
    """
    now = timezone.now()

    # Create multiple declarations
    for i in range(5):
        IsccDeclaration.objects.create(
            iscc_id=f"ISCC:TEST{i}",
            event_seq=i + 1,
            iscc_code=f"ISCC:CODE{i % 2}",  # Two different codes
            datahash=f"1e20{'a' * 64}" if i % 2 == 0 else f"1e20{'b' * 64}",
            nonce=f"{i:03d}abcd1234567890abcdef123456789",
            actor=f"actor{i % 3}",  # Three different actors
            declared_at=now,
            created_at=now,
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
    now = timezone.now()

    # Create initial declaration
    declaration = IsccDeclaration.objects.create(
        iscc_id="ISCC:UPDATE",
        event_seq=1,
        iscc_code="ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ",
        datahash="1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c",
        nonce="000abcd1234567890abcdef123456789",
        actor="actor1",
        gateway="https://old.gateway.com",
        declared_at=now,
        created_at=now,
    )

    original_updated_at = declaration.updated_at

    # Simulate full replacement update
    declaration.event_seq = 2
    declaration.iscc_code = "ISCC:NEWCODE"
    declaration.datahash = "1e20ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    declaration.actor = "actor2"
    declaration.gateway = "https://new.gateway.com"
    declaration.save()

    # Verify updates
    declaration = IsccDeclaration.objects.get(iscc_id="ISCC:UPDATE")
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

    # Test primary key
    pk_field = IsccDeclaration._meta.pk
    assert pk_field.name == "iscc_id"

    # Test indexes exist (checking they're defined, not their actual behavior)
    index_fields = []
    for index in IsccDeclaration._meta.indexes:
        index_fields.append(index.fields)

    # Verify expected indexes are present
    assert ["iscc_code", "-created_at"] in index_fields
    assert ["datahash", "-created_at"] in index_fields
    assert ["actor", "-created_at"] in index_fields
    assert ["actor", "iscc_code"] in index_fields
    assert ["actor", "datahash"] in index_fields
    assert ["deleted", "-created_at"] in index_fields
    assert ["event_seq", "deleted"] in index_fields


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_iscc_declaration_duplicate_content_allowed():
    # type: () -> None
    """
    Test that the same actor can declare the same content multiple times.
    This verifies no database constraints prevent duplicate declarations.
    """
    now = timezone.now()
    actor = "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1"
    iscc_code = "ISCC:KACT7BESWDYQXSWQSVBOBQCTBPQGQVJ3WH7XWZLW3IWNT4H5MOBOTPQ"
    datahash = "1e208e3ca3f3a5fe9a5e5c8f9e5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c5f5c"

    # Create first declaration
    declaration1 = IsccDeclaration.objects.create(
        iscc_id="ISCC:FIRST",
        event_seq=1,
        iscc_code=iscc_code,
        datahash=datahash,
        nonce="000abcd1234567890abcdef123456789",
        actor=actor,
        declared_at=now,
        created_at=now,
    )

    # Create second declaration with same actor, iscc_code, and datahash
    # This should succeed as we removed unique constraints
    declaration2 = IsccDeclaration.objects.create(
        iscc_id="ISCC:SECOND",
        event_seq=2,
        iscc_code=iscc_code,  # Same code
        datahash=datahash,  # Same hash
        nonce="001abcd1234567890abcdef123456789",  # Different nonce
        actor=actor,  # Same actor
        declared_at=now,
        created_at=now,
    )

    # Verify both exist
    assert declaration1.iscc_id == "ISCC:FIRST"
    assert declaration2.iscc_id == "ISCC:SECOND"

    # Query declarations by actor and iscc_code
    declarations = IsccDeclaration.objects.filter(actor=actor, iscc_code=iscc_code)
    assert declarations.count() == 2
