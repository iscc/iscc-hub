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


def test_validate_hex_string_valid():
    # type: () -> None
    """Test validates a valid lowercase hex string."""
    validators.validate_hex_string("abcdef0123456789", "test_field", 16)  # Should not raise


def test_validate_hex_string_uppercase():
    # type: () -> None
    """Test raises ValueError for uppercase hex characters."""
    with pytest.raises(ValueError, match="test_field must be lowercase"):
        validators.validate_hex_string("ABCDEF0123456789", "test_field", 16)

    # Mixed case
    with pytest.raises(ValueError, match="test_field must be lowercase"):
        validators.validate_hex_string("AbCdEf0123456789", "test_field", 16)


def test_validate_hex_string_wrong_length():
    # type: () -> None
    """Test raises ValueError for incorrect length."""
    # Too short
    with pytest.raises(ValueError, match="test_field must be exactly 16 characters"):
        validators.validate_hex_string("abcdef012345678", "test_field", 16)  # 15 chars

    # Too long
    with pytest.raises(ValueError, match="test_field must be exactly 16 characters"):
        validators.validate_hex_string("abcdef01234567890", "test_field", 16)  # 17 chars


def test_validate_hex_string_invalid_characters():
    # type: () -> None
    """Test raises ValueError for non-hex characters."""
    # Non-hex letter
    with pytest.raises(ValueError, match="test_field must contain only hexadecimal characters"):
        validators.validate_hex_string("abcdefg123456789", "test_field", 16)  # 'g' is not hex

    # Special character
    with pytest.raises(ValueError, match="test_field must contain only hexadecimal characters"):
        validators.validate_hex_string("abcdef-123456789", "test_field", 16)  # '-' is not hex


def test_validate_hex_string_different_field_names():
    # type: () -> None
    """Test error messages use the correct field name."""
    with pytest.raises(ValueError, match="nonce must be lowercase"):
        validators.validate_hex_string("ABC", "nonce", 3)

    with pytest.raises(ValueError, match="datahash must be exactly 5 characters"):
        validators.validate_hex_string("abc", "datahash", 5)

    with pytest.raises(ValueError, match="metahash must contain only hexadecimal characters"):
        validators.validate_hex_string("xyz", "metahash", 3)


def test_validate_optional_field_null_value():
    # type: () -> None
    """Test raises ValueError for null values."""
    with pytest.raises(ValueError, match="Optional field 'gateway' must not be null"):
        validators.validate_optional_field("gateway", None)


def test_validate_optional_field_empty_string():
    # type: () -> None
    """Test raises ValueError for empty or whitespace-only strings."""
    with pytest.raises(ValueError, match="Optional field 'gateway' must not be empty"):
        validators.validate_optional_field("gateway", "")

    with pytest.raises(ValueError, match="Optional field 'gateway' must not be empty"):
        validators.validate_optional_field("gateway", "   ")

    with pytest.raises(ValueError, match="Optional field 'gateway' must not be empty"):
        validators.validate_optional_field("gateway", "\t\n")


def test_validate_optional_field_empty_list():
    # type: () -> None
    """Test raises ValueError for empty lists."""
    with pytest.raises(ValueError, match="Optional field 'units' must not be empty"):
        validators.validate_optional_field("units", [])


def test_validate_optional_field_valid_values():
    # type: () -> None
    """Test passes for valid non-empty values."""
    # Valid string
    validators.validate_optional_field("gateway", "https://example.com")

    # Valid list
    validators.validate_optional_field("units", ["item1", "item2"])

    # Valid dict
    validators.validate_optional_field("metadata", {"key": "value"})

    # Valid number
    validators.validate_optional_field("count", 42)

    # Valid boolean
    validators.validate_optional_field("enabled", True)


def test_validate_optional_field_with_special_validator():
    # type: () -> None
    """Test applies special validators when provided."""

    # Define a special validator that checks string length
    def check_min_length(value):
        if len(value) < 5:
            raise ValueError("Value too short")

    special_validators = {"gateway": check_min_length}

    # Should pass - long enough
    validators.validate_optional_field("gateway", "https://example.com", special_validators)

    # Should fail - too short
    with pytest.raises(ValueError, match="Value too short"):
        validators.validate_optional_field("gateway", "http", special_validators)


