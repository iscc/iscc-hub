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


def test_validate_nonce_hub_id_direct():
    # type: () -> None
    """Test validate_nonce_hub_id directly for edge cases."""
    # Test minimum hub_id (0)
    nonce = "000aaa3f18c7b9407a48536a9b00c4cb"
    validators.validate_nonce_hub_id(nonce, 0)  # Should not raise

    # Test maximum hub_id (4095 = 0xfff)
    nonce = "fffaaa3f18c7b9407a48536a9b00c4cb"
    validators.validate_nonce_hub_id(nonce, 4095)  # Should not raise

    # Test mismatch
    with pytest.raises(ValueError, match="Nonce hub_id mismatch: expected 100, got 0"):
        validators.validate_nonce_hub_id("000aaa3f18c7b9407a48536a9b00c4cb", 100)


def test_validate_timestamp_valid():
    # type: () -> None
    """Test validates a valid RFC 3339 timestamp with milliseconds."""
    # Valid timestamp with millisecond precision
    validators.validate_timestamp("2025-08-04T12:34:56.789Z", check_tolerance=False)


def test_validate_timestamp_not_string():
    # type: () -> None
    """Test raises ValueError when timestamp is not a string."""
    with pytest.raises(ValueError, match="timestamp must be a string"):
        validators.validate_timestamp(12345)


def test_validate_timestamp_missing_z():
    # type: () -> None
    """Test raises ValueError when timestamp doesn't end with Z."""
    with pytest.raises(ValueError, match="timestamp must end with 'Z' to indicate UTC"):
        validators.validate_timestamp("2025-08-04T12:34:56.789")


def test_validate_timestamp_missing_milliseconds():
    # type: () -> None
    """Test raises ValueError when timestamp lacks millisecond precision."""
    with pytest.raises(ValueError, match="timestamp must include millisecond precision"):
        validators.validate_timestamp("2025-08-04T12:34:56Z")


def test_validate_timestamp_wrong_millisecond_digits():
    # type: () -> None
    """Test raises ValueError for wrong number of millisecond digits."""
    # Too many digits
    with pytest.raises(ValueError, match="timestamp must have exactly 3 digits for milliseconds"):
        validators.validate_timestamp("2025-08-04T12:34:56.1234Z")

    # Too few digits
    with pytest.raises(ValueError, match="timestamp must have exactly 3 digits for milliseconds"):
        validators.validate_timestamp("2025-08-04T12:34:56.12Z")


def test_validate_timestamp_invalid_format():
    # type: () -> None
    """Test raises ValueError for invalid timestamp format."""
    # Invalid format but ends with Z and has a dot
    with pytest.raises(ValueError, match="timestamp must be RFC 3339 formatted"):
        validators.validate_timestamp("not-a-valid.123Z")


def test_validate_timestamp_non_utc():
    # type: () -> None
    """Test raises ValueError for non-UTC timezone."""
    # With timezone offset instead of Z
    with pytest.raises(ValueError, match="timestamp must end with 'Z' to indicate UTC"):
        validators.validate_timestamp("2025-08-04T12:34:56.789+01:00")


def test_validate_timestamp_within_tolerance():
    # type: () -> None
    """Test timestamp within ±10 minute tolerance."""
    ref_time = datetime(2025, 8, 4, 12, 30, 0, tzinfo=UTC)

    # 5 minutes in the future - should pass
    validators.validate_timestamp("2025-08-04T12:35:00.000Z", reference_time=ref_time)

    # 5 minutes in the past - should pass
    validators.validate_timestamp("2025-08-04T12:25:00.000Z", reference_time=ref_time)

    # Exactly at tolerance boundary (10 minutes) - should pass
    validators.validate_timestamp("2025-08-04T12:40:00.000Z", reference_time=ref_time)
    validators.validate_timestamp("2025-08-04T12:20:00.000Z", reference_time=ref_time)


def test_validate_timestamp_outside_tolerance():
    # type: () -> None
    """Test raises ValueError when timestamp is outside ±10 minute tolerance."""
    ref_time = datetime(2025, 8, 4, 12, 30, 0, tzinfo=UTC)

    # 11 minutes in the future
    with pytest.raises(ValueError, match="timestamp is outside ±10 minute tolerance: 11.0 minutes"):
        validators.validate_timestamp("2025-08-04T12:41:00.000Z", reference_time=ref_time)

    # 11 minutes in the past
    with pytest.raises(ValueError, match="timestamp is outside ±10 minute tolerance: 11.0 minutes"):
        validators.validate_timestamp("2025-08-04T12:19:00.000Z", reference_time=ref_time)


def test_validate_timestamp_skip_tolerance_check():
    # type: () -> None
    """Test skipping tolerance check allows any valid timestamp."""
    ref_time = datetime(2025, 8, 4, 12, 30, 0, tzinfo=UTC)

    # 1 hour in the future - would fail with tolerance check
    validators.validate_timestamp("2025-08-04T13:30:00.000Z", check_tolerance=False, reference_time=ref_time)

    # 1 year in the past - would fail with tolerance check
    validators.validate_timestamp("2024-08-04T12:30:00.000Z", check_tolerance=False, reference_time=ref_time)


def test_validate_timestamp_with_current_time():
    # type: () -> None
    """Test validation with current time when no reference provided."""
    # Create a timestamp that's definitely within tolerance of now
    current_time = datetime.now(UTC)
    timestamp_str = current_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # Should pass with default reference_time (current time)
    validators.validate_timestamp(timestamp_str, check_tolerance=True)
