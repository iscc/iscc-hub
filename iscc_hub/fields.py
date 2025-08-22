import binascii

import base58
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

    def value_to_string(self, obj):
        # type: (object) -> str | None
        """Convert field value to string for serialization."""
        value = self.value_from_object(obj)  # type: ignore[arg-type]
        if value is None:
            return None
        # Return the ISCC-ID string representation for serialization
        return str(IsccID(value))

    def formfield(self, **kwargs):
        # type: (**object) -> CharField
        """Return a CharField for forms and admin interface."""
        defaults = {
            "form_class": CharField,
            "max_length": 25,  # ISCC-ID string max length
        }
        defaults.update(kwargs)
        return super(models.BinaryField, self).formfield(**defaults)


class HexField(models.BinaryField):
    """Store hex strings as binary data, cutting storage requirements in half."""

    description = "Hex string stored as binary"

    def to_python(self, value):
        # type: (object) -> bytes | None
        """Convert value to bytes, accepting hex string input transparently."""
        if value is None:
            return value

        if isinstance(value, bytes | bytearray | memoryview):
            return bytes(value)
        elif isinstance(value, str):
            if value == "":
                return None
            # Accept hex input transparently
            try:
                return binascii.unhexlify(value)
            except binascii.Error as e:
                raise ValidationError(f"Invalid hex: {e}", code="invalid_hex") from e
        else:
            raise ValidationError("Value must be bytes or hex string", code="invalid_type")

    def get_prep_value(self, value):
        # type: (object) -> bytes | None
        """Convert to bytes for database storage."""
        b = self.to_python(value) if value is not None else None
        return super().get_prep_value(b)

    def from_db_value(self, value, expression, connection):
        # type: (bytes | None, object, object) -> bytes | None
        """Return bytes from database."""
        return value

    def value_to_string(self, obj):
        # type: (object) -> str | None
        """Convert field value to hex string for serialization."""
        value = self.value_from_object(obj)  # type: ignore[arg-type]
        if value is None:
            return None
        # Convert bytes to hex string for serialization
        if isinstance(value, bytes):
            return value.hex()
        return str(value)

    def formfield(self, **kwargs):
        # type: (**object) -> CharField
        """Return a CharField for forms and admin interface."""
        defaults = {"form_class": CharField}  # type: dict[str, object]
        # If max_length is set, it refers to binary byte length
        # Hex string in forms will be 2x this length
        if self.max_length:
            defaults["max_length"] = self.max_length * 2
        defaults.update(kwargs)
        return super(models.BinaryField, self).formfield(**defaults)  # type: ignore[return-value]


class PubkeyField(models.BinaryField):
    """Store Multibase z-base58-btc encoded Ed25519 public keys as raw 32-byte binary data."""

    description = "Ed25519 public key stored as 32-byte binary"

    # Constants from iscc_crypto.keys
    PREFIX_PUBLIC_KEY = bytes.fromhex("ED01")

    def __init__(self, *args, **kwargs):
        # type: (*object, **object) -> None
        """Initialize PubkeyField with fixed 32-byte length."""
        kwargs["max_length"] = 32
        super().__init__(*args, **kwargs)

    def _validate_multibase(self, value):
        # type: (str) -> bytes
        """Validate and extract raw bytes from multibase encoded public key."""
        if not value.startswith("z"):
            raise ValidationError(
                "Invalid public key format - must start with 'z' (base58btc multibase prefix)",
                code="invalid_pubkey",
            )

        try:
            decoded = base58.b58decode(value[1:])
        except Exception as e:
            raise ValidationError(
                f"Invalid public key format: {e}",
                code="invalid_pubkey",
            ) from e

        if not decoded.startswith(self.PREFIX_PUBLIC_KEY):
            raise ValidationError(
                "Invalid public key format - not an Ed25519 public key",
                code="invalid_pubkey",
            )

        raw_bytes = decoded[2:]  # Skip the 2-byte prefix
        if len(raw_bytes) != 32:
            raise ValidationError(
                "Invalid public key format - must be exactly 32 bytes",
                code="invalid_pubkey",
            )

        return raw_bytes

    def _encode_to_multibase(self, raw_bytes):
        # type: (bytes) -> str
        """Encode raw 32-byte public key to multibase format."""
        if len(raw_bytes) != 32:
            raise ValidationError(
                "Public key must be exactly 32 bytes",
                code="invalid_length",
            )

        # Validate that the bytes can form a valid Ed25519 public key
        # This is a lightweight check - Ed25519 public keys can be any 32 bytes,
        # but we validate to catch potential issues early
        try:
            # Import here to avoid circular dependencies
            from cryptography.hazmat.primitives.asymmetric import ed25519

            ed25519.Ed25519PublicKey.from_public_bytes(raw_bytes)
        except Exception as e:
            raise ValidationError(
                f"Invalid public key bytes: {e}",
                code="invalid_pubkey_bytes",
            ) from e

        prefixed = self.PREFIX_PUBLIC_KEY + raw_bytes
        return "z" + base58.b58encode(prefixed).decode("utf-8")

    def to_python(self, value):
        # type: (object) -> str | None
        """Convert value to Multibase z-base58-btc encoded public key string."""
        if value is None:
            return None

        if isinstance(value, str):
            if value == "":
                return None
            # Validate format and return the encoded string
            self._validate_multibase(value)
            return value

        if isinstance(value, bytes):
            if len(value) != 32:
                raise ValidationError(
                    "Public key must be exactly 32 bytes",
                    code="invalid_length",
                )
            # Convert raw bytes to encoded string
            return self._encode_to_multibase(value)

        raise ValidationError(
            "Public key must be a string or bytes",
            code="invalid_type",
        )

    def from_db_value(self, value, expression, connection):
        # type: (bytes | None, object, object) -> str | None
        """Convert database bytes to Multibase encoded public key string."""
        if value is None:
            return None
        return self.to_python(value)

    def get_prep_value(self, value):
        # type: (str | None) -> bytes | None
        """Convert Multibase encoded public key string to raw bytes for database storage."""
        if value is None or value == "":
            return None

        # If already bytes, validate and return
        if isinstance(value, bytes):
            if len(value) != 32:
                raise ValidationError(
                    "Public key must be exactly 32 bytes",
                    code="invalid_length",
                )
            return value

        # Convert encoded string to raw bytes
        return self._validate_multibase(value)

    def value_to_string(self, obj):
        # type: (object) -> str | None
        """Convert field value to string for serialization."""
        value = self.value_from_object(obj)  # type: ignore[arg-type]
        if value is None:
            return None
        # Return the Multibase encoded string representation
        if isinstance(value, bytes):
            return self.to_python(value)
        return str(value)

    def formfield(self, **kwargs):
        # type: (**object) -> CharField
        """Return a CharField for forms and admin interface."""
        defaults = {
            "form_class": CharField,
            "max_length": 50,  # Multibase encoded pubkey max length
        }
        defaults.update(kwargs)
        return super(models.BinaryField, self).formfield(**defaults)