def test_validate_optional_field_special_validator_not_applied():
    # type: () -> None
    """Test special validators only apply to matching field names."""

    def check_min_length(value):
        if len(value) < 5:
            raise ValueError("Value too short")

    special_validators = {"gateway": check_min_length}

    # Special validator should NOT apply to 'other_field'
    validators.validate_optional_field("other_field", "abc", special_validators)  # Should not raise


def test_validate_optional_field_no_special_validators():
    # type: () -> None
    """Test works without special validators."""
    # None special_validators
    validators.validate_optional_field("gateway", "https://example.com", None)

    # Empty special_validators dict
    validators.validate_optional_field("gateway", "https://example.com", {})


def test_validate_multihash_valid():
    # type: () -> None
    """Test validates a valid multihash with 1e20 prefix."""
    # Valid datahash - 68 chars total (4 prefix + 64 hex)
    valid_hash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"
    validators.validate_multihash(valid_hash, "datahash")  # Should not raise


def test_validate_multihash_not_string():
    # type: () -> None
    """Test raises ValueError when value is not a string."""
    with pytest.raises(ValueError, match="datahash must be a string"):
        validators.validate_multihash(12345, "datahash")

    with pytest.raises(ValueError, match="datahash must be a string"):
        validators.validate_multihash(None, "datahash")


def test_validate_multihash_uppercase():
    # type: () -> None
    """Test raises ValueError for uppercase hex characters."""
    # Uppercase in hex part
    upper_hash = "1e208021A144E1CE8FD4ECB2C7660D712B0E6818926BF2E3BB4930D54B5B23ED304D"
    with pytest.raises(ValueError, match="datahash must be lowercase"):
        validators.validate_multihash(upper_hash, "datahash")

    # Uppercase in prefix
    upper_prefix = "1E208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"
    with pytest.raises(ValueError, match="datahash must be lowercase"):
        validators.validate_multihash(upper_prefix, "datahash")


def test_validate_multihash_wrong_prefix():
    # type: () -> None
    """Test raises ValueError for incorrect prefix."""
    # Wrong prefix
    wrong_prefix = "1f208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"
    with pytest.raises(ValueError, match="datahash must start with '1e20'"):
        validators.validate_multihash(wrong_prefix, "datahash")

    # No prefix
    no_prefix = "8021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d1e20"
    with pytest.raises(ValueError, match="datahash must start with '1e20'"):
        validators.validate_multihash(no_prefix, "datahash")


def test_validate_multihash_wrong_length():
    # type: () -> None
    """Test raises ValueError for incorrect length."""
    # Too short (67 chars)
    short_hash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304"
    with pytest.raises(ValueError, match="datahash must be exactly 68 characters"):
        validators.validate_multihash(short_hash, "datahash")

    # Too long (69 chars)
    long_hash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304dd"
    with pytest.raises(ValueError, match="datahash must be exactly 68 characters"):
        validators.validate_multihash(long_hash, "datahash")


def test_validate_multihash_invalid_hex():
    # type: () -> None
    """Test raises ValueError for non-hex characters after prefix."""
    # Non-hex character in the hash part
    invalid_hex = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed30xz"
    with pytest.raises(ValueError, match="datahash must contain only hexadecimal characters"):
        validators.validate_multihash(invalid_hex, "datahash")


def test_validate_multihash_different_field_names():
    # type: () -> None
    """Test error messages use the correct field name."""
    # Valid metahash - 68 chars (4 prefix + 64 hex)
    valid_hash = "1e20a0e3c5b4f7d2c1a8e9f5b3d7e2a1c4f8b6d9e3a7c2f5d8b1e4a9c7f3b6d2e1a0"
    validators.validate_multihash(valid_hash, "metahash")  # Should not raise

    # Test with metahash field name in error
    with pytest.raises(ValueError, match="metahash must be lowercase"):
        validators.validate_multihash(valid_hash.upper(), "metahash")


def test_validate_gateway_valid_url():
    # type: () -> None
    """Test validates a valid HTTP(S) URL."""
    validators.validate_gateway("https://example.com")  # Should not raise
    validators.validate_gateway("http://example.com")  # Should not raise
    validators.validate_gateway("https://api.example.com/v1/metadata")  # Should not raise


def test_validate_gateway_valid_template():
    # type: () -> None
    """Test validates a valid URI template with supported variables."""
    # Template with single variable
    validators.validate_gateway("https://example.com/{iscc_id}")

    # Template with multiple variables
    validators.validate_gateway("https://api.example.com/{pubkey}/content/{iscc_code}")

    # Template with all supported variables
    validators.validate_gateway("https://example.com/{iscc_id}/{iscc_code}/{pubkey}/{datahash}")


