"""
Tests for custom Django field implementations.
"""

from unittest.mock import MagicMock

import pytest

from iscc_hub.fields import SequenceField


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
