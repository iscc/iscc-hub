"""Test Pydantic schema validation including extra field rejection."""

import pytest
from pydantic import ValidationError

from iscc_hub.schema import IsccNote, IsccSignature


def test_schema_rejects_extra_fields(minimal_iscc_note):
    # type: (dict) -> None
    """Test that IsccNote schema rejects unknown fields."""
    minimal_iscc_note["unknown_field"] = "should_cause_error"

    with pytest.raises(ValidationError) as exc_info:
        IsccNote(**minimal_iscc_note)

    errors = exc_info.value.errors()
    assert any(e["type"] == "extra_forbidden" for e in errors)
    assert any("unknown_field" in str(e) for e in errors)


def test_signature_rejects_extra_fields():
    # type: () -> None
    """Test that IsccSignature schema rejects unknown fields."""
    signature_data = {
        "version": "ISCC-SIG v1.0",
        "pubkey": "z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "proof": "z3J8R9nYkqYJyYqzJKXk5KsyJqzJKXk5KsyJqzJKXk5KsyJqzJKXk5Ksy",
        "extra_field": "should_not_be_allowed",
    }

    with pytest.raises(ValidationError) as exc_info:
        IsccSignature(**signature_data)

    errors = exc_info.value.errors()
    assert any(e["type"] == "extra_forbidden" for e in errors)


def test_nested_signature_extra_fields_rejected(minimal_iscc_note):
    # type: (dict) -> None
    """Test that extra fields in nested signature are rejected."""
    minimal_iscc_note["signature"]["unknown_sig_field"] = "should_cause_error"

    with pytest.raises(ValidationError) as exc_info:
        IsccNote(**minimal_iscc_note)

    errors = exc_info.value.errors()
    assert any(e["type"] == "extra_forbidden" for e in errors)
    assert any("unknown_sig_field" in str(e) for e in errors)


def test_schema_accepts_all_valid_fields(full_iscc_note):
    # type: (dict) -> None
    """Test that all known fields are accepted by the schema."""
    # Should not raise any exception
    iscc_note = IsccNote(**full_iscc_note)
    assert iscc_note.iscc_code == full_iscc_note["iscc_code"]
    assert iscc_note.gateway == full_iscc_note["gateway"]
    assert iscc_note.metahash == full_iscc_note["metahash"]