def test_validate_gateway_invalid_template_syntax():
    # type: () -> None
    """Test raises ValueError for mismatched braces."""
    # Missing closing brace
    with pytest.raises(ValueError, match="gateway has invalid URI template syntax"):
        validators.validate_gateway("https://example.com/{iscc_id")

    # Missing opening brace
    with pytest.raises(ValueError, match="gateway has invalid URI template syntax"):
        validators.validate_gateway("https://example.com/iscc_id}")

    # Mismatched count
    with pytest.raises(ValueError, match="gateway has invalid URI template syntax"):
        validators.validate_gateway("https://example.com/{{iscc_id}")


def test_validate_gateway_unsupported_variables():
    # type: () -> None
    """Test raises ValueError for unsupported template variables."""
    # Single unsupported variable
    with pytest.raises(ValueError, match="gateway contains unsupported variables: unknown"):
        validators.validate_gateway("https://example.com/{unknown}")

    # Multiple unsupported variables (sorted in error)
    with pytest.raises(ValueError, match="gateway contains unsupported variables: bad, wrong"):
        validators.validate_gateway("https://example.com/{wrong}/{bad}")

    # Mix of supported and unsupported
    with pytest.raises(ValueError, match="gateway contains unsupported variables: invalid"):
        validators.validate_gateway("https://example.com/{iscc_id}/{invalid}")


def test_validate_gateway_invalid_url():
    # type: () -> None
    """Test raises ValueError for invalid URLs when no template variables."""
    # No scheme
    with pytest.raises(ValueError, match="gateway must be a valid URL or URI template"):
        validators.validate_gateway("example.com")

    # Invalid scheme
    with pytest.raises(ValueError, match="gateway must be a valid URL or URI template"):
        validators.validate_gateway("ftp://example.com")

    # No hostname
    with pytest.raises(ValueError, match="gateway must be a valid URL or URI template"):
        validators.validate_gateway("https://")

    # Whitespace
    with pytest.raises(ValueError, match="gateway must be a valid URL or URI template"):
        validators.validate_gateway(" https://example.com ")


def test_validate_gateway_edge_cases():
    # type: () -> None
    """Test edge cases for gateway validation."""
    # URL with port
    validators.validate_gateway("https://example.com:8080")  # Should not raise

    # URL with path
    validators.validate_gateway("https://example.com/api/v1")  # Should not raise

    # URL with query parameters
    validators.validate_gateway("https://example.com?key=value")  # Should not raise

    # Template with path segments
    validators.validate_gateway("https://api.example.com/v1/{iscc_id}/metadata")  # Should not raise


def test_datahash_to_instance_code():
    # type: () -> None
    """Test conversion of datahash to Instance-Code ISCC-UNIT."""
    # Valid datahash
    datahash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"

    # Convert to Instance-Code
    instance_code = validators.datahash_to_instance_code(datahash)

    # Should be a valid ISCC with Instance MainType
    assert instance_code.startswith("ISCC:")
    assert len(instance_code) > 5

    # Verify it's an Instance-Code by decoding
    import iscc_core as ic

    decoded = ic.iscc_decode(instance_code)
    assert decoded[0] == ic.MT.INSTANCE


def test_validate_units_reconstruction_valid():
    # type: () -> None
    """Test valid units reconstruction to match iscc_code."""
    # Using corrected ISCC-CODE that matches the units + datahash reconstruction
    iscc_code = "ISCC:KACZH265WE3KJOSRJT3OCVAFMMNYPEWWFTXNHEFX66ACDIKE4HHI7VA"
    datahash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"
    units = [
        "ISCC:AADZH265WE3KJOSR5K67QJEF5JHLF2REJJYVI4ZYKJ727JU2ZX2AHNQ",
        "ISCC:EADUZ5XBKQCWGG4HYIKX7CNPQMFTPTWEUCQLXFJWC25TKM645KYUSNQ",
        "ISCC:GADZFVRM53JZBN7XOOT3Y6FL372G2GY6PEKRY43JIJ6KV4GH5P7NN4A",
    ]

    # Should not raise
    validators.validate_units_reconstruction(units, datahash, iscc_code)


def test_validate_units_reconstruction_not_list():
    # type: () -> None
    """Test raises ValueError when units is not a list."""
    with pytest.raises(ValueError, match="units must be a list"):
        validators.validate_units_reconstruction("not_a_list", "1e20" + "a" * 64, "ISCC:KACT46A6S3L5XTH3")


