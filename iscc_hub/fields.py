from django.core.exceptions import ValidationError
from django.db import models
from django.forms import CharField

from iscc_hub.iscc_id import IsccID


class SequenceField(models.AutoField):
    """
    A primary key field that uses SQLite's rowid without AUTOINCREMENT.
    Provides gap-less sequence when used with proper transaction handling.

    Inherits from AutoField to get correct INSERT behavior from Django.
    """

    description = "Gap-less integer primary key"

    def db_type(self, connection):
        # type: (object) -> str
        """
        Return just INTEGER for SQLite to use rowid without AUTOINCREMENT.
        Django will automatically add PRIMARY KEY.
        """
        return "INTEGER"

    def db_type_suffix(self, connection):
        # type: (object) -> str
        """
        Override to return empty string instead of 'AUTOINCREMENT'.
        This ensures SQLite uses rowid without AUTOINCREMENT for gap-less sequences.
        """
        return ""


class IsccIDField(models.BinaryField):
    """Store ISCC-IDs as 8-byte binary data with string representation in Python."""

    description = "ISCC-ID stored as 8-byte binary"

    def __init__(self, *args, **kwargs):
        # type: (*object, **object) -> None
        """Initialize ISCCIDField with fixed 8-byte length."""
        kwargs["max_length"] = 8
        # ISCC-IDs are auto-generated unique identifiers, so enforce constraints
        kwargs.setdefault("editable", False)
        kwargs.setdefault("null", False)
        kwargs.setdefault("blank", False)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        # type: (object) -> str | None
        """Convert value to ISCC-ID string format."""
        if value is None:
            return None

        if isinstance(value, str):
            if value == "":
                return None
            # Validate ISCC-ID format
            if not value.startswith("ISCC:"):
                raise ValidationError(
                    "Invalid ISCC-ID format. Must start with 'ISCC:'",
                    code="invalid_iscc_format",
                )
            # Validate by attempting to create IsccID instance
            try:
                IsccID(value)
            except Exception as e:
                raise ValidationError(
                    f"Invalid ISCC-ID: {e}",
                    code="invalid_iscc",
                ) from e
            return value

        if isinstance(value, bytes):
            if len(value) != 8:
                raise ValidationError(
                    "ISCC-ID body must be exactly 8 bytes",
                    code="invalid_length",
                )
            return str(IsccID(value))

        raise ValidationError(
            "ISCC-ID must be a string or bytes",
            code="invalid_type",
        )

    def from_db_value(self, value, expression, connection):
        # type: (bytes | None, object, object) -> str | None
        """Convert database bytes to ISCC-ID string."""
        if value is None:
            return None
        return str(IsccID(value))

    def get_prep_value(self, value):
        # type: (str | None) -> bytes | None
        """Convert ISCC-ID string to bytes for database storage."""
        if value is None or value == "":
            return None

        # If already bytes, validate and return
        if isinstance(value, bytes):
            if len(value) != 8:
                raise ValidationError(
                    "ISCC-ID body must be exactly 8 bytes",
                    code="invalid_length",
                )
            return value

        # Convert to python first to ensure validation
        python_value = self.to_python(value)
        if python_value is None:
            return None

        return bytes(IsccID(python_value))

    def formfield(self, **kwargs):
        # type: (**object) -> CharField
        """Return a CharField for forms and admin interface."""
        defaults = {
            "form_class": CharField,
            "max_length": 25,  # ISCC-ID string max length
        }
        defaults.update(kwargs)
        return super(models.BinaryField, self).formfield(**defaults)
