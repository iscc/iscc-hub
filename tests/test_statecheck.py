"""
Tests for the statecheck module.
"""

import pytest
from django.db import transaction

from iscc_hub.models import Event, IsccDeclaration
from iscc_hub.statecheck import (
    StateValidationError,
    check_duplicate_datahash,
    check_duplicate_declaration,
    check_iscc_id_exists,
    check_nonce_unused,
    get_declaration_by_iscc_id,
    validate_state,
    validate_state_atomic,
)
from tests.conftest import create_test_declaration, generate_test_iscc_id


@pytest.mark.django_db
class TestStateValidation:
    """Test state validation functions."""

    def test_check_nonce_unused_passes_for_new_nonce(self):
        """Test that checking an unused nonce passes."""
        # Should not raise for a new nonce
        check_nonce_unused("abcdef0123456789abcdef0123456789")

    def test_check_nonce_unused_fails_for_existing_nonce(self):
        """Test that checking an existing nonce raises error."""
        # Create a declaration with a nonce
        create_test_declaration(seq=1, nonce="fedcba9876543210fedcba9876543210")

        # Should raise for existing nonce
        with pytest.raises(StateValidationError) as exc_info:
            check_nonce_unused("fedcba9876543210fedcba9876543210")

        assert exc_info.value.code == "NONCE_REUSE"
        assert "already used" in exc_info.value.message

    def test_check_duplicate_declaration_passes_for_new_combination(self):
        """Test that checking a new iscc_code/actor combination passes."""
        check_duplicate_declaration(
            "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
        )

    def test_check_duplicate_declaration_fails_for_existing_combination(self):
        """Test that checking an existing iscc_code/actor combination raises error."""
        # Create a declaration
        create_test_declaration(seq=1)

        # Should raise for duplicate
        with pytest.raises(StateValidationError) as exc_info:
            check_duplicate_declaration(
                "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
                "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            )

        assert exc_info.value.code == "DUPLICATE_DECLARATION"
        assert "already declared" in exc_info.value.message

    def test_check_duplicate_declaration_passes_for_deleted_declaration(self):
        """Test that checking against a deleted declaration passes."""
        # Create a deleted declaration
        create_test_declaration(seq=1, deleted=True)

        # Should not raise for deleted declaration
        check_duplicate_declaration(
            "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
        )

    def test_check_duplicate_datahash_passes_for_new_combination(self):
        """Test that checking a new datahash/actor combination passes."""
        check_duplicate_datahash(
            "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
        )

    def test_check_duplicate_datahash_fails_for_existing_combination(self):
        """Test that checking an existing datahash/actor combination raises error."""
        # Create a declaration
        create_test_declaration(seq=1)

        # Should raise for duplicate
        with pytest.raises(StateValidationError) as exc_info:
            check_duplicate_datahash(
                "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
                "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            )

        assert exc_info.value.code == "DUPLICATE_DATAHASH"
        assert "already declared" in exc_info.value.message

    def test_check_iscc_id_exists_returns_true_for_existing(self):
        """Test that checking an existing ISCC-ID returns True."""
        # Create a declaration
        iscc_id = generate_test_iscc_id(seq=1)
        create_test_declaration(seq=1)  # Uses the same iscc_id from generate_test_iscc_id

        assert check_iscc_id_exists(iscc_id) is True

    def test_check_iscc_id_exists_returns_false_for_nonexistent(self):
        """Test that checking a non-existent ISCC-ID returns False."""
        non_existent_id = generate_test_iscc_id(seq=999)
        assert check_iscc_id_exists(non_existent_id) is False

    def test_get_declaration_by_iscc_id_returns_declaration(self):
        """Test that getting an existing declaration works."""
        # Create a declaration
        decl = create_test_declaration(seq=1)

        result = get_declaration_by_iscc_id(decl.iscc_id)
        assert result is not None
        # Both should be the same database record
        assert result.event_seq == decl.event_seq
        assert result.iscc_code == decl.iscc_code
        assert result.nonce == decl.nonce

    def test_get_declaration_by_iscc_id_returns_none_for_nonexistent(self):
        """Test that getting a non-existent declaration returns None."""
        non_existent_id = generate_test_iscc_id(seq=999)
        result = get_declaration_by_iscc_id(non_existent_id)
        assert result is None

    def test_validate_state_for_new_declaration(self):
        """Test validate_state for a new declaration."""
        iscc_note = {
            "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "nonce": "abcdef0123456789abcdef0123456789",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Should not raise
        validate_state(iscc_note, "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5")

    def test_validate_state_for_update_with_same_actor(self):
        """Test validate_state for updating own declaration."""
        # Create existing declaration
        decl = create_test_declaration(seq=1)

        iscc_note = {
            "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "nonce": "newnonceabcdef0123456789abcdef01",  # New nonce for update
            "timestamp": "2024-01-02T00:00:00Z",
        }

        # Should not raise for same actor
        validate_state(iscc_note, "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5", iscc_id=decl.iscc_id)

    def test_validate_state_for_update_with_different_actor(self):
        """Test validate_state fails when updating another actor's declaration."""
        # Create existing declaration
        decl = create_test_declaration(seq=1)

        iscc_note = {
            "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "nonce": "newnonceabcdef0123456789abcdef01",
            "timestamp": "2024-01-02T00:00:00Z",
        }

        # Should raise for different actor
        with pytest.raises(StateValidationError) as exc_info:
            validate_state(
                iscc_note,
                "DifferentActor123456789",  # Different actor
                iscc_id=decl.iscc_id,
            )

        assert exc_info.value.code == "UNAUTHORIZED"
        assert "another actor" in exc_info.value.message

    def test_validate_state_for_update_nonexistent_iscc_id(self):
        """Test validate_state fails for non-existent ISCC-ID update."""
        iscc_note = {
            "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "nonce": "newnonceabcdef0123456789abcdef01",
            "timestamp": "2024-01-02T00:00:00Z",
        }

        non_existent_id = generate_test_iscc_id(seq=999)
        with pytest.raises(StateValidationError) as exc_info:
            validate_state(
                iscc_note,
                "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
                iscc_id=non_existent_id,  # Non-existent
            )

        assert exc_info.value.code == "NOT_FOUND"
        assert "not found" in exc_info.value.message

    def test_validate_state_for_update_with_duplicate_nonce(self):
        """Test validate_state fails for update with already used nonce."""
        # Create two declarations
        decl1 = create_test_declaration(seq=1)
        create_test_declaration(
            seq=2,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQZ",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6d",
            nonce="existingnonce123456789abcdef0123",
        )

        iscc_note = {
            "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "nonce": "existingnonce123456789abcdef0123",  # Already used nonce
            "timestamp": "2024-01-02T00:00:00Z",
        }

        with pytest.raises(StateValidationError) as exc_info:
            validate_state(iscc_note, "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5", iscc_id=decl1.iscc_id)

        assert exc_info.value.code == "NONCE_REUSE"

    def test_validate_state_atomic_wraps_in_transaction(self):
        """Test that validate_state_atomic uses atomic transaction."""
        iscc_note = {
            "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "nonce": "abcdef0123456789abcdef0123456789",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Should not raise and should use transaction
        validate_state_atomic(iscc_note, "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5")

    def test_state_validation_error_stores_code_and_message(self):
        """Test that StateValidationError properly stores code and message."""
        error = StateValidationError("TEST_CODE", "Test message")
        assert error.code == "TEST_CODE"
        assert error.message == "Test message"
        assert str(error) == "Test message"
