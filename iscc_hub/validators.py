"""Custom IsccNote validation module for granular control and signature integrity preservation."""

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import iscc_core as ic
import iscc_crypto as icr
import uritemplate
from dateutil.parser import isoparse

from iscc_hub.exceptions import (
    FieldValidationError,
    HashError,
    HexFormatError,
    IsccCodeError,
    IsccIdError,
    LengthError,
    NonceError,
    SignatureError,
    TimestampError,
    ValidationError,
)
from iscc_hub.iscc_id import IsccID

# Constants for better maintainability
DATAHASH_PREFIX = "1e20"
HASH_LENGTH = 68
NONCE_LENGTH = 32
SUPPORTED_GATEWAY_VARIABLES = {"iscc_id", "iscc_code", "datahash"}
SUPPORTED_URL_SCHEMES = ["http", "https"]
MAX_HUB_ID = 4095  # 12-bit maximum (2^12 - 1)
SIGNATURE_VERSION = "ISCC-SIG v1.0"
MAX_UNITS_ARRAY_SIZE = 4  # Prevent DOS attacks
MAX_STRING_LENGTH = 2048  # Maximum length for string fields

# Allowlists for the declared `$schema` wire value (matches the published schemas' const)
SUPPORTED_ISCC_NOTE_SCHEMAS = {"http://purl.org/iscc/schema/iscc-note-0.8.0.json"}
SUPPORTED_ISCC_NOTE_DELETE_SCHEMAS = {"http://purl.org/iscc/schema/iscc-note-delete-0.8.0.json"}


def deserialize_request(data, max_size=8192):
    # type: (bytes, int) -> dict
    """
    Safely deserialize JSON request body with size limit.

    :param data: Raw request body bytes
    :param max_size: Maximum allowed request size in bytes
    :return: Deserialized JSON dictionary
    :raises ValidationError: If request is too large or invalid JSON
    """
    import json

    if not isinstance(data, bytes):
        raise ValidationError("Request body must be bytes", code="invalid_type")

    # Check size before deserialization to prevent DOS
    if len(data) > max_size:
        raise ValidationError(f"Request body exceeds maximum size of {max_size} bytes", code="invalid_length")

    # Parse JSON
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValidationError("Invalid JSON in request body", code="invalid_format") from e


def validate_iscc_note(
    data, verify_signature=True, verify_hub_id=None, require_timestamp=False, timestamp_tolerance_seconds=0
):
    # type: (bytes, bool, int|None, bool, int) -> dict
    """
    Validate an IsccNote request body with comprehensive security checks.

    Performs format validation, cryptographic verification, and security checks on ISCC
    declaration data before notarization. Validates field formats, timestamps, signatures,
    and ensures data integrity between related fields.

    :param data: Raw request body bytes
    :param verify_signature: Whether to verify the cryptographic signature (default: True)
    :param verify_hub_id: Hub ID to validate nonce against (0-4095, default: None)
    :param require_timestamp: Whether a declarer-supplied timestamp is required (default: False)
    :param timestamp_tolerance_seconds: Max deviation (s) for a provided timestamp; ≤0 disables (default: 0)
    :return: Validated IsccNote data ready for notarization
    :raises ValidationError: If validation fails with detailed error information
    """
    # Deserialize with size check
    data_dict = deserialize_request(data)

    # Validate allowed fields and basic structure ($context/@type and any other key are rejected here)
    allowed_fields = {
        "$schema",
        "iscc_code",
        "datahash",
        "nonce",
        "timestamp",
        "signature",
        "units",
        "metahash",
        "gateway",
    }
    validate_structure(data_dict, allowed_fields)

    # Validate required fields (timestamp is optional, governed by server policy below)
    required_fields = {"$schema", "iscc_code", "datahash", "nonce", "signature"}
    validate_required_fields(data_dict, required_fields)

    # Validate the declared $schema against the allowlist
    validate_schema_uri(data_dict["$schema"], SUPPORTED_ISCC_NOTE_SCHEMAS)

    # Validate ISCC-CODE
    validate_iscc_code(data_dict["iscc_code"])

    # Validate datahash
    validate_multihash(data_dict["datahash"], "datahash")

    # Validate nonce
    validate_nonce(data_dict["nonce"], verify_hub_id)

    # Validate timestamp (policy-driven; optional unless required by server policy)
    validate_timestamp_policy(data_dict, require_timestamp, timestamp_tolerance_seconds)

    # Validate optional fields
    validate_optional_fields(data_dict)

    # Validate signature structure
    validate_signature_structure(data_dict["signature"])

    # Validate cross-field datahash match with ISCC-CODE
    validate_datahash_match(data_dict["iscc_code"], data_dict["datahash"])

    # Validate signature cryptographically if requested
    if verify_signature:
        verify_signature_cryptographically(data_dict)

    return data_dict


