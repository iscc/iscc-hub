"""
Test fixture loading functionality.
"""

import iscc_crypto as icr
import pytest
from django.core.management import call_command
from django.db.models import Q

from iscc_hub.models import Event, IsccDeclaration, LogRecord, LogState
from iscc_hub.sequencer import sequence_iscc_note
from tests.conftest import create_iscc_from_text


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
        assert declaration.pubkey is not None
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


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_fixture_seeds_log_models_and_allows_next_declaration():
    # type: () -> None
    """The fixture seeds LogState/LogRecord so the dual-write continues without a seq collision.

    Regression guard for the missing log-model fixtures: without LogState/LogRecord, a fresh
    LogState would mint event_seq=1 and collide with the fixture's legacy Event seq=1, and the
    LogRecord-based dedup/receipt/delete paths would not see the fixture declarations.
    """
    call_command("loaddata", "test_data")

    # The log models were dumped and are consistent with the legacy Event log.
    state = LogState.objects.get()
    assert state.tree_size == LogRecord.objects.count() == Event.objects.count()

    # The next declaration continues from the loaded counter (no seq collision with fixture Events).
    data = create_iscc_from_text("fixture-continuation")
    note = {
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": "2025-01-15T12:00:00.000Z",
    }
    signed = icr.sign_json(note, icr.key_generate())
    seq, _ = sequence_iscc_note(signed)
    # 0-based: the next leaf index equals the loaded tree_size; the dual-written Event.seq
    # (tree_size + 1) does not collide with the fixture's existing Event rows.
    assert seq == state.tree_size
    assert LogRecord.objects.count() == state.tree_size + 1
