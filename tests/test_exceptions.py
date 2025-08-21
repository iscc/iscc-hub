"""Tests for custom exception classes and error response formatting."""

import pytest

from iscc_hub.exceptions import (
    DuplicateDeclarationError,
    FieldValidationError,
    HashError,
    HexFormatError,
    IsccCodeError,
    IsccIdError,
    LengthError,
    NonceError,
    SequencerError,
    SignatureError,
    TimestampError,
    ValidationError,
)


def test_validation_error_basic():
    # type: () -> None
    """Test basic ValidationError with message only."""
    error = ValidationError("Something went wrong")
    assert str(error) == "Something went wrong"
    assert error.message == "Something went wrong"
    assert error.code == "validation_failed"
    assert error.field is None

    response = error.to_error_response()
    assert response == {"error": {"message": "Something went wrong", "code": "validation_failed"}}


def test_validation_error_with_code():
    # type: () -> None
    """Test ValidationError with custom code."""
    error = ValidationError("Custom error", code="custom_code")
    assert error.code == "custom_code"

    response = error.to_error_response()
    assert response == {"error": {"message": "Custom error", "code": "custom_code"}}


def test_validation_error_with_field():
    # type: () -> None
    """Test ValidationError with field information."""
    error = ValidationError("Field error", code="field_error", field="test_field")
    assert error.field == "test_field"

    response = error.to_error_response()
    assert response == {"error": {"message": "Field error", "code": "field_error", "field": "test_field"}}


def test_field_validation_error():
    # type: () -> None
    """Test FieldValidationError."""
    error = FieldValidationError("username", "Username is required", "missing_field")
    assert error.field == "username"
    assert error.message == "Username is required"
    assert error.code == "missing_field"

    response = error.to_error_response()
    assert response == {
        "error": {"message": "Username is required", "code": "missing_field", "field": "username"}
    }


def test_iscc_code_error():
    # type: () -> None
    """Test IsccCodeError with automatic field and code."""
    error = IsccCodeError("Invalid ISCC format")
    assert error.field == "iscc_code"
    assert error.code == "invalid_iscc"
    assert error.message == "Invalid ISCC format"

    response = error.to_error_response()
    assert response == {
        "error": {"message": "Invalid ISCC format", "code": "invalid_iscc", "field": "iscc_code"}
    }


def test_iscc_id_error():
    # type: () -> None
    """Test IsccIdError with automatic field and code."""
    error = IsccIdError("Invalid ISCC-ID format")
    assert error.field == "iscc_id"
    assert error.code == "invalid_iscc"
    assert error.message == "Invalid ISCC-ID format"

    response = error.to_error_response()
    assert response == {
        "error": {"message": "Invalid ISCC-ID format", "code": "invalid_iscc", "field": "iscc_id"}
    }


def test_timestamp_error_format():
    # type: () -> None
    """Test TimestampError for format issues."""
    error = TimestampError("Invalid timestamp format")
    assert error.field == "timestamp"
    assert error.code == "invalid_format"

    response = error.to_error_response()
    assert response == {
        "error": {"message": "Invalid timestamp format", "code": "invalid_format", "field": "timestamp"}
    }


def test_timestamp_error_out_of_range():
    # type: () -> None
    """Test TimestampError for out of range timestamp."""
    error = TimestampError("Timestamp too old", out_of_range=True)
    assert error.field == "timestamp"
    assert error.code == "timestamp_out_of_range"

    response = error.to_error_response()
    assert response == {
        "error": {"message": "Timestamp too old", "code": "timestamp_out_of_range", "field": "timestamp"}
    }


def test_nonce_error_format():
    # type: () -> None
    """Test NonceError for format issues."""
    error = NonceError("Invalid nonce format")
    assert error.field == "nonce"
    assert error.code == "invalid_format"

    response = error.to_error_response()
    assert response["error"]["code"] == "invalid_format"


def test_nonce_error_reuse():
    # type: () -> None
    """Test NonceError for nonce reuse."""
    error = NonceError("Nonce already used: 000faa3f18c7b9407a48536a9b00c4cb", is_reuse=True)
    assert error.code == "nonce_reuse"

    response = error.to_error_response()
    assert response["error"]["code"] == "nonce_reuse"
    assert response["error"]["field"] == "nonce"


def test_nonce_error_mismatch():
    # type: () -> None
    """Test NonceError for hub ID mismatch."""
    error = NonceError("Hub ID mismatch", is_mismatch=True)
    assert error.code == "nonce_mismatch"

    response = error.to_error_response()
    assert response["error"]["code"] == "nonce_mismatch"


def test_signature_error():
    # type: () -> None
    """Test SignatureError."""
    error = SignatureError("Invalid signature")
    assert error.code == "invalid_signature"
    assert error.field is None  # Signature errors don't have a specific field

    response = error.to_error_response()
    assert response == {"error": {"message": "Invalid signature", "code": "invalid_signature"}}


def test_hash_error_format():
    # type: () -> None
    """Test HashError for format issues."""
    error = HashError("datahash", "Invalid hash format")
    assert error.field == "datahash"
    assert error.code == "invalid_format"

    response = error.to_error_response()
    assert response["error"]["field"] == "datahash"
    assert response["error"]["code"] == "invalid_format"


def test_hash_error_duplicate():
    # type: () -> None
    """Test HashError for duplicate datahash."""
    error = HashError("datahash", "Datahash already exists", is_duplicate=True)
    assert error.field == "datahash"
    assert error.code == "duplicate_datahash"

    response = error.to_error_response()
    assert response["error"]["code"] == "duplicate_datahash"