def validate_iscc_note_delete(
    data, verify_signature=True, verify_hub_id=None, require_timestamp=False, timestamp_tolerance_seconds=0
):
    # type: (bytes, bool, int|None, bool, int) -> dict
    """
    Validate an IsccNoteDelete request body for ISCC-ID deletion.

    Performs format validation and cryptographic verification on ISCC deletion
    requests. Validates required fields, timestamps, signatures, and ensures
    the ISCC-ID format is correct. A deletion is a deliberate signed act, so
    ``timestamp`` is always required regardless of the IsccNote server policy.

    :param data: Raw request body bytes
    :param verify_signature: Whether to verify the cryptographic signature (default: True)
    :param verify_hub_id: Hub ID to validate nonce against (0-4095, default: None)
    :param require_timestamp: Whether a missing timestamp is rejected (default: False)
    :param timestamp_tolerance_seconds: Max deviation (s) for the provided timestamp; ≤0 disables (default: 0)
    :return: Validated IsccNoteDelete data ready for deletion processing
    :raises ValidationError: If validation fails with detailed error information
    """
    # Deserialize with size check
    data_dict = deserialize_request(data)

    # Validate allowed fields and basic structure (@context/@type and any other key are rejected here)
    allowed_fields = {"$schema", "iscc_id", "nonce", "timestamp", "signature"}
    validate_structure(data_dict, allowed_fields)

    # Validate required fields for delete (timestamp stays mandatory for deletions)
    required_fields = {"$schema", "iscc_id", "nonce", "timestamp", "signature"}
    validate_required_fields(data_dict, required_fields)

    # Validate the declared $schema against the allowlist
    validate_schema_uri(data_dict["$schema"], SUPPORTED_ISCC_NOTE_DELETE_SCHEMAS)

    # Validate ISCC-ID format
    validate_iscc_id(data_dict["iscc_id"], verify_hub_id)

    # Validate nonce
    validate_nonce(data_dict["nonce"], verify_hub_id)

    # Validate timestamp (present via required fields; range-checked when tolerance enabled)
    validate_timestamp_policy(data_dict, require_timestamp, timestamp_tolerance_seconds)

    # Validate signature structure
    validate_signature_structure(data_dict["signature"])

    # Validate signature cryptographically if requested
    if verify_signature:
        verify_signature_cryptographically(data_dict)

    return data_dict


def validate_structure(data, allowed_fields):
    # type: (dict, set) -> None
    """
    Validate basic structure and field constraints.

    :param data: The data dictionary to validate
    :param allowed_fields: Set of allowed field names
    :raises ValidationError: If structure is invalid or contains unknown fields
    """
    # Ensure data is a dictionary
    if not isinstance(data, dict):
        raise ValidationError(f"Invalid input: expected JSON object, got {type(data).__name__}", code="invalid_type")

    # Check for unknown fields
    unknown_fields = set(data.keys()) - allowed_fields
    if unknown_fields:
        raise ValidationError(
            f"Unknown fields not allowed: {', '.join(sorted(unknown_fields))}", code="validation_failed"
        )

    # Check string field lengths
    for key, value in data.items():
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            raise LengthError(key, f"Field '{key}' exceeds maximum string length of {MAX_STRING_LENGTH}")


def validate_required_fields(data, required_fields=None):
    # type: (dict, set|None) -> None
    """
    Validate presence of all required fields.

    :param data: The data dictionary to validate
    :param required_fields: Set of required field names (optional, defaults to IsccNote fields)
    :raises FieldValidationError: If any required field is missing
    """
    if required_fields is None:
        # Default to IsccNote fields for backward compatibility
        required_fields = {"iscc_code", "datahash", "nonce", "timestamp", "signature"}
    for field in required_fields:
        if field not in data:
            raise FieldValidationError(field, f"Missing required field: {field}", code="validation_failed")


