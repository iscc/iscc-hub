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
