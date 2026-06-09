"""
Test fixture loading functionality.
"""

import iscc_crypto as icr
import pytest
from django.core.management import call_command

from iscc_hub.iscc_id import IsccID
from iscc_hub.models import IsccDeclaration, LogRecord, LogState
from iscc_hub.sequencer import sequence_iscc_note
from tests.conftest import create_iscc_from_text


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_load_fixtures_command():
    # type: () -> None
    """
    Test that the loaddata command works with the test_data fixture.
    """
    call_command("loaddata", "test_data")

    # Verify LogRecord data was loaded.
    records = LogRecord.objects.all()
    assert records.count() > 0, "No LogRecord rows loaded from fixture"

    # Verify IsccDeclaration data was loaded.
    declarations = IsccDeclaration.objects.all()
    assert declarations.count() > 0, "No IsccDeclaration records loaded from fixture"

    # Each LogRecord carries valid append-only data.
    for record in records:
        assert record.index is not None
        assert record.iscc_id is not None
        assert record.type in {LogRecord.RecordType.DECLARATION, LogRecord.RecordType.DELETION}
        assert bytes(record.record)

    # Each IsccDeclaration record carries valid current-state data.
    for declaration in declarations:
        assert declaration.iscc_id is not None
        assert declaration.iscc_code is not None
        assert declaration.datahash is not None
        assert declaration.nonce is not None
        assert declaration.pubkey is not None
        # Timestamps are implicit in the ISCC-ID, so just check updated_at.
        assert declaration.updated_at is not None


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_fixture_data_relationships():
    # type: () -> None
    """
    Test that each active declaration has a backing declaration record in the log.
    """
    call_command("loaddata", "test_data")

    for declaration in IsccDeclaration.objects.all():
        record = LogRecord.objects.filter(
            iscc_id=bytes(IsccID(declaration.iscc_id)),
            type=LogRecord.RecordType.DECLARATION,
        ).first()
        assert record is not None, f"No declaration LogRecord for IsccDeclaration {declaration.iscc_id}"


@pytest.mark.django_db(transaction=True, reset_sequences=True)
def test_fixture_seeds_log_models_and_allows_next_declaration():
    # type: () -> None
    """The fixture seeds LogState/LogRecord so the next declaration continues gaplessly."""
    call_command("loaddata", "test_data")

    # The counter is consistent with the loaded append-only log.
    state = LogState.objects.get()
    assert state.tree_size == LogRecord.objects.count()

    # The next declaration continues from the loaded counter (no index collision).
    data = create_iscc_from_text("fixture-continuation")
    note = {
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": "2025-01-15T12:00:00.000Z",
    }
    signed = icr.sign_json(note, icr.key_generate())
    seq, _ = sequence_iscc_note(signed)
    # 0-based: the next leaf index equals the loaded tree_size.
    assert seq == state.tree_size
    assert LogRecord.objects.count() == state.tree_size + 1