def validate_schema_uri(value, supported):
    # type: (str, set[str]) -> None
    """
    Validate the declared `$schema` URI against an allowlist.

    The Hub admits only declarations that name a published schema it supports. The
    wire value must match exactly (it mirrors each published schema's `$schema` const).

    :param value: The `$schema` value carried in the message
    :param supported: Set of accepted `$schema` URIs
    :raises FieldValidationError: If the value is not a string in the allowlist
    """
    if not isinstance(value, str) or value not in supported:
        raise FieldValidationError("$schema", f"Unsupported $schema: {value}", code="validation_failed")


def validate_iscc_code(iscc_code):
    # type: (str) -> None
    """
    Validate ISCC code format and type.

    Validates that the ISCC code is a composite ISCC-CODE (MainType ISCC).
    Individual ISCC-UNITs should be placed in the units array field.

    :param iscc_code: The ISCC code string to validate
    :raises IsccCodeError: If ISCC code is invalid or not composite type
    """
    # Ensure iscc_code is a string
    if not isinstance(iscc_code, str):
        raise IsccCodeError(f"ISCC code must be a string, got {type(iscc_code).__name__}")

    try:
        ic.iscc_validate(iscc_code, strict=True)
    except (ValueError, TypeError) as e:
        raise IsccCodeError("Invalid ISCC code format") from e

    # Check that the ISCC is of MainType ISCC (composite)
    fields = ic.iscc_decode(iscc_code)
    if fields[0] != ic.MT.ISCC:
        raise IsccCodeError("ISCC code must be of MainType ISCC (composite)")


def validate_nonce(nonce, hub_id=None):
    # type: (str, int|None) -> None
    """
    Validate nonce format and optionally check hub ID match.

    Validates that nonce is a 128-bit hex string where the first 12 bits
    match the target hub ID (for replay attack prevention).

    :param nonce: The 32-character hex nonce string
    :param hub_id: Optional hub ID (0-4095) to validate against
    :raises NonceError: If nonce format is invalid or hub ID doesn't match
    """
    if not isinstance(nonce, str):
        raise NonceError("nonce must be a string")

    validate_hex_string(nonce, "nonce", NONCE_LENGTH)

    # Validate hub ID if provided
    if hub_id is not None:
        validate_nonce_hub_id(nonce, hub_id)


def validate_nonce_hub_id(nonce, expected_hub_id):
    # type: (str, int) -> None
    """
    Validate that nonce contains the expected hub ID.

    Extracts the first 12 bits from the nonce and verifies they match the
    expected hub ID. Hub IDs must be in range 0-4095 (12-bit values).

    :param nonce: The 32-character hex nonce string
    :param expected_hub_id: The expected hub ID (0-4095)
    :raises ValidationError: If hub ID is out of range
    :raises NonceError: If hub ID doesn't match nonce
    """
    # Validate hub ID range
    if not 0 <= expected_hub_id <= MAX_HUB_ID:
        raise ValidationError(
            f"Hub ID must be between 0 and {MAX_HUB_ID}, got {expected_hub_id}", code="validation_failed"
        )

    # Extract hub ID from first 12 bits of nonce
    nonce_bytes = bytes.fromhex(nonce)
    extracted_hub_id = (nonce_bytes[0] << 4) | (nonce_bytes[1] >> 4)
    # Note: extracted_hub_id is guaranteed to be 0-4095 (12 bits max)

    if extracted_hub_id != expected_hub_id:
        raise NonceError(
            f"Nonce hub_id mismatch: expected {expected_hub_id}, got {extracted_hub_id}", is_mismatch=True
        )


