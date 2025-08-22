"""Custom exception classes for ISCC Hub validation with detailed error information."""


class BaseApiException(Exception):
    """
    Base exception for all API-related errors.

    Handles conversion to Django Ninja HTTP responses with appropriate status codes.
    """

    status_code = 400  # Default to Bad Request

    def __init__(self, message, code=None, field=None):
        # type: (str, str|None, str|None) -> None
        """
        Initialize BaseApiException with structured error details.

        :param message: Human-readable error message
        :param code: Machine-readable error code for programmatic handling
        :param field: The specific field that caused the error
        """
        super().__init__(message)
        self.message = message
        self.code = code or "error"
        self.field = field

    def to_error_response(self):
        # type: () -> dict
        """
        Convert exception to ErrorResponse format for API.

        :return: Dictionary conforming to ErrorResponse schema
        """
        error_detail = {"message": self.message, "code": self.code}
        if self.field:
            error_detail["field"] = self.field
        return {"error": error_detail}


class ValidationError(BaseApiException, ValueError):
    """
    Base validation error with structured error details.

    Provides error details conforming to the ErrorResponse schema for API responses.
    """

    status_code = 422  # Unprocessable Entity

    def __init__(self, message, code=None, field=None):
        # type: (str, str|None, str|None) -> None
        """
        Initialize ValidationError with structured error details.

        :param message: Human-readable error message
        :param code: Machine-readable error code for programmatic handling
        :param field: The specific field that caused the error
        """
        super().__init__(message, code or "validation_failed", field)


class FieldValidationError(ValidationError):
    """Validation error specific to a field."""

    def __init__(self, field, message, code=None):
        # type: (str, str, str|None) -> None
        """
        Initialize field-specific validation error.

        :param field: The field that failed validation
        :param message: Human-readable error message
        :param code: Machine-readable error code
        """
        super().__init__(message, code, field)


class IsccCodeError(FieldValidationError):
    """ISCC code validation error."""

    def __init__(self, message):
        # type: (str) -> None
        """Initialize ISCC-CODE error."""
        super().__init__("iscc_code", message, "invalid_iscc")


class IsccIdError(FieldValidationError):
    """ISCC-ID validation error."""

    def __init__(self, message):
        # type: (str) -> None
        """Initialize ISCC-ID error."""
        super().__init__("iscc_id", message, "invalid_iscc")


class TimestampError(FieldValidationError):
    """Timestamp validation error."""

    def __init__(self, message, out_of_range=False):
        # type: (str, bool) -> None
        """
        Initialize timestamp error.

        :param message: Error message
        :param out_of_range: Whether timestamp is out of tolerance range
        """
        code = "timestamp_out_of_range" if out_of_range else "invalid_format"
        super().__init__("timestamp", message, code)


class NonceError(FieldValidationError):
    """Nonce validation error."""

    def __init__(self, message, is_reuse=False, is_mismatch=False):
        # type: (str, bool, bool) -> None
        """
        Initialize nonce error.

        :param message: Error message
        :param is_reuse: Whether nonce was already used
        :param is_mismatch: Whether nonce doesn't match hub ID
        """
        if is_reuse:
            code = "nonce_reuse"
            self.status_code = 400  # Bad Request
        elif is_mismatch:
            code = "nonce_mismatch"
        else:
            code = "invalid_format"
        super().__init__("nonce", message, code)


class SignatureError(ValidationError):
    """Signature validation error."""

    status_code = 401  # Unauthorized

    def __init__(self, message):
        # type: (str) -> None
        """Initialize signature error."""
        super().__init__(message, "invalid_signature", None)


class HashError(FieldValidationError):
    """Hash validation error (datahash/metahash)."""

    def __init__(self, field, message, is_duplicate=False):
        # type: (str, str, bool) -> None
        """
        Initialize hash error.

        :param field: The hash field name (datahash or metahash)
        :param message: Error message
        :param is_duplicate: Whether hash is a duplicate
        """
        if is_duplicate and field == "datahash":
            code = "duplicate_datahash"
            self.status_code = 400  # Bad Request
        else:
            code = "invalid_format"
        super().__init__(field, message, code)


class LengthError(FieldValidationError):
    """Field length validation error."""

    def __init__(self, field, message):
        # type: (str, str) -> None
        """Initialize length error."""
        super().__init__(field, message, "invalid_length")


class HexFormatError(FieldValidationError):
    """Hexadecimal format validation error."""

    def __init__(self, field, message):
        # type: (str, str) -> None
        """Initialize hex format error."""
        super().__init__(field, message, "invalid_hex")


class SequencerError(BaseApiException):
    """Sequencer operation error."""

    status_code = 400  # Bad Request

    def __init__(self, message):
        # type: (str) -> None
        """Initialize sequencer error."""
        super().__init__(message, code="sequencer_error")


class NotFoundError(BaseApiException):
    """Resource not found error."""

    status_code = 404  # Not Found

    def __init__(self, message, resource_type=None, resource_id=None):
        # type: (str, str|None, str|None) -> None
        """
        Initialize not found error.

        :param message: Human-readable error message
        :param resource_type: Type of resource not found (e.g., "declaration")
        :param resource_id: ID of the resource not found
        """
        super().__init__(message, "not_found", None)
        self.resource_type = resource_type
        self.resource_id = resource_id

    def to_error_response(self):
        # type: () -> dict
        """
        Convert exception to ErrorResponse format for API.

        :return: Dictionary conforming to ErrorResponse schema with additional context
        """
        error_detail = {"message": self.message, "code": self.code}
        if self.field:
            error_detail["field"] = self.field
        if self.resource_type:
            error_detail["resource_type"] = self.resource_type
        if self.resource_id:
            error_detail["resource_id"] = self.resource_id
        return {"error": error_detail}


class DuplicateDeclarationError(BaseApiException):
    """Duplicate declaration error."""

    status_code = 409  # Conflict

    def __init__(self, message, existing_iscc_id=None, existing_actor=None):
        # type: (str, str|None, str|None) -> None
        """
        Initialize duplicate declaration error.

        :param message: Human-readable error message
        :param existing_iscc_id: ISCC-ID of existing declaration
        :param existing_actor: Actor who made the existing declaration
        """
        super().__init__(message, "duplicate_declaration", "datahash")
        self.existing_iscc_id = existing_iscc_id
        self.existing_actor = existing_actor

    def to_error_response(self):
        # type: () -> dict
        """
        Convert exception to ErrorResponse format for API.

        :return: Dictionary conforming to ErrorResponse schema with additional context
        """
        error_detail = {"message": self.message, "code": self.code, "field": self.field}
        if self.existing_iscc_id:
            error_detail["existing_iscc_id"] = self.existing_iscc_id
        if self.existing_actor:
            error_detail["existing_actor"] = self.existing_actor
        return {"error": error_detail}