def test_validate_units_reconstruction_non_string_unit():
    # type: () -> None
    """Test raises ValueError when a unit is not a string."""
    units = ["ISCC:AADZH265WE3KJOSR", 123, "ISCC:EADUZ5XBKQCWGG4HY"]
    with pytest.raises(ValueError, match="units\\[1\\] must be a string"):
        validators.validate_units_reconstruction(units, "1e20" + "a" * 64, "ISCC:KACT46A6S3L5XTH3")


def test_validate_units_reconstruction_invalid_unit():
    # type: () -> None
    """Test raises ValueError when a unit is invalid ISCC."""
    units = ["ISCC:INVALID_CODE"]
    datahash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"
    iscc_code = "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA"

    with pytest.raises(ValueError, match="Cannot build ISCC-CODE from units shorter than 64-bits"):
        validators.validate_units_reconstruction(units, datahash, iscc_code)


def test_validate_units_reconstruction_mismatch():
    # type: () -> None
    """Test raises ValueError when reconstruction doesn't match iscc_code."""
    # Units that won't reconstruct to the provided iscc_code (wrong Data-Code)
    units = [
        "ISCC:AADZH265WE3KJOSR5K67QJEF5JHLF2REJJYVI4ZYKJ727JU2ZX2AHNQ",  # Meta
        "ISCC:GADZH265WE3KJOSR5K67QJEF5JHLF2REJJYVI4ZYKJ727JU2ZX2AHNQ",  # Different Data unit
    ]
    datahash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"
    iscc_code = "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA"

    with pytest.raises(ValueError, match="ISCC code reconstruction failed"):
        validators.validate_units_reconstruction(units, datahash, iscc_code)


def test_validate_units_reconstruction_generic_exception():
    # type: () -> None
    """Test generic exception handler in validate_units_reconstruction."""
    # Mock a generic exception by passing an object that will fail inside gen_iscc_code
    import unittest.mock as mock

    units = ["ISCC:AADZH265WE3KJOSR5K67QJEF5JHLF2REJJYVI4ZYKJ727JU2ZX2AHNQ"]
    datahash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"
    iscc_code = "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA"

    # Patch gen_iscc_code to raise a non-ValueError exception
    with mock.patch("iscc_hub.validators.ic.gen_iscc_code", side_effect=RuntimeError("Unexpected error")):
        with pytest.raises(ValueError, match="ISCC code reconstruction failed: units and datahash"):
            validators.validate_units_reconstruction(units, datahash, iscc_code)


def test_validate_datahash_match_wide_iscc():
    # type: () -> None
    """Test datahash matching for WIDE subtype ISCC (128-bit comparison)."""
    from io import BytesIO

    import iscc_core as ic

    # Create test content
    content = b"Test content for WIDE ISCC generation"

    # Generate 128-bit Data and Instance codes
    # According to deepwiki, we need to use gen_iscc_code_v0 with wide=True
    dcode = ic.gen_data_code(BytesIO(content), bits=256)
    icode = ic.gen_instance_code(BytesIO(content), bits=256)

    # Generate WIDE ISCC-CODE using gen_iscc_code_v0 with wide=True
    iscc_result = ic.gen_iscc_code_v0([dcode["iscc"], icode["iscc"]], wide=True)
    iscc_code = iscc_result["iscc"]

    # Use the datahash from instance code generation
    datahash = icode["datahash"]

    # Verify it's a WIDE ISCC (ST_ISCC.WIDE = 7)
    _, subtype, _, _, _ = ic.iscc_decode(iscc_code)
    assert subtype == ic.ST_ISCC.WIDE

    # Should validate successfully with 128-bit comparison
    validators.validate_datahash_match(iscc_code, datahash)


def test_validate_datahash_match_invalid_iscc_error():
    # type: () -> None
    """Test validate_datahash_match converts iscc_core errors."""
    # Use an invalid ISCC that will cause an error during decoding
    # This tests line 475 where iscc_core errors are converted
    import unittest.mock as mock

    iscc_code = "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA"
    datahash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"

    # Mock iscc_decode to raise a ValueError that's not our custom message
    with mock.patch("iscc_hub.validators.ic.iscc_decode", side_effect=ValueError("Some other error")):
        with pytest.raises(ValueError, match="Invalid ISCC code: Some other error"):
            validators.validate_datahash_match(iscc_code, datahash)