def validate_timestamp_policy(data, require_timestamp, tolerance_seconds):
    # type: (dict, bool, int) -> None
    """
    Apply the Hub timestamp policy to a parsed message.

    An omitted timestamp is accepted unless required by policy. A present timestamp
    is always format-checked and range-checked when tolerance is enabled, even when
    the policy did not demand one. An explicit ``null`` is treated as present (not
    omitted) and rejected, since the wire schema types the field as a string.

    :param data: The parsed message dictionary
    :param require_timestamp: Whether an omitted timestamp is rejected
    :param tolerance_seconds: Max deviation (s) for a provided timestamp; ≤0 disables
    :raises TimestampError: If a present timestamp is malformed (incl. null) or out of range
    :raises FieldValidationError: If timestamp is omitted but required by policy
    """
    if "timestamp" not in data:
        if require_timestamp:
            raise FieldValidationError("timestamp", "timestamp is required by server policy", code="validation_failed")
    else:
        # Present (possibly null): a declarer-supplied timestamp MUST be a string.
        validate_timestamp(data["timestamp"], tolerance_seconds)


def validate_timestamp(timestamp_str, tolerance_seconds=0, reference_time=None):
    # type: (str, int, datetime|None) -> None
    """
    Validate timestamp format and optionally check it is within tolerance.

    Timestamp must be RFC 3339 formatted in UTC with millisecond precision.
    Format: YYYY-MM-DDTHH:MM:SS.sssZ. The format is always enforced; the range
    check runs only when ``tolerance_seconds`` is greater than zero.

    :param timestamp_str: The timestamp string to validate
    :param tolerance_seconds: Max allowed deviation in seconds; ≤0 disables the range check (default: 0)
    :param reference_time: Reference time for tolerance check (default: current UTC time)
    :raises TimestampError: If timestamp is invalid or outside tolerance
    """
    if not isinstance(timestamp_str, str):
        raise TimestampError("timestamp must be a string")

    # Check basic requirements
    if not timestamp_str.endswith("Z"):
        raise TimestampError("timestamp must end with 'Z' to indicate UTC")

    if "." not in timestamp_str:
        raise TimestampError("timestamp must include millisecond precision")

    # Parse timestamp using dateutil's RFC 3339 parser
    try:
        parsed_time = isoparse(timestamp_str)

        # Check millisecond precision (3 decimal places)
        ms_part = timestamp_str.split(".")[1].rstrip("Z")
        if len(ms_part) != 3:
            raise TimestampError("timestamp must have exactly 3 digits for milliseconds")

    except (ValueError, TypeError) as e:
        if isinstance(e, TimestampError):
            raise
        raise TimestampError("timestamp must be RFC 3339 formatted (e.g., '2025-08-04T12:34:56.789Z')") from e

    # Range-check only when a positive tolerance is configured (≤0 disables)
    if tolerance_seconds > 0:
        # Use provided reference time or current UTC time
        ref_time = reference_time if reference_time else datetime.now(UTC)

        # Calculate time difference
        time_diff = abs((parsed_time - ref_time).total_seconds())

        if time_diff > tolerance_seconds:
            raise TimestampError(
                f"timestamp is outside ±{tolerance_seconds} second tolerance: {time_diff:.1f} seconds",
                out_of_range=True,
            )


def validate_hex_string(value, field_name, expected_length):
    # type: (str, str, int) -> None
    """
    Validate a hex string has correct format.

    Ensures hex strings are lowercase, have the expected length, and contain
    only valid hexadecimal characters (0-9, a-f).

    :param value: The hex string to validate
    :param field_name: Name of the field for error messages
    :param expected_length: Expected character length of the hex string
    :raises HexFormatError: If hex string format is invalid
    :raises LengthError: If hex string has incorrect length
    """
    # Check lowercase
    if value != value.lower():
        raise HexFormatError(field_name, f"{field_name} must be lowercase")

    # Check length
    if len(value) != expected_length:
        raise LengthError(field_name, f"{field_name} must be exactly {expected_length} characters")

    # Check hex characters
    try:
        int(value, 16)
    except ValueError as e:
        raise HexFormatError(field_name, f"{field_name} must contain only hexadecimal characters") from e


