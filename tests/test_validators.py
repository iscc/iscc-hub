"""Comprehensive tests for iscc_hub.validators module."""

from datetime import UTC, datetime, timedelta

import pytest

from iscc_hub import validators


def test_validate_required_fields_all_present():
    # type: () -> None
    """Test passes when all required fields present."""
    data = {
        "iscc_code": "value",
        "datahash": "value",
        "nonce": "value",
        "timestamp": "value",
        "signature": "value",
    }
    validators.validate_required_fields(data)  # Should not raise


def test_validate_required_fields_missing():
    # type: () -> None
    """Test raises ValueError for each missing required field."""
    required = ["iscc_code", "datahash", "nonce", "timestamp", "signature"]
    for field in required:
        data = {f: "value" for f in required if f != field}
        with pytest.raises(ValueError, match=f"Missing required field: {field}"):
            validators.validate_required_fields(data)


def test_validate_required_fields_empty():
    # type: () -> None
    """Test raises ValueError for empty dictionary."""
    with pytest.raises(ValueError, match="Missing required field:"):
        validators.validate_required_fields({})


def test_validate_required_fields_extra_ignored():
    # type: () -> None
    """Test extra fields don't affect validation."""
    data = {
        "iscc_code": "value",
        "datahash": "value",
        "nonce": "value",
        "timestamp": "value",
        "signature": "value",
        "extra": "ignored",
    }
    validators.validate_required_fields(data)  # Should not raise