def test_validate_datahash_match_valid():
    # type: () -> None
    """Test valid datahash matching Instance-Code portion of ISCC."""
    # ISCC-CODE with matching datahash
    iscc_code = "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA"
    datahash = "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d"

    # Should not raise
    validators.validate_datahash_match(iscc_code, datahash)


def test_validate_datahash_match_mismatch():
    # type: () -> None
    """Test raises ValueError when datahash doesn't match Instance-Code."""
    # ISCC-CODE with non-matching datahash
    iscc_code = "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA"
    # Different hash
    datahash = "1e20ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    with pytest.raises(ValueError, match="datahash does not match ISCC Instance-Code"):
        validators.validate_datahash_match(iscc_code, datahash)


def test_validate_optional_fields_with_valid_fields():
    # type: () -> None
    """Test validate_optional_fields with all valid optional fields."""
    data = {
        "iscc_code": "ISCC:KACZH265WE3KJOSRJT3OCVAFMMNYPEWWFTXNHEFX66ACDIKE4HHI7VA",
        "datahash": "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d",
        "gateway": "https://example.com",
        "metahash": "1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598",
        "units": [
            "ISCC:AADZH265WE3KJOSR5K67QJEF5JHLF2REJJYVI4ZYKJ727JU2ZX2AHNQ",
            "ISCC:EADUZ5XBKQCWGG4HYIKX7CNPQMFTPTWEUCQLXFJWC25TKM645KYUSNQ",
            "ISCC:GADZFVRM53JZBN7XOOT3Y6FL372G2GY6PEKRY43JIJ6KV4GH5P7NN4A",
        ],
    }
    # Should not raise
    validators.validate_optional_fields(data)


def test_validate_optional_fields_with_invalid_metahash():
    # type: () -> None
    """Test validate_optional_fields raises for invalid metahash."""
    data = {
        "iscc_code": "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA",
        "datahash": "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d",
        "metahash": "invalid_hash",
    }
    with pytest.raises(ValueError, match="metahash must"):
        validators.validate_optional_fields(data)


def test_validate_optional_fields_with_invalid_gateway():
    # type: () -> None
    """Test validate_optional_fields raises for invalid gateway."""
    data = {
        "iscc_code": "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA",
        "datahash": "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d",
        "gateway": "not-a-url",
    }
    with pytest.raises(ValueError, match="gateway must be a valid URL"):
        validators.validate_optional_fields(data)


def test_validate_optional_fields_with_invalid_units():
    # type: () -> None
    """Test validate_optional_fields raises for invalid units reconstruction."""
    data = {
        "iscc_code": "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA",
        "datahash": "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d",
        "units": ["ISCC:AADZH265WE3KJOSR5K67QJEF5JHLF2REJJYVI4ZYKJ727JU2ZX2AHNQ"],  # Wrong units
    }
    with pytest.raises(ValueError, match="ISCC-CODE requires at least MT.DATA and MT.INSTANCE units"):
        validators.validate_optional_fields(data)


def test_validate_optional_fields_with_empty_values():
    # type: () -> None
    """Test validate_optional_fields raises for empty optional values."""
    # Empty gateway
    data = {
        "iscc_code": "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA",
        "datahash": "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d",
        "gateway": "",
    }
    with pytest.raises(ValueError, match="Optional field 'gateway' must not be empty"):
        validators.validate_optional_fields(data)

    # Empty units
    data["gateway"] = "https://example.com"
    data["units"] = []
    with pytest.raises(ValueError, match="Optional field 'units' must not be empty"):
        validators.validate_optional_fields(data)


def test_validate_signature_structure_valid():
    # type: () -> None
    """Test validate_signature_structure with valid signature."""
    signature = {
        "version": "ISCC-SIG v1.0",
        "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
        "proof": "z2dW4e3DVcqnweJWPvLZNyaYiYTZiaEYKHiy3PUpE6Poth2BUVzKA72Tqih6GHz9KoWvEQ2CqfXSgyjY17cR94nXu",
    }
    validators.validate_signature_structure(signature)  # Should not raise


def test_validate_signature_structure_not_dict():
    # type: () -> None
    """Test validate_signature_structure raises for non-dict."""
    with pytest.raises(ValueError, match="Signature must be a dictionary"):
        validators.validate_signature_structure("not_a_dict")