def validate_optional_field(field_name, value, special_validators=None):
    # type: (str, Any, dict | None) -> None
    """
    Validate an optional field value.

    Ensures optional fields are not null, empty strings, or empty arrays.
    Applies field-specific validators when provided.

    :param field_name: Name of the field being validated
    :param value: The field value to validate
    :param special_validators: Dictionary of field-specific validator functions
    :raises FieldValidationError: If field value is invalid
    """
    # Check for null
    if value is None:
        raise FieldValidationError(
            field_name, f"Optional field '{field_name}' must not be null", code="validation_failed"
        )

    # Check for empty string or whitespace
    if isinstance(value, str) and not value.strip():
        raise FieldValidationError(
            field_name, f"Optional field '{field_name}' must not be empty", code="validation_failed"
        )

    # Check for empty array
    if isinstance(value, list) and len(value) == 0:
        raise FieldValidationError(
            field_name, f"Optional field '{field_name}' must not be empty", code="validation_failed"
        )

    # Apply special validation if provided
    if special_validators and field_name in special_validators:
        special_validators[field_name](value)


def validate_optional_fields(data):
    # type: (dict) -> None
    """
    Validate all optional fields in the IsccNote data.

    Validates gateway URLs/templates, metahash format, and units array.
    Ensures optional fields meet protocol requirements when present.

    :param data: The data dictionary containing optional fields
    :raises FieldValidationError: If any optional field validation fails
    :raises HashError: If metahash format is invalid
    """
    # Create validators dict for special field validation
    validators = {
        "metahash": lambda v: validate_multihash(v, "metahash"),
        "gateway": validate_gateway,
        "units": lambda v: validate_units_reconstruction(v, data["datahash"], data["iscc_code"]),
    }

    # Validate optional fields in IsccNote
    optional_fields_iscc_note = {"gateway", "units", "metahash"}
    for field in optional_fields_iscc_note:
        if field in data:
            validate_optional_field(field, data[field], validators)


def validate_signature_structure(signature):
    # type: (dict) -> None
    """
    Validate signature structure, fields, and version.

    Validates required fields (version, proof, pubkey) and optional fields
    (controller, keyid). Ensures signature version matches expected format.

    :param signature: The signature dictionary to validate
    :raises SignatureError: If signature structure is invalid
    :raises FieldValidationError: If optional signature fields are invalid
    """
    if not isinstance(signature, dict):
        raise SignatureError("Signature must be a dictionary")

    # Check required fields in signature
    required_signature_fields = {"version", "proof", "pubkey"}
    for field in required_signature_fields:
        if field not in signature:
            raise SignatureError(f"Missing required field in signature: {field}")

    # Validate signature version
    if signature["version"] != SIGNATURE_VERSION:
        raise SignatureError(
            f"Invalid signature version: expected '{SIGNATURE_VERSION}', got '{signature['version']}'"
        )

    # Check optional fields in signature
    optional_fields_signature = {"controller", "keyid"}
    for field in optional_fields_signature:
        if field in signature:
            try:
                validate_optional_field(field, signature[field])
            except FieldValidationError as e:
                # Update message to be more specific for signature fields
                new_message = e.message.replace(f"Optional field '{field}'", f"Optional field '{field}' in signature")
                raise FieldValidationError(field, new_message, e.code) from e

    # Check for unknown fields in signature
    allowed_signature_fields = required_signature_fields | optional_fields_signature
    unknown_signature_fields = set(signature.keys()) - allowed_signature_fields
    if unknown_signature_fields:
        raise SignatureError(f"Unknown fields in signature not allowed: {', '.join(sorted(unknown_signature_fields))}")


def verify_signature_cryptographically(data):
    # type: (dict) -> None
    """
    Verify the cryptographic signature using Ed25519.

    Performs cryptographic verification of the JSON signature against the
    public key. Ensures data integrity and authenticity.

    :param data: The complete data dictionary including signature
    :raises SignatureError: If signature verification fails or errors occur
    """
    try:
        # Do not raise inside the verifier to allow consistent error handling here
        verification_result = icr.verify_json(data, identity_doc=None, raise_on_error=False)
    except Exception as e:
        # Normalize unexpected verifier errors
        raise SignatureError("Invalid signature") from e

    if not getattr(verification_result, "signature_valid", False):
        raise SignatureError("Invalid signature")


