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


def test_validate_iscc_code_valid_composite():
    # type: () -> None
    """Test validates a valid composite ISCC code."""
    # Valid ISCC-CODE from spec examples
    iscc_code = "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA"
    validators.validate_iscc_code(iscc_code)  # Should not raise


def test_validate_iscc_code_invalid_format():
    # type: () -> None
    """Test raises ValueError for invalid ISCC format."""
    with pytest.raises(ValueError, match="Invalid ISCC code"):
        validators.validate_iscc_code("ISCC:INVALID")


def test_validate_iscc_code_non_composite():
    # type: () -> None
    """Test raises ValueError for non-composite ISCC (not MainType ISCC)."""
    # Valid Meta-Code unit but not a composite ISCC-CODE
    meta_code = "ISCC:AADZH265WE3KJOSR5K67QJEF5JHLF2REJJYVI4ZYKJ727JU2ZX2AHNQ"
    with pytest.raises(ValueError, match="ISCC code must be of MainType ISCC"):
        validators.validate_iscc_code(meta_code)


def test_validate_nonce_valid():
    # type: () -> None
    """Test validates a valid 128-bit hex nonce."""
    nonce = "000faa3f18c7b9407a48536a9b00c4cb"  # 32 hex chars = 128 bits
    validators.validate_nonce(nonce)  # Should not raise


def test_validate_nonce_not_string():
    # type: () -> None
    """Test raises ValueError when nonce is not a string."""
    with pytest.raises(ValueError, match="nonce must be a string"):
        validators.validate_nonce(12345)


def test_validate_nonce_uppercase():
    # type: () -> None
    """Test raises ValueError for uppercase hex characters."""
    # NOTE: OpenAPI pattern allows uppercase but implementation requires lowercase
    nonce = "000FAA3F18C7B9407A48536A9B00C4CB"
    with pytest.raises(ValueError, match="nonce must be lowercase"):
        validators.validate_nonce(nonce)


def test_validate_nonce_wrong_length():
    # type: () -> None
    """Test raises ValueError for incorrect nonce length."""
    with pytest.raises(ValueError, match="nonce must be exactly 32 characters"):
        validators.validate_nonce("000faa3f18c7b9407a48536a9b00c4")  # 31 chars


def test_validate_nonce_invalid_hex():
    # type: () -> None
    """Test raises ValueError for non-hex characters."""
    nonce = "000faa3f18c7b9407a48536a9b00c4xz"  # 'xz' are not hex
    with pytest.raises(ValueError, match="nonce must contain only hexadecimal characters"):
        validators.validate_nonce(nonce)


def test_validate_nonce_with_hub_id_match():
    # type: () -> None
    """Test validates nonce with matching hub ID."""
    # First 12 bits: 0x000 = hub_id 0
    nonce = "000faa3f18c7b9407a48536a9b00c4cb"
    validators.validate_nonce(nonce, hub_id=0)  # Should not raise


def test_validate_nonce_with_hub_id_mismatch():
    # type: () -> None
    """Test raises ValueError when hub ID doesn't match nonce."""
    # First 12 bits: 0x000 = hub_id 0, but we expect 15
    nonce = "000faa3f18c7b9407a48536a9b00c4cb"
    with pytest.raises(ValueError, match="Nonce hub_id mismatch: expected 15, got 0"):
        validators.validate_nonce(nonce, hub_id=15)


def test_validate_nonce_hub_id_extraction():
    # type: () -> None
    """Test correct extraction of hub ID from nonce."""
    # 0xfff = 4095 (max hub_id)
    nonce = "fffaaa3f18c7b9407a48536a9b00c4cb"
    validators.validate_nonce(nonce, hub_id=4095)  # Should not raise

    # 0x123 = 291
    nonce = "123aaa3f18c7b9407a48536a9b00c4cb"
    validators.validate_nonce(nonce, hub_id=291)  # Should not raise