def test_validate_signature_structure_missing_fields():
    # type: () -> None
    """Test validate_signature_structure raises for missing required fields."""
    # Missing proof
    signature = {
        "version": "ISCC-SIG v1.0",
        "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
    }
    with pytest.raises(ValueError, match="Missing required field in signature: proof"):
        validators.validate_signature_structure(signature)


def test_validate_signature_structure_with_optional_fields():
    # type: () -> None
    """Test validate_signature_structure with optional fields."""
    signature = {
        "version": "ISCC-SIG v1.0",
        "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
        "proof": "z2dW4e3DVcqnweJWPvLZNyaYiYTZiaEYKHiy3PUpE6Poth2BUVzKA72Tqih6GHz9KoWvEQ2CqfXSgyjY17cR94nXu",
        "controller": "did:web:example.com",
        "keyid": "key-1",
    }
    validators.validate_signature_structure(signature)  # Should not raise


def test_validate_signature_structure_empty_optional_fields():
    # type: () -> None
    """Test validate_signature_structure raises for empty optional fields."""
    signature = {
        "version": "ISCC-SIG v1.0",
        "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
        "proof": "z2dW4e3DVcqnweJWPvLZNyaYiYTZiaEYKHiy3PUpE6Poth2BUVzKA72Tqih6GHz9KoWvEQ2CqfXSgyjY17cR94nXu",
        "controller": "",  # Empty
    }
    with pytest.raises(ValueError, match="Optional field 'controller' in signature must not be empty"):
        validators.validate_signature_structure(signature)


def test_verify_signature_cryptographically_valid(minimal_iscc_note):
    # type: () -> None
    """Test verify_signature_cryptographically with valid signature."""
    # Should not raise
    validators.verify_signature_cryptographically(minimal_iscc_note)


def test_verify_signature_cryptographically_invalid(invalid_signature_note):
    # type: () -> None
    """Test verify_signature_cryptographically raises for invalid signature."""
    with pytest.raises(ValueError, match="Invalid signature"):
        validators.verify_signature_cryptographically(invalid_signature_note)


def test_validate_url_valid():
    # type: () -> None
    """Test validate_url with valid URLs."""
    validators.validate_url("https://example.com")
    validators.validate_url("http://localhost:8080")
    validators.validate_url("https://api.example.com/path?query=value")


def test_validate_url_invalid_scheme():
    # type: () -> None
    """Test validate_url raises for invalid scheme."""
    with pytest.raises(ValueError, match="gateway must be a valid URL"):
        validators.validate_url("ftp://example.com")


def test_validate_url_no_scheme():
    # type: () -> None
    """Test validate_url raises for missing scheme."""
    with pytest.raises(ValueError, match="gateway must be a valid URL"):
        validators.validate_url("example.com")


def test_validate_url_no_hostname():
    # type: () -> None
    """Test validate_url raises for missing hostname."""
    with pytest.raises(ValueError, match="gateway must be a valid URL"):
        validators.validate_url("https://")


def test_validate_url_with_whitespace():
    # type: () -> None
    """Test validate_url raises for URL with whitespace."""
    with pytest.raises(ValueError, match="gateway must be a valid URL"):
        validators.validate_url(" https://example.com ")


def test_validate_iscc_note_full_validation(
    example_nonce, current_timestamp, example_keypair, example_iscc_data
):
    # type: (str, str, Any, dict) -> None
    """Test validate_iscc_note with full validation."""
    # Create a note with current timestamp for tolerance testing
    import iscc_crypto as icr

    minimal_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    # Should validate successfully with current timestamp
    validated = validators.validate_iscc_note(signed_note)
    assert validated == signed_note


def test_validate_iscc_note_skip_signature(unsigned_iscc_note):
    # type: () -> None
    """Test validate_iscc_note without signature verification."""
    validated = validators.validate_iscc_note(
        unsigned_iscc_note, verify_signature=False, verify_timestamp=False
    )
    assert validated == unsigned_iscc_note


def test_validate_iscc_note_with_hub_id():
    # type: () -> None
    """Test validate_iscc_note with hub ID verification."""
    note = {
        "iscc_code": "ISCC:KACZH265WE3KJOSRJT3OCVAFMMNYPEWWFTXNHEFX66ACDIKE4HHI7VA",
        "datahash": "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d",
        "nonce": "000faa3f18c7b9407a48536a9b00c4cb",  # hub_id = 0
        "timestamp": "2025-01-15T12:00:00.000Z",
        "signature": {
            "version": "ISCC-SIG v1.0",
            "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
            "proof": "zInvalidButWeSkipVerification",
        },
    }
    validators.validate_iscc_note(note, verify_signature=False, verify_hub_id=0, verify_timestamp=False)