def validate_multihash(value, field_name):
    # type: (str, str) -> None
    """
    Validate a BLAKE3 multihash string (datahash or metahash).

    Validates that the hash is a 256-bit BLAKE3 multihash in lowercase hex
    format with the correct prefix (1e20).

    :param value: The hash value to validate
    :param field_name: Name of the field being validated (for error messages)
    :raises HashError: If hash format is invalid
    """
    # Check type
    if not isinstance(value, str):
        raise HashError(field_name, f"{field_name} must be a string")

    # Check lowercase
    if value != value.lower():
        raise HashError(field_name, f"{field_name} must be lowercase")

    # Check prefix (BLAKE3 multihash identifier)
    if not value.startswith(DATAHASH_PREFIX):
        raise HashError(field_name, f"{field_name} must start with '{DATAHASH_PREFIX}' (BLAKE3 multihash prefix)")

    # Check length
    if len(value) != HASH_LENGTH:
        raise HashError(field_name, f"{field_name} must be exactly {HASH_LENGTH} characters")

    # Check hex characters (skip the first 4 chars which are the prefix)
    try:
        int(value[4:], 16)
    except ValueError as e:
        raise HashError(field_name, f"{field_name} must contain only hexadecimal characters") from e


def validate_gateway(gateway):
    # type: (str) -> None
    """
    Validate that gateway is either a valid URL or URI template.

    Accepts HTTP/HTTPS URLs or RFC 6570 URI templates with supported variables:
    {iscc_id}, {iscc_code}, {datahash}

    Query parameters are allowed for both regular URLs and URI templates.

    :param gateway: The gateway URL or URI template string to validate
    :raises FieldValidationError: If gateway is invalid or uses unsupported variables
    """
    # Type guard (mirrors validate_multihash) so a non-string value is rejected, not crashed on
    if not isinstance(gateway, str):
        raise FieldValidationError("gateway", "gateway must be a string", code="invalid_format")

    # Check for restricted components
    url = urlparse(gateway)

    # Username and password are always restricted
    if url.username or url.password:
        component = "username" if url.username else "password"
        raise FieldValidationError("gateway", f"restricted URL {component} component", code="invalid_format")

    # Fragment is always restricted
    if url.fragment:
        raise FieldValidationError("gateway", "restricted URL fragment component", code="invalid_format")

    # Query parameters are allowed for all gateway URLs

    # Check for basic template syntax errors first
    if "{" in gateway or "}" in gateway:
        # Check for mismatched braces
        if gateway.count("{") != gateway.count("}"):
            raise FieldValidationError("gateway", "gateway has invalid URI template syntax", code="invalid_format")

    # Create URI template and extract variables
    template = uritemplate.URITemplate(gateway)
    variable_names = set(template.variable_names) if hasattr(template, "variable_names") else set()

    # If it has variables, validate them
    if variable_names:
        # Check for unsupported variables
        unsupported = variable_names - SUPPORTED_GATEWAY_VARIABLES
        if unsupported:
            unsupported_list = sorted(unsupported)
            raise FieldValidationError(
                "gateway",
                f"gateway contains unsupported variables: {', '.join(unsupported_list)}",
                code="invalid_format",
            )

        # Enforce allowed operators and forbid query/fragment-introducing operators, explode, and prefixes
        # Allowed operators: none (simple), '/' (path-segment), '.' (dot-prefix)
        # Disallowed operators: '+', ';', '?', '&', '#'
        # Disallow modifiers '*' (explode) and ':' (prefix length)
        expr_pattern = re.compile(r"\{([^}]+)\}")  # Changed to require at least one character
        for match in expr_pattern.finditer(gateway):
            inner = match.group(1)

            # Extract operator if present
            op = ""
            if inner[0] in "+#./;?&":
                op = inner[0]
                varspec = inner[1:]
            else:
                varspec = inner

            # Reject disallowed operators that introduce query/fragment
            if op in {"+", ";", "?", "&", "#"}:
                raise FieldValidationError(
                    "gateway",
                    f"gateway uses disallowed URI Template operator: '{op}'",
                    code="invalid_format",
                )

            # At this point, op can only be "", "/", or "." which are all allowed
            # No need for additional validation of the operator

            # For simplicity and safety, allow only a single variable per expression and no modifiers
            # (no explode '*' and no prefix length ':N').
            if "," in varspec:
                raise FieldValidationError(
                    "gateway",
                    "gateway template expressions must contain exactly one variable",
                    code="invalid_format",
                )

            if "*" in varspec or ":" in varspec:
                raise FieldValidationError(
                    "gateway",
                    "gateway template does not allow explode '*' or prefix length modifiers",
                    code="invalid_format",
                )

    # Regardless of template usage, must be a valid HTTP(S) URL
    validate_url(gateway)


