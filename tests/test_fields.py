"""
Tests for custom Django field implementations.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError
from django.forms import CharField

from iscc_hub.fields import HexField, IsccIDField, SequenceField
from iscc_hub.iscc_id import IsccID


# Parameterized tests for IsccIDField.to_python
@pytest.mark.parametrize(
    "input_value,expected_output,should_raise,error_code",
    [
        (None, None, False, None),
        ("", None, False, None),
        ("ISCC:MAIWGQRD43YZQUAA", "ISCC:MAIWGQRD43YZQUAA", False, None),
        ("INVALID:FORMAT", None, True, "invalid_iscc_format"),
        ("ISCC:INVALID", None, True, "invalid_iscc"),
        (b"SHORT", None, True, "invalid_length"),
        (12345, None, True, "invalid_type"),
    ],
)
def test_isccid_field_to_python_parameterized(input_value, expected_output, should_raise, error_code):
    # type: (str|bytes|int|None, str|None, bool, str|None) -> None
    """Parameterized test for IsccIDField.to_python method."""
    field = IsccIDField()

    if input_value is not None and isinstance(input_value, bytes) and len(input_value) == 8:
        # Special case for valid 8-byte input
        iscc_id = IsccID("ISCC:MAIWGQRD43YZQUAA")
        input_value = bytes(iscc_id)
        expected_output = "ISCC:MAIWGQRD43YZQUAA"
        should_raise = False
        error_code = None

    if should_raise:
        with pytest.raises(ValidationError) as exc_info:
            field.to_python(input_value)
        assert exc_info.value.code == error_code
    else:
        result = field.to_python(input_value)
        assert result == expected_output


# Parameterized tests for IsccIDField.get_prep_value
@pytest.mark.parametrize(
    "input_value,expected_type,should_raise,error_code",
    [
        (None, type(None), False, None),
        ("", type(None), False, None),
        ("ISCC:MAIWGQRD43YZQUAA", bytes, False, None),
        (b"TOOLONG!!", None, True, "invalid_length"),
        ("INVALID", None, True, None),
    ],
)
def test_isccid_field_get_prep_value_parameterized(input_value, expected_type, should_raise, error_code):
    # type: (str|bytes|None, type|None, bool, str|None) -> None
    """Parameterized test for IsccIDField.get_prep_value method."""
    field = IsccIDField()

    if should_raise:
        with pytest.raises(ValidationError) as exc_info:
            field.get_prep_value(input_value)
        if error_code:
            assert exc_info.value.code == error_code
    else:
        result = field.get_prep_value(input_value)
        if expected_type is type(None):
            assert result is None
        else:
            assert isinstance(result, expected_type)
            if expected_type is bytes:
                assert len(result) == 8


def test_sequence_field_description():
    # type: () -> None
    """Test that SequenceField has the correct description."""
    field = SequenceField()
    assert field.description == "Gap-less integer primary key"


def test_sequence_field_db_type():
    # type: () -> None
    """Test that db_type returns INTEGER for SQLite."""
    field = SequenceField()
    connection = MagicMock()
    assert field.db_type(connection) == "INTEGER"


def test_sequence_field_db_type_suffix():
    # type: () -> None
    """Test that db_type_suffix returns empty string instead of AUTOINCREMENT."""
    field = SequenceField()
    connection = MagicMock()
    assert field.db_type_suffix(connection) == ""


# Tests for IsccIDField
def test_isccid_field_init():
    # type: () -> None
    """Test IsccIDField initialization with default values."""
    field = IsccIDField()
    assert field.max_length == 8
    assert field.editable is False
    assert field.null is False
    assert field.blank is False
    assert field.description == "ISCC-ID stored as 8-byte binary"


def test_isccid_field_init_with_overrides():
    # type: () -> None
    """Test that certain parameters can be overridden if explicitly set."""
    field = IsccIDField(editable=True, null=True, blank=True)
    assert field.max_length == 8  # This is always fixed
    assert field.editable is True
    assert field.null is True
    assert field.blank is True


def test_isccid_field_to_python_none():
    # type: () -> None
    """Test to_python with None value."""
    field = IsccIDField()
    assert field.to_python(None) is None


def test_isccid_field_to_python_empty_string():
    # type: () -> None
    """Test to_python with empty string."""
    field = IsccIDField()
    assert field.to_python("") is None


def test_isccid_field_to_python_valid_string():
    # type: () -> None
    """Test to_python with valid ISCC-ID string."""
    field = IsccIDField()
    valid_iscc = "ISCC:MAIWGQRD43YZQUAA"
    result = field.to_python(valid_iscc)
    assert result == valid_iscc


def test_isccid_field_to_python_invalid_format():
    # type: () -> None
    """Test to_python with string not starting with ISCC:."""
    field = IsccIDField()
    with pytest.raises(ValidationError) as exc_info:
        field.to_python("INVALID:FORMAT")
    assert exc_info.value.code == "invalid_iscc_format"
    assert "Must start with 'ISCC:'" in str(exc_info.value)


def test_isccid_field_to_python_invalid_iscc():
    # type: () -> None
    """Test to_python with invalid ISCC-ID that can't be parsed."""
    field = IsccIDField()
    with pytest.raises(ValidationError) as exc_info:
        field.to_python("ISCC:INVALID")
    assert exc_info.value.code == "invalid_iscc"
    assert "Invalid ISCC-ID:" in str(exc_info.value)