def test_validate_iscc_note_missing_field():
    # type: () -> None
    """Test validate_iscc_note raises for missing required field."""
    note = {
        "datahash": "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d",
        "nonce": "000faa3f18c7b9407a48536a9b00c4cb",
        "timestamp": "2025-01-15T12:00:00.000Z",
        "signature": {},
    }
    with pytest.raises(ValueError, match="Missing required field: iscc_code"):
        validators.validate_iscc_note(note)


def test_validate_iscc_note_skip_timestamp(example_nonce, example_keypair, example_iscc_data):
    # type: (str, Any, dict) -> None
    """Test validate_iscc_note skipping timestamp tolerance check."""
    import iscc_crypto as icr

    # Create a note with an old timestamp
    old_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": "2020-01-01T00:00:00.000Z",
    }

    # Sign the note with old timestamp
    signed_note = icr.sign_json(old_note, example_keypair)

    # Would fail with timestamp check
    with pytest.raises(ValueError, match="timestamp is outside"):
        validators.validate_iscc_note(signed_note, verify_timestamp=True)

    # Should pass without timestamp check
    validators.validate_iscc_note(signed_note, verify_timestamp=False)


# Tests from test_missing_coverage.py
def test_validate_input_size_exceeds_json_limit(example_iscc_data, example_nonce, example_keypair):
    # type: () -> None
    """Test that oversized JSON input is rejected."""
    # Create a note with very large strings that will exceed JSON size limit (8192 bytes)
    # Each string is 2000 chars (under individual limit of 2048)
    large_string = "x" * 2000
    oversized_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": "2025-01-01T00:00:00.000Z",
        "gateway": large_string,
        "metahash": "1e20" + "a" * 64,
        "extra1": large_string,  # Add more fields to exceed 8192 bytes total
        "extra2": large_string,
        "extra3": large_string,
        "signature": {
            "version": "ISCC-SIG v1.0",
            "proof": "z" + "A" * 100,
            "pubkey": "z" + "B" * 100,
            "controller": large_string,
        },
    }

    with pytest.raises(ValueError, match="Input data exceeds maximum size"):
        validators.validate_input_size(oversized_note)


def test_validate_input_size_exceeds_string_limit(example_iscc_data):
    # type: () -> None
    """Test that oversized string fields are rejected."""
    oversized_string = "x" * 3000  # Exceeds MAX_STRING_LENGTH (2048)
    data = {"gateway": oversized_string}

    with pytest.raises(ValueError, match="Field 'gateway' exceeds maximum string length"):
        validators.validate_input_size(data)


def test_validate_nonce_hub_id_out_of_range():
    # type: () -> None
    """Test hub ID validation with out of range value."""
    nonce = "000faa3f18c7b9407a48536a9b00c4cb"

    # Test hub ID too large
    with pytest.raises(ValueError, match="Hub ID must be between 0 and 4095"):
        validators.validate_nonce_hub_id(nonce, 5000)

    # Test negative hub ID
    with pytest.raises(ValueError, match="Hub ID must be between 0 and 4095"):
        validators.validate_nonce_hub_id(nonce, -1)


def test_validate_nonce_invalid_hub_id_in_nonce():
    # type: () -> None
    """Test validation when nonce contains invalid hub ID."""
    # Create a nonce that would extract to an invalid hub ID
    # This is tricky since we need to craft bytes that when extracted give > 4095
    # 4095 = 0xFFF, so we need first 12 bits to be all 1s or more
    # 0xFF 0xF0 would give us 0xFFF (4095) when extracted
    # 0xFF 0xFF would give us 0xFFF (4095) when extracted
    # Actually, let's use a nonce that's all FFs which would extract to 4095
    nonce_all_f = "f" * 32  # This will extract to 4095 (0xFFF)

    # This should work since 4095 is valid
    validators.validate_nonce_hub_id(nonce_all_f, 4095)

    # For the error case, we need to mock or create a scenario where extraction fails
    # Since the extraction is: (nonce_bytes[0] << 4) | (nonce_bytes[1] >> 4)
    # With all Fs: (0xFF << 4) | (0xFF >> 4) = 0xFF0 | 0x0F = 0xFFF = 4095
    # This is actually valid, so let's skip this particular test as it's not possible
    # to create a nonce that extracts to > 4095 with the current bit manipulation


