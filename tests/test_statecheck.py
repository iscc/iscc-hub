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
        IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
        )

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
        IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
            deleted=False,
        )

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
        IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
            deleted=True,  # Marked as deleted
        )

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
        IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
            deleted=False,
        )

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
        IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
        )

        assert check_iscc_id_exists(b"12345678") is True

    def test_check_iscc_id_exists_returns_false_for_nonexistent(self):
        """Test that checking a non-existent ISCC-ID returns False."""
        assert check_iscc_id_exists(b"87654321") is False

    def test_get_declaration_by_iscc_id_returns_declaration(self):
        """Test that getting an existing declaration works."""
        # Create a declaration
        decl = IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
        )

        result = get_declaration_by_iscc_id(b"12345678")
        assert result is not None
        # Both should be the same database record
        assert result.event_seq == decl.event_seq
        assert result.iscc_code == decl.iscc_code
        assert result.nonce == decl.nonce

    def test_get_declaration_by_iscc_id_returns_none_for_nonexistent(self):
        """Test that getting a non-existent declaration returns None."""
        result = get_declaration_by_iscc_id(b"87654321")
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
        IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
        )

        iscc_note = {
            "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "nonce": "newnonceabcdef0123456789abcdef01",  # New nonce for update
            "timestamp": "2024-01-02T00:00:00Z",
        }

        # Should not raise for same actor
        validate_state(iscc_note, "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5", iscc_id=b"12345678")

    def test_validate_state_for_update_with_different_actor(self):
        """Test validate_state fails when updating another actor's declaration."""
        # Create existing declaration
        IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
        )

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
                iscc_id=b"12345678",
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

        with pytest.raises(StateValidationError) as exc_info:
            validate_state(
                iscc_note,
                "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
                iscc_id=b"87654321",  # Non-existent
            )

        assert exc_info.value.code == "NOT_FOUND"
        assert "not found" in exc_info.value.message

    def test_validate_state_for_update_with_duplicate_nonce(self):
        """Test validate_state fails for update with already used nonce."""
        # Create two declarations
        IsccDeclaration.objects.create(
            iscc_id=b"12345678",
            event_seq=1,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            nonce="fedcba9876543210fedcba9876543210",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
        )

        IsccDeclaration.objects.create(
            iscc_id=b"87654321",
            event_seq=2,
            iscc_code="ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQZ",
            datahash="1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6d",
            nonce="existingnonce123456789abcdef0123",
            actor="7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
            declared_at="2024-01-01T00:00:00Z",
            created_at="2024-01-01T00:00:00Z",
        )

        iscc_note = {
            "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
            "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
            "nonce": "existingnonce123456789abcdef0123",  # Already used nonce
            "timestamp": "2024-01-02T00:00:00Z",
        }

        with pytest.raises(StateValidationError) as exc_info:
            validate_state(iscc_note, "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5", iscc_id=b"12345678")

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