def test_isccid_field_to_python_valid_bytes():
    # type: () -> None
    """Test to_python with valid 8-byte input."""
    field = IsccIDField()
    # Create a valid ISCC-ID and get its bytes representation
    iscc_id = IsccID("ISCC:MAIWGQRD43YZQUAA")
    bytes_value = bytes(iscc_id)
    result = field.to_python(bytes_value)
    assert result == "ISCC:MAIWGQRD43YZQUAA"


def test_isccid_field_to_python_invalid_bytes_length():
    # type: () -> None
    """Test to_python with bytes of incorrect length."""
    field = IsccIDField()
    with pytest.raises(ValidationError) as exc_info:
        field.to_python(b"SHORT")
    assert exc_info.value.code == "invalid_length"
    assert "exactly 8 bytes" in str(exc_info.value)


def test_isccid_field_to_python_invalid_type():
    # type: () -> None
    """Test to_python with unsupported type."""
    field = IsccIDField()
    with pytest.raises(ValidationError) as exc_info:
        field.to_python(12345)
    assert exc_info.value.code == "invalid_type"
    assert "must be a string or bytes" in str(exc_info.value)


def test_isccid_field_from_db_value_none():
    # type: () -> None
    """Test from_db_value with None."""
    field = IsccIDField()
    result = field.from_db_value(None, None, None)
    assert result is None


def test_isccid_field_from_db_value_bytes():
    # type: () -> None
    """Test from_db_value with valid bytes."""
    field = IsccIDField()
    iscc_id = IsccID("ISCC:MAIWGQRD43YZQUAA")
    bytes_value = bytes(iscc_id)
    result = field.from_db_value(bytes_value, None, None)
    assert result == "ISCC:MAIWGQRD43YZQUAA"


def test_isccid_field_get_prep_value_none():
    # type: () -> None
    """Test get_prep_value with None."""
    field = IsccIDField()
    assert field.get_prep_value(None) is None


def test_isccid_field_get_prep_value_empty_string():
    # type: () -> None
    """Test get_prep_value with empty string."""
    field = IsccIDField()
    assert field.get_prep_value("") is None


def test_isccid_field_get_prep_value_valid_string():
    # type: () -> None
    """Test get_prep_value with valid ISCC-ID string."""
    field = IsccIDField()
    valid_iscc = "ISCC:MAIWGQRD43YZQUAA"
    result = field.get_prep_value(valid_iscc)
    assert isinstance(result, bytes)
    assert len(result) == 8
    # Verify round-trip
    assert str(IsccID(result)) == valid_iscc


