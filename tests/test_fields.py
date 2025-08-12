"""
Tests for custom Django field implementations.
"""

from unittest.mock import MagicMock

import pytest
from django.core.exceptions import ValidationError
from django.forms import CharField

from iscc_hub.fields import IsccIDField, SequenceField
from iscc_hub.iscc_id import IsccID


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
