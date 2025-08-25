"""
Test fixture loading functionality.
"""

import pytest
from django.core.management import call_command
from django.db.models import Q

from iscc_hub.models import Event, IsccDeclaration


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_load_fixtures_command():
    # type: () -> None
    """
    Test that the loaddata command works with test_data fixture.
    """
    # Load the fixture
    call_command("loaddata", "test_data")

    # Verify Event data was loaded
    events = Event.objects.all()
    assert events.count() > 0, "No Event records loaded from fixture"

    # Verify IsccDeclaration data was loaded
    declarations = IsccDeclaration.objects.all()
    assert declarations.count() > 0, "No IsccDeclaration records loaded from fixture"

    # Check that Event records have valid data
    for event in events:
        assert event.seq is not None
        assert event.iscc_id is not None
        assert event.event_type in [1, 2, 3]
        assert event.event_data is not None

    # Check that IsccDeclaration records have valid data
    for declaration in declarations:
        assert declaration.iscc_id is not None
        assert declaration.event_seq is not None
        assert declaration.iscc_code is not None
        assert declaration.datahash is not None
        assert declaration.nonce is not None
        assert declaration.actor is not None
        # Timestamps are now implicit in the ISCC-ID, so just check updated_at
        assert declaration.updated_at is not None


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_fixture_data_relationships():
    # type: () -> None
    """
    Test that fixture data maintains proper relationships.
    """
    # Load the fixture
    call_command("loaddata", "test_data")

    # Check that each IsccDeclaration has a corresponding Event
    declarations = IsccDeclaration.objects.all()
    for declaration in declarations:
        # Should have at least one event with this ISCC-ID
        events = Event.objects.filter(iscc_id=declaration.iscc_id)
        assert events.exists(), f"No Event found for IsccDeclaration {declaration.iscc_id}"

        # Check event_seq references
        event = Event.objects.filter(seq=declaration.event_seq).first()
        error_msg = f"No Event with seq={declaration.event_seq} for IsccDeclaration {declaration.iscc_id}"
        assert event is not None, error_msg