def test_isccid_field_get_prep_value_valid_bytes():
    # type: () -> None
    """Test get_prep_value with valid bytes input."""
    field = IsccIDField()
    iscc_id = IsccID("ISCC:MAIWGQRD43YZQUAA")
    bytes_value = bytes(iscc_id)
    result = field.get_prep_value(bytes_value)
    assert result == bytes_value


def test_isccid_field_get_prep_value_invalid_bytes():
    # type: () -> None
    """Test get_prep_value with invalid bytes length."""
    field = IsccIDField()
    with pytest.raises(ValidationError) as exc_info:
        field.get_prep_value(b"TOOLONG!!")
    assert exc_info.value.code == "invalid_length"
    assert "exactly 8 bytes" in str(exc_info.value)


def test_isccid_field_get_prep_value_invalid_string():
    # type: () -> None
    """Test get_prep_value with invalid string that fails validation."""
    field = IsccIDField()
    with pytest.raises(ValidationError):
        field.get_prep_value("INVALID")


def test_isccid_field_get_prep_value_string_converts_to_none():
    # type: () -> None
    """Test get_prep_value when to_python returns None for a string."""
    IsccIDField()

    # Create a custom field instance that simulates to_python returning None
    # This happens when an empty string goes through to_python
    class TestField(IsccIDField):
        def to_python(self, value):
            # type: (object) -> None
            """Always return None to test the branch."""
            return None

    test_field = TestField()
    result = test_field.get_prep_value("any_value")
    assert result is None


def test_isccid_field_formfield():
    # type: () -> None
    """Test formfield returns CharField with correct defaults."""
    field = IsccIDField()
    form_field = field.formfield()
    assert isinstance(form_field, CharField)
    assert form_field.max_length == 25


def test_isccid_field_formfield_with_kwargs():
    # type: () -> None
    """Test formfield with custom kwargs."""
    field = IsccIDField()
    form_field = field.formfield(max_length=30, help_text="Custom help")
    assert isinstance(form_field, CharField)
    assert form_field.max_length == 30
    assert form_field.help_text == "Custom help"


def test_iscc_id_field_value_to_string():
    # type: () -> None
    """Test value_to_string method for serialization."""
    field = IsccIDField()

    # Create a mock object with ISCC-ID value
    class MockObject:
        iscc_id = b"\x19h\xb9%\x16\x10\xd0\x00"  # 8-byte binary representation

    obj = MockObject()

    # Test with valid value
    field.attname = "iscc_id"
    result = field.value_to_string(obj)
    assert result == "ISCC:MAIRS2FZEULBBUAA"

    # Test with None value
    obj.iscc_id = None
    result = field.value_to_string(obj)
    assert result is None


# Tests for HexField
def test_hex_field_init():
    # type: () -> None
    """Test HexField initialization."""
    field = HexField()
    assert field.description == "Hex string stored as binary"


def test_hex_field_init_with_max_length():
    # type: () -> None
    """Test HexField initialization with max_length."""
    field = HexField(max_length=32)
    assert field.max_length == 32


# Parameterized tests for HexField.to_python
@pytest.mark.parametrize(
    "input_value,expected_output,should_raise,error_code",
    [
        (None, None, False, None),
        ("", None, False, None),
        ("deadbeef", b"\xde\xad\xbe\xef", False, None),
        ("DEADBEEF", b"\xde\xad\xbe\xef", False, None),  # Case insensitive
        ("  deadbeef  ", None, True, "invalid_hex"),  # Whitespace should fail
        (b"\xde\xad\xbe\xef", b"\xde\xad\xbe\xef", False, None),
        (bytearray(b"\xde\xad\xbe\xef"), b"\xde\xad\xbe\xef", False, None),
        (memoryview(b"\xde\xad\xbe\xef"), b"\xde\xad\xbe\xef", False, None),
        ("invalid_hex", None, True, "invalid_hex"),
        ("deadbee", None, True, "invalid_hex"),  # Odd length
        (12345, None, True, "invalid_type"),
    ],
)
def test_hex_field_to_python_parameterized(input_value, expected_output, should_raise, error_code):
    # type: (str|bytes|bytearray|memoryview|int|None, bytes|None, bool, str|None) -> None
    """Parameterized test for HexField.to_python method."""
    field = HexField()

    if should_raise:
        with pytest.raises(ValidationError) as exc_info:
            field.to_python(input_value)
        assert exc_info.value.code == error_code
    else:
        result = field.to_python(input_value)
        assert result == expected_output


