"""Custom IsccNote validation module for granular control and signature integrity preservation."""

from typing import Any
from urllib.parse import urlparse

import iscc_core as ic
import iscc_crypto as icr
import uritemplate

# Constants for better maintainability
DATAHASH_PREFIX = "1e20"
HASH_LENGTH = 68
NONCE_LENGTH = 32
SUPPORTED_RESOLVER_VARIABLES = {"iscc_id", "iscc_code", "pubkey", "datahash"}
SUPPORTED_URL_SCHEMES = ["http", "https"]


def validate_iscc_note(data, verify_signature=True, verify_node_id=None):
    # type: (dict, bool, int|None) -> dict
    """
    Validate an IsccNote request body without using Pydantic.

    :param data: Raw dictionary containing the IsccNote fields
    :param verify_signature: Whether to verify the cryptographic signature (default: True)
    :param verify_node_id: Node ID to validate nonce against (default: None, skips validation)
    :return: Validated IsccNote data ready for notarization
    :raises ValueError: If validation fails with detailed error information
    """
    # Validate required fields
    validate_required_fields(data)

    # Validate ISCC-CODE
    validate_iscc_code(data["iscc_code"])

    # Validate datahash
    validate_multihash(data["datahash"], "datahash")

    # Validate nonce
    validate_nonce(data["nonce"], verify_node_id)

    # Validate optional fields
    validate_optional_fields(data)

    # Validate signature structure
    validate_signature_structure(data["signature"])

    # Validate cross-field datahash match with ISCC-CODE
    validate_datahash_match(data["iscc_code"], data["datahash"])

    # Validate signature cryptographically if requested
    if verify_signature:
        verify_signature_cryptographically(data)

    return data


def validate_required_fields(data):
    # type: (dict) -> None
    """Validate that all required fields are present."""
    required_fields = {"iscc_code", "datahash", "nonce", "timestamp", "signature"}
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")


def validate_iscc_code(iscc_code):
    # type: (str) -> None
    """Validate ISCC code format and type."""
    try:
        ic.iscc_validate(iscc_code, strict=True)
    except ValueError as e:
        raise ValueError("Invalid ISCC code") from e

    # Check that the ISCC is of MainType ISCC (composite)
    fields = ic.iscc_decode(iscc_code)
    if fields[0] != ic.MT.ISCC:
        raise ValueError("ISCC code must be of MainType ISCC")


def validate_nonce(nonce, node_id=None):
    # type: (str, int|None) -> None
    """Validate nonce format and optionally check node ID match."""
    if not isinstance(nonce, str):
        raise ValueError("nonce must be a string")

    validate_hex_string(nonce, "nonce", NONCE_LENGTH)

    # Validate node ID if provided
    if node_id is not None:
        validate_nonce_node_id(nonce, node_id)


def validate_nonce_node_id(nonce, expected_node_id):
    # type: (str, int) -> None
    """Validate that nonce contains the expected node ID."""
    # Extract node ID directly since we've already validated nonce format
    nonce_bytes = bytes.fromhex(nonce)
    extracted_node_id = (nonce_bytes[0] << 4) | (nonce_bytes[1] >> 4)

    if extracted_node_id != expected_node_id:
        raise ValueError(f"Nonce node_id mismatch: expected {expected_node_id}, got {extracted_node_id}")


def validate_hex_string(value, field_name, expected_length):
    # type: (str, str, int) -> None
    """Validate a hex string has correct format."""
    # Check lowercase
    if value != value.lower():
        raise ValueError(f"{field_name} must be lowercase")

    # Check length
    if len(value) != expected_length:
        raise ValueError(f"{field_name} must be exactly {expected_length} characters")

    # Check hex characters
    try:
        int(value, 16)
    except ValueError as e:
        raise ValueError(f"{field_name} must contain only hexadecimal characters") from e


