"""Custom exception classes for ISCC Hub validation with detailed error information."""


class ValidationError(ValueError):
    """
    Base validation error with structured error details.

    Provides error details conforming to the ErrorResponse schema for API responses.
    """

    def __init__(self, message, code=None, field=None):
        # type: (str, str|None, str|None) -> None
        """
        Initialize ValidationError with structured error details.

        :param message: Human-readable error message
        :param code: Machine-readable error code for programmatic handling
        :param field: The specific field that caused the error
        """
        super().__init__(message)
        self.message = message
        self.code = code or "validation_failed"
        self.field = field

    def to_error_response(self):
        # type: () -> dict
        """
        Convert exception to ErrorResponse format.

        :return: Dictionary conforming to ErrorResponse schema
        """
        error_detail = {"message": self.message, "code": self.code}
        if self.field:
            error_detail["field"] = self.field
        return {"error": error_detail}


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
        """Initialize ISCC code error."""
        super().__init__("iscc_code", message, "invalid_iscc")


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
        elif is_mismatch:
            code = "nonce_mismatch"
        else:
            code = "invalid_format"
        super().__init__("nonce", message, code)


class SignatureError(ValidationError):
    """Signature validation error."""

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
        code = "duplicate_datahash" if is_duplicate and field == "datahash" else "invalid_format"
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