# Parameterized tests for HexField.get_prep_value
@pytest.mark.parametrize(
    "input_value,expected_bytes,should_raise",
    [
        (None, None, False),
        ("", None, False),
        ("deadbeef", b"\xde\xad\xbe\xef", False),
        ("DEADBEEF", b"\xde\xad\xbe\xef", False),  # Case insensitive
        (b"\xde\xad\xbe\xef", b"\xde\xad\xbe\xef", False),  # Already bytes
        ("invalid", None, True),
        ("deadbee", None, True),  # Odd length
    ],
)
def test_hex_field_get_prep_value_parameterized(input_value, expected_bytes, should_raise):
    # type: (str|bytes|None, bytes|None, bool) -> None
    """Parameterized test for HexField.get_prep_value method."""
    field = HexField()

    if should_raise:
        with pytest.raises(ValidationError):
            field.get_prep_value(input_value)
    else:
        result = field.get_prep_value(input_value)
        assert result == expected_bytes


def test_hex_field_from_db_value_none():
    # type: () -> None
    """Test from_db_value with None."""
    field = HexField()
    result = field.from_db_value(None, None, None)
    assert result is None


def test_hex_field_from_db_value_bytes():
    # type: () -> None
    """Test from_db_value with bytes."""
    field = HexField()
    bytes_value = b"\xde\xad\xbe\xef"
    result = field.from_db_value(bytes_value, None, None)
    assert result == bytes_value  # Now returns bytes directly


def test_hex_field_value_to_string():
    # type: () -> None
    """Test value_to_string method for serialization."""
    field = HexField()

    # Create a mock object with hex value as bytes
    class MockObject:
        hex_value = b"\xde\xad\xbe\xef"

    obj = MockObject()

    # Test with valid bytes value
    field.attname = "hex_value"
    result = field.value_to_string(obj)
    assert result == "deadbeef"

    # Test with None value
    obj.hex_value = None
    result = field.value_to_string(obj)
    assert result is None

    # Test with string value (shouldn't normally happen but test str() fallback)
    obj.hex_value = "cafebabe"
    result = field.value_to_string(obj)
    assert result == "cafebabe"


def test_hex_field_formfield():
    # type: () -> None
    """Test formfield returns CharField."""
    field = HexField()
    form_field = field.formfield()
    assert isinstance(form_field, CharField)


def test_hex_field_formfield_with_max_length():
    # type: () -> None
    """Test formfield with max_length set."""
    field = HexField(max_length=16)  # 16 bytes = 32 hex chars
    form_field = field.formfield()
    assert isinstance(form_field, CharField)
    assert form_field.max_length == 32  # 2x the binary length


def test_hex_field_formfield_with_kwargs():
    # type: () -> None
    """Test formfield with custom kwargs."""
    field = HexField()
    form_field = field.formfield(max_length=64, help_text="Enter hex value")
    assert isinstance(form_field, CharField)
    assert form_field.max_length == 64
    assert form_field.help_text == "Enter hex value"


def test_hex_field_roundtrip():
    # type: () -> None
    """Test complete roundtrip: hex string -> bytes -> bytes."""
    field = HexField()

    # Test with various hex strings
    test_cases = [
        ("deadbeef", b"\xde\xad\xbe\xef"),
        ("0123456789abcdef", b"\x01\x23\x45\x67\x89\xab\xcd\xef"),
        ("00", b"\x00"),
        ("ff" * 32, b"\xff" * 32),  # 64 character hex string
    ]

    for hex_str, expected_bytes in test_cases:
        # Convert to bytes for storage
        bytes_value = field.get_prep_value(hex_str)
        assert bytes_value == expected_bytes

        # Convert back from storage
        result = field.from_db_value(bytes_value, None, None)
        assert result == expected_bytes  # Now returns bytes directly