def test_hash_error_metahash():
    # type: () -> None
    """Test HashError for metahash (not duplicate)."""
    error = HashError("metahash", "Invalid metahash", is_duplicate=True)
    assert error.field == "metahash"
    assert error.code == "invalid_format"  # metahash doesn't get duplicate_datahash code

    response = error.to_error_response()
    assert response["error"]["field"] == "metahash"
    assert response["error"]["code"] == "invalid_format"


def test_length_error():
    # type: () -> None
    """Test LengthError."""
    error = LengthError("nonce", "Nonce must be 32 characters")
    assert error.field == "nonce"
    assert error.code == "invalid_length"

    response = error.to_error_response()
    assert response == {
        "error": {"message": "Nonce must be 32 characters", "code": "invalid_length", "field": "nonce"}
    }


def test_hex_format_error():
    # type: () -> None
    """Test HexFormatError."""
    error = HexFormatError("datahash", "Must be lowercase hex")
    assert error.field == "datahash"
    assert error.code == "invalid_hex"

    response = error.to_error_response()
    assert response == {
        "error": {"message": "Must be lowercase hex", "code": "invalid_hex", "field": "datahash"}
    }


def test_sequencer_error():
    # type: () -> None
    """Test SequencerError."""
    error = SequencerError("Failed to acquire sequence lock")
    assert error.message == "Failed to acquire sequence lock"
    assert error.code == "sequencer_error"
    assert error.field is None
    assert error.status_code == 400

    response = error.to_error_response()
    assert response == {"error": {"message": "Failed to acquire sequence lock", "code": "sequencer_error"}}


def test_duplicate_declaration_error():
    # type: () -> None
    """Test DuplicateDeclarationError without additional context."""
    error = DuplicateDeclarationError("Datahash already declared")
    assert error.message == "Datahash already declared"
    assert error.code == "duplicate_declaration"
    assert error.field == "datahash"
    assert error.status_code == 409
    assert error.existing_iscc_id is None
    assert error.existing_actor is None

    response = error.to_error_response()
    assert response == {
        "error": {"message": "Datahash already declared", "code": "duplicate_declaration", "field": "datahash"}
    }


def test_duplicate_declaration_error_with_context():
    # type: () -> None
    """Test DuplicateDeclarationError with existing declaration details."""
    error = DuplicateDeclarationError(
        "Datahash already declared",
        existing_iscc_id="ISCC:MAIWFKM3UDDAAEAB",
        existing_actor="did:key:z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
    )
    assert error.existing_iscc_id == "ISCC:MAIWFKM3UDDAAEAB"
    assert error.existing_actor == "did:key:z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB"

    response = error.to_error_response()
    assert response == {
        "error": {
            "message": "Datahash already declared",
            "code": "duplicate_declaration",
            "field": "datahash",
            "existing_iscc_id": "ISCC:MAIWFKM3UDDAAEAB",
            "existing_actor": "did:key:z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
        }
    }


def test_duplicate_declaration_error_partial_context():
    # type: () -> None
    """Test DuplicateDeclarationError with only ISCC-ID context."""
    error = DuplicateDeclarationError("Datahash already declared", existing_iscc_id="ISCC:MAIWFKM3UDDAAEAB")
    assert error.existing_iscc_id == "ISCC:MAIWFKM3UDDAAEAB"
    assert error.existing_actor is None

    response = error.to_error_response()
    assert response == {
        "error": {
            "message": "Datahash already declared",
            "code": "duplicate_declaration",
            "field": "datahash",
            "existing_iscc_id": "ISCC:MAIWFKM3UDDAAEAB",
        }
    }


def test_exception_inheritance():
    # type: () -> None
    """Test that all custom exceptions inherit from ValidationError."""
    assert issubclass(FieldValidationError, ValidationError)
    assert issubclass(IsccCodeError, FieldValidationError)
    assert issubclass(IsccIdError, FieldValidationError)
    assert issubclass(TimestampError, FieldValidationError)
    assert issubclass(NonceError, FieldValidationError)
    assert issubclass(SignatureError, ValidationError)
    assert issubclass(HashError, FieldValidationError)
    assert issubclass(LengthError, FieldValidationError)
    assert issubclass(HexFormatError, FieldValidationError)


def test_error_response_conforms_to_schema():
    # type: () -> None
    """Test that error responses conform to ErrorResponse schema."""
    # Test various error types to ensure they all produce valid responses
    errors = [
        ValidationError("Generic error"),
        FieldValidationError("field", "Field error", "field_code"),
        IsccCodeError("Invalid ISCC"),
        IsccIdError("Invalid ISCC-ID"),
        TimestampError("Bad time", out_of_range=True),
        NonceError("Bad nonce", is_reuse=True),
        SignatureError("Bad sig"),
        HashError("datahash", "Bad hash"),
        LengthError("field", "Too long"),
        HexFormatError("field", "Not hex"),
    ]

    for error in errors:
        response = error.to_error_response()

        # Check structure matches ErrorResponse schema
        assert "error" in response
        assert isinstance(response["error"], dict)

        error_detail = response["error"]
        assert "message" in error_detail
        assert isinstance(error_detail["message"], str)
        assert "code" in error_detail
        assert isinstance(error_detail["code"], str)

        # Field is optional but must be string if present
        if "field" in error_detail:
            assert isinstance(error_detail["field"], str)