def validate_optional_field(field_name, value, special_validators=None):
    # type: (str, Any, dict | None) -> None
    """Validate an optional field value."""
    # Check for null
    if value is None:
        raise ValueError(f"Optional field '{field_name}' must not be null")

    # Check for empty string or whitespace
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"Optional field '{field_name}' must not be empty")

    # Check for empty array
    if isinstance(value, list) and len(value) == 0:
        raise ValueError(f"Optional field '{field_name}' must not be empty")

    # Apply special validation if provided
    if special_validators and field_name in special_validators:
        special_validators[field_name](value)


def validate_optional_fields(data):
    # type: (dict) -> None
    """Validate all optional fields in the data."""
    # Define special validators for specific fields
    special_validators = {
        "metahash": lambda v: validate_multihash(v, "metahash"),
        "resolver": validate_resolver,
        "units": lambda v: validate_units_reconstruction(v, data["datahash"], data["iscc_code"]),
    }

    # Validate optional fields in IsccNote
    optional_fields_iscc_note = {"resolver", "units", "metahash"}
    for field in optional_fields_iscc_note:
        if field in data:
            validate_optional_field(field, data[field], special_validators)


def validate_signature_structure(signature):
    # type: (dict) -> None
    """Validate signature structure and fields."""
    if not isinstance(signature, dict):
        raise ValueError("Signature must be a dictionary")

    # Check required fields in signature
    required_signature_fields = {"version", "proof", "pubkey"}
    for field in required_signature_fields:
        if field not in signature:
            raise ValueError(f"Missing required field in signature: {field}")

    # Check optional fields in signature
    optional_fields_signature = {"controller", "keyid"}
    for field in optional_fields_signature:
        if field in signature:
            try:
                validate_optional_field(field, signature[field])
            except ValueError as e:
                # Re-raise with "in signature" suffix for clarity
                raise ValueError(str(e).replace(f"'{field}'", f"'{field}' in signature")) from e


def verify_signature_cryptographically(data):
    # type: (dict) -> None
    """Verify the cryptographic signature."""
    verification_result = icr.verify_json(data, identity_doc=None, raise_on_error=False)
    if not verification_result.signature_valid:
        raise ValueError("Invalid signature")


def validate_multihash(value, field_name):
    # type: (str, str) -> None
    """
    Validate a multihash string (datahash or metahash).

    :param value: The hash value to validate
    :param field_name: Name of the field being validated (for error messages)
    :raises ValueError: If validation fails
    """
    # Check type
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    # Check lowercase
    if value != value.lower():
        raise ValueError(f"{field_name} must be lowercase")

    # Check prefix
    if not value.startswith(DATAHASH_PREFIX):
        raise ValueError(f"{field_name} must start with '{DATAHASH_PREFIX}'")

    # Check length
    if len(value) != HASH_LENGTH:
        raise ValueError(f"{field_name} must be exactly {HASH_LENGTH} characters")

    # Check hex characters (skip the first 4 chars which are the prefix)
    try:
        int(value[4:], 16)
    except ValueError as e:
        raise ValueError(f"{field_name} must contain only hexadecimal characters") from e


def validate_resolver(resolver):
    # type: (str) -> None
    """
    Validate that resolver is either a valid URL or URI template.

    :param resolver: The resolver string to validate
    :raises ValueError: If resolver is invalid
    """
    # Check for basic template syntax errors first
    if "{" in resolver or "}" in resolver:
        # Check for mismatched braces
        if resolver.count("{") != resolver.count("}"):
            raise ValueError("resolver has invalid URI template syntax")

    # Create URI template and extract variables
    template = uritemplate.URITemplate(resolver)
    variable_names = template.variable_names if hasattr(template, "variable_names") else set()

    # If it has variables, validate them
    if variable_names:
        # Check for unsupported variables
        unsupported = variable_names - SUPPORTED_RESOLVER_VARIABLES
        if unsupported:
            unsupported_list = sorted(unsupported)
            raise ValueError(f"resolver contains unsupported variables: {', '.join(unsupported_list)}")
        # Valid template with supported variables
        return

    # If no template variables, validate as plain URL
    validate_url(resolver)