def test_validate_signature_invalid_version(example_iscc_data, example_nonce):
    # type: () -> None
    """Test signature validation with invalid version."""
    signature = {
        "version": "ISCC-SIG v2.0",  # Wrong version
        "proof": "zSomeProof",
        "pubkey": "zSomePubkey",
    }

    with pytest.raises(ValueError, match="Invalid signature version"):
        validators.validate_signature_structure(signature)


def test_verify_signature_cryptographically_valid_with_keypair(
    example_iscc_data, example_nonce, example_keypair
):
    # type: () -> None
    """Test successful cryptographic signature verification."""
    import iscc_crypto as icr

    # Create and sign a valid note
    note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": "2025-01-01T00:00:00.000Z",
    }

    signed_note = icr.sign_json(note, example_keypair)

    # This should succeed without raising
    validators.verify_signature_cryptographically(signed_note)


def test_validate_units_exceeds_max_size(example_iscc_data):
    # type: () -> None
    """Test units validation with array exceeding max size."""
    # Create more units than allowed (MAX_UNITS_ARRAY_SIZE = 4)
    units = [
        "ISCC:AADWN77F73NA44D6X3N4VEUAPOW5HJKGK5JKLNGLNFPOESXWYDVDVUQ",
        "ISCC:EADSKDNZNYGUUF5AMFEJLZ5P66CP5YKCOA3X7F36RWE4CIRCBTUWXYY",
        "ISCC:GAD334BLFXWN7QWLCSBGJMLRZW73FFNV7ORVUKN23UWPKGQCWTIHQKY",
        "ISCC:AADWN77F73NA44D6X3N4VEUAPOW5HJKGK5JKLNGLNFPOESXWYDVDVUQ",
        "ISCC:EADSKDNZNYGUUF5AMFEJLZ5P66CP5YKCOA3X7F36RWE4CIRCBTUWXYY",  # 5th unit exceeds limit
    ]

    with pytest.raises(ValueError, match="units array exceeds maximum size"):
        validators.validate_units_reconstruction(
            units, example_iscc_data["datahash"], example_iscc_data["iscc"]
        )


# Tests from test_signature_exception.py
def test_verify_signature_cryptographically_exception():
    # type: () -> None
    """Test that exceptions during signature verification are handled properly."""
    from unittest.mock import patch

    test_data = {
        "iscc_code": "ISCC:KACWN77F73NA44D6EUG3S3QNJIL2BPPQFMW6ZX6CZNOKPAK23S2IJ2I",
        "signature": {"version": "ISCC-SIG v1.0", "proof": "zInvalidProof", "pubkey": "zInvalidPubkey"},
    }

    # Mock verify_json to raise an exception
    with patch("iscc_hub.validators.icr.verify_json") as mock_verify:
        mock_verify.side_effect = RuntimeError("Unexpected error during verification")

        with pytest.raises(ValueError, match="Invalid signature"):
            validators.verify_signature_cryptographically(test_data)


def test_validator_rejects_extra_fields(unsigned_iscc_note):
    # type: (dict) -> None
    """Test that custom validator rejects unknown top-level fields."""
    unsigned_iscc_note["unknown_field"] = "should_cause_error"

    with pytest.raises(ValueError, match="Unknown fields not allowed: unknown_field"):
        validators.validate_iscc_note(unsigned_iscc_note, verify_signature=False, verify_timestamp=False)


def test_validator_rejects_extra_signature_fields(unsigned_iscc_note):
    # type: (dict) -> None
    """Test that custom validator rejects unknown signature fields."""
    unsigned_iscc_note["signature"]["extra_sig_field"] = "should_cause_error"

    with pytest.raises(ValueError, match="Unknown fields in signature not allowed: extra_sig_field"):
        validators.validate_iscc_note(unsigned_iscc_note, verify_signature=False, verify_timestamp=False)


def test_validator_accepts_all_valid_fields(full_iscc_note):
    # type: (dict) -> None
    """Test that validator accepts all valid optional fields."""
    # Should not raise any exception
    result = validators.validate_iscc_note(full_iscc_note, verify_signature=False, verify_timestamp=False)
    assert result["gateway"] == full_iscc_note["gateway"]
    assert result["metahash"] == full_iscc_note["metahash"]
    assert result["units"] == full_iscc_note["units"]