def validate_url(url):
    # type: (str) -> None
    """
    Validate that a string is a valid HTTP(S) URL.

    Ensures URL has a valid HTTP/HTTPS scheme and hostname.

    :param url: The URL string to validate
    :raises FieldValidationError: If URL is invalid
    """
    # Reject any whitespace anywhere (matches the published anchored gateway pattern ^https?://[^\s]+$)
    if re.search(r"\s", url):
        raise FieldValidationError("gateway", "gateway must be a valid URL or URI template", code="invalid_format")

    # Parse URL
    parsed = urlparse(url)

    # Check if it has a valid scheme
    if parsed.scheme not in SUPPORTED_URL_SCHEMES:
        raise FieldValidationError("gateway", "gateway must be a valid URL or URI template", code="invalid_format")

    # Check if it has a hostname
    if not parsed.netloc:
        raise FieldValidationError("gateway", "gateway must be a valid URL or URI template", code="invalid_format")


def validate_units_reconstruction(units, datahash, iscc_code):
    # type: (list, str, str) -> None
    """
    Validate that units array and datahash can reconstruct the provided iscc_code.

    Validates that the provided ISCC-UNITs plus the Instance-Code derived from
    datahash can reconstruct the original ISCC-CODE. Ensures units have ISCC-BODYs
    larger than 64-bit for improved discovery. Limits array size to prevent DOS.

    :param units: List of ISCC unit strings (excluding Instance-Code)
    :param datahash: Pre-validated datahash string
    :param iscc_code: Original ISCC-CODE to validate against
    :raises FieldValidationError: If reconstruction fails or units contain invalid ISCC codes
    """
    # Input validation
    if not isinstance(units, list):
        raise FieldValidationError("units", "units must be a list", code="invalid_format")

    # Check array size limit
    if len(units) > MAX_UNITS_ARRAY_SIZE:
        raise FieldValidationError(
            "units", f"units array exceeds maximum size of {MAX_UNITS_ARRAY_SIZE}", code="invalid_length"
        )

    # Validate that all units are strings
    for i, unit in enumerate(units):
        if not isinstance(unit, str):
            raise FieldValidationError("units", f"units[{i}] must be a string", code="invalid_format")

    try:
        # Convert datahash to Instance-Code and add to units
        instance_code = datahash_to_instance_code(datahash)
        all_codes = units + [instance_code]

        # Check if the ISCC-CODE is WIDE subtype
        try:
            _, subtype, _, _, _ = ic.iscc_decode(iscc_code)
            is_wide = subtype == ic.ST_ISCC.WIDE
        except Exception:
            # If we can't decode, assume it's not WIDE
            is_wide = False

        # Attempt to reconstruct ISCC-CODE
        if is_wide:
            # Use gen_iscc_code_v0 with wide=True for WIDE subtype
            iscc_result = ic.gen_iscc_code_v0(all_codes, wide=True)
        else:
            # Use standard gen_iscc_code for normal ISCCs
            iscc_result = ic.gen_iscc_code(all_codes)
        reconstructed_iscc = iscc_result["iscc"]

        # Validate reconstruction matches original
        if reconstructed_iscc != iscc_code:
            raise FieldValidationError(
                "units",
                "ISCC code reconstruction failed: units and datahash do not reconstruct to provided iscc_code",
                code="validation_failed",
            )
    except (ValidationError, FieldValidationError):
        # Re-raise our validation errors as-is
        raise
    except ValueError as e:
        # Wrap iscc_core validation errors
        raise FieldValidationError("units", f"Invalid ISCC unit: {str(e)}", code="invalid_iscc") from e
    except Exception as e:
        # Wrap other unexpected exceptions
        raise FieldValidationError(
            "units",
            "ISCC code reconstruction failed: units and datahash do not reconstruct to provided iscc_code",
            code="validation_failed",
        ) from e