def validate_url(url):
    # type: (str) -> None
    """
    Validate that a string is a valid HTTP(S) URL.

    :param url: The URL string to validate
    :raises ValueError: If URL is invalid
    """
    # Check for whitespace
    if url != url.strip():
        raise ValueError("resolver must be a valid URL or URI template")

    # Parse URL
    parsed = urlparse(url)

    # Check if it has a valid scheme
    if parsed.scheme not in SUPPORTED_URL_SCHEMES:
        raise ValueError("resolver must be a valid URL or URI template")

    # Check if it has a hostname
    if not parsed.netloc:
        raise ValueError("resolver must be a valid URL or URI template")


def validate_units_reconstruction(units, datahash, iscc_code):
    # type: (list, str, str) -> None
    """
    Validate that units array and datahash can reconstruct the provided iscc_code.

    This function validates the assumption that if units are provided, converting the
    datahash to an Instance-Code ISCC-UNIT and appending it to the units array should
    allow reconstruction of an ISCC-CODE identical to the provided iscc_code using
    ic.gen_iscc_code.

    :param units: List of ISCC unit strings (excluding Instance-Code)
    :param datahash: Pre-validated datahash string
    :param iscc_code: Original ISCC-CODE to validate against
    :raises ValueError: If reconstruction fails or units contain invalid ISCC codes
    """
    # Input validation
    if not isinstance(units, list):
        raise ValueError("units must be a list")

    # Empty check is already done by _validate_optional_field

    # Validate that all units are strings
    for i, unit in enumerate(units):
        if not isinstance(unit, str):
            raise ValueError(f"units[{i}] must be a string")

    try:
        # Convert datahash to Instance-Code and add to units
        instance_code = datahash_to_instance_code(datahash)
        all_codes = units + [instance_code]

        # Attempt to reconstruct ISCC-CODE
        iscc_result = ic.gen_iscc_code(all_codes)
        reconstructed_iscc = iscc_result["iscc"]

        # Validate reconstruction matches original
        if reconstructed_iscc != iscc_code:
            raise ValueError(
                "ISCC code reconstruction failed: units and datahash do not reconstruct to provided iscc_code"
            )
    except ValueError as e:
        # Re-raise ISCC library validation errors as-is for better debugging
        if "Malformed ISCC string" in str(e):
            raise
        # Re-raise our custom validation messages as-is
        raise
    except Exception as e:
        # Wrap other unexpected exceptions
        raise ValueError(
            "ISCC code reconstruction failed: units and datahash do not reconstruct to provided iscc_code"
        ) from e


def datahash_to_instance_code(datahash):
    # type: (str) -> str
    """
    Convert a pre-validated datahash to an Instance-Code ISCC-UNIT.

    This function expects a pre-validated datahash string that:
    - Is a valid multihash with prefix "1e20"
    - Contains only lowercase hexadecimal characters
    - Has the correct length (68 characters)

    :param datahash: Pre-validated datahash string (with multihash prefix)
    :return: The Instance-Code ISCC-UNIT string
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

    For normal ISCCs: last 64 bits of ISCC must match first 64 bits of datahash.
    For WIDE ISCCs: last 128 bits of ISCC must match first 128 bits of datahash.

    Assumes both iscc_code and datahash have been pre-validated and that the
    ISCC-CODE was validated to be a composite ISCC (MainType ISCC).

    :param iscc_code: Pre-validated ISCC-CODE string
    :param datahash: Pre-validated datahash string (with "1e20" prefix)
    :raises ValueError: If datahash does not match ISCC Instance-Code
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
            raise ValueError(
                f"datahash does not match ISCC Instance-Code: "
                f"expected first {comparison_bits} bits of datahash to match "
                f"first {comparison_bits} bits of Instance-Code"
            )
    except ValueError as e:
        # Re-raise our custom error messages
        if "datahash does not match" in str(e):
            raise
        # Convert iscc_core validation errors to our format
        raise ValueError(f"Invalid ISCC code: {str(e)}") from e