def datahash_to_instance_code(datahash):
    # type: (str) -> str
    """
    Convert a pre-validated datahash to an Instance-Code ISCC-UNIT.

    Removes the multihash prefix and encodes the hash as an ISCC Instance-Code
    unit for use in ISCC-CODE reconstruction.

    :param datahash: Pre-validated datahash string (68 chars with 1e20 prefix)
    :return: The Instance-Code ISCC-UNIT string (e.g. "ISCC:IAA...")
    """
    # Remove multihash prefix (first 4 characters: "1e20")
    hash_hex = datahash[4:]

    # Decode hex to bytes
    hash_bytes = bytes.fromhex(hash_hex)

    # Use iscc_core.encode_component to build the ISCC-UNIT
    instance_code = ic.encode_component(
        mtype=ic.MT.INSTANCE,
        stype=ic.ST.NONE,
        version=ic.VS.V0,
        bit_length=256,
        digest=hash_bytes,
    )

    return f"ISCC:{instance_code}"


def validate_datahash_match(iscc_code, datahash):
    # type: (str, str) -> None
    """
    Validate that datahash matches the Instance-Code portion of the ISCC-CODE.

    For standard ISCCs: Compares first 64 bits of datahash with Instance-Code.
    For WIDE ISCCs: Compares first 128 bits of datahash with Instance-Code.
    This ensures the ISCC-CODE was derived from the declared content hash.

    :param iscc_code: Pre-validated ISCC-CODE string
    :param datahash: Pre-validated datahash string (with "1e20" prefix)
    :raises HashError: If datahash does not match ISCC Instance-Code
    :raises IsccCodeError: If ISCC code is invalid
    """
    try:
        # Remove multihash prefix from datahash
        datahash_bytes = bytes.fromhex(datahash[4:])

        # Check the composite ISCC-CODE's subtype to determine comparison method
        composite_decoded = ic.iscc_decode(iscc_code)
        _, composite_subtype, _, _, _ = composite_decoded

        # Decompose ISCC-CODE to get individual units
        units = ic.iscc_decompose(iscc_code)

        # Get the last unit (always Instance-Code for valid composite ISCCs)
        instance_code = units[-1]
        instance_decoded = ic.iscc_decode(instance_code)

        # Extract Instance-Code data
        _, _, _, _, instance_digest = instance_decoded

        # Determine comparison length based on composite ISCC subtype
        if composite_subtype == ic.ST_ISCC.WIDE:
            # For WIDE subtype, compare 128 bits (16 bytes)
            comparison_bits = 128
            comparison_bytes = 16
        else:
            # For normal subtypes, compare 64 bits (8 bytes)
            comparison_bits = 64
            comparison_bytes = 8

        # Compare the relevant portions
        if instance_digest[:comparison_bytes] != datahash_bytes[:comparison_bytes]:
            raise HashError(
                "datahash",
                f"datahash does not match ISCC Instance-Code: "
                f"expected first {comparison_bits} bits of datahash to match "
                f"first {comparison_bits} bits of Instance-Code",
            )
    except (ValidationError, FieldValidationError, HashError):
        # Re-raise our validation errors
        raise
    except ValueError as e:
        # Convert iscc_core validation errors to our format
        raise IsccCodeError(f"Invalid ISCC code: {str(e)}") from e


def validate_iscc_id(iscc_id, hub_id=None):
    # type: (str, int|None) -> None
    """
    Validate ISCC-ID format and optionally check hub ID match.

    Validates that the ISCC-ID has the correct MainType (ID) and version (V1).
    Optionally validates that the embedded hub ID matches the expected value.

    :param iscc_id: The ISCC-ID string to validate
    :param hub_id: Optional hub ID (0-4095) to validate against embedded value
    :raises IsccIdError: If ISCC-ID format is invalid or hub ID doesn't match
    """
    try:
        mt, st, vs, ln, body = ic.iscc_decode(iscc_id)
        if mt != ic.MT.ID or vs != ic.VS.V1:
            raise
    except Exception as e:
        raise IsccIdError("Invalid ISCC-ID format") from e

    if hub_id is not None:
        iscc_id_obj = IsccID(iscc_id)
        if iscc_id_obj.hub_id != hub_id:
            raise IsccIdError(f"ISCC-ID with invalid hub_id {iscc_id_obj.hub_id}")
