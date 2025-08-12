"""
Online state validation for ISCC declarations.

This module provides validation functions that check against the current
state in the database to prevent duplicate submissions and ensure data
integrity.
"""

from django.db import transaction

from iscc_hub.models import IsccDeclaration


class StateValidationError(ValueError):
    """
    Raised when state validation fails.
    """

    def __init__(self, code, message):
        # type: (str, str) -> None
        """Initialize state validation error with code and message."""
        self.code = code
        self.message = message
        super().__init__(message)


def check_nonce_unused(nonce):
    # type: (str) -> None
    """
    Check that the nonce has not already been used.

    :param nonce: The 128-bit hex-encoded nonce to check
    :raises StateValidationError: If nonce already exists
    """
    if IsccDeclaration.objects.filter(nonce=nonce).exists():
        raise StateValidationError(code="NONCE_REUSE", message=f"Nonce already used: {nonce}")


def check_duplicate_declaration(iscc_code, actor):
    # type: (str, str) -> None
    """
    Check that the same actor hasn't already declared this ISCC-CODE.

    :param iscc_code: The ISCC-CODE to check
    :param actor: The actor's public key
    :raises StateValidationError: If duplicate declaration exists
    """
    if IsccDeclaration.objects.filter(iscc_code=iscc_code, actor=actor, deleted=False).exists():
        raise StateValidationError(
            code="DUPLICATE_DECLARATION", message=f"ISCC-CODE already declared by this actor: {iscc_code}"
        )


def check_duplicate_datahash(datahash, actor):
    # type: (str, str) -> None
    """
    Check that the same actor hasn't already declared this datahash.

    :param datahash: The datahash to check
    :param actor: The actor's public key
    :raises StateValidationError: If duplicate datahash exists
    """
    if IsccDeclaration.objects.filter(datahash=datahash, actor=actor, deleted=False).exists():
        raise StateValidationError(
            code="DUPLICATE_DATAHASH", message=f"Datahash already declared by this actor: {datahash}"
        )


def check_iscc_id_exists(iscc_id):
    # type: (str) -> bool
    """
    Check if an ISCC-ID already exists in the database.

    :param iscc_id: The ISCC-ID to check
    :return: True if exists, False otherwise
    """
    return IsccDeclaration.objects.filter(iscc_id=iscc_id).exists()


def get_declaration_by_iscc_id(iscc_id):
    # type: (str) -> IsccDeclaration|None
    """
    Get a declaration by its ISCC-ID.

    :param iscc_id: The ISCC-ID to retrieve
    :return: IsccDeclaration instance or None if not found
    """
    try:
        return IsccDeclaration.objects.get(iscc_id=iscc_id)
    except IsccDeclaration.DoesNotExist:
        return None


def validate_state(iscc_note, actor, iscc_id=None):
    # type: (dict, str, str|None) -> None
    """
    Perform all state validations for an IsccNote.

    This function should be called within a transaction to ensure
    consistency between validation and the subsequent write operation.

    :param iscc_note: The IsccNote dictionary to validate
    :param actor: The actor's public key
    :param iscc_id: Optional ISCC-ID for update operations
    :raises StateValidationError: If any state validation fails
    """
    # For updates, check if the ISCC-ID exists and belongs to the same actor
    if iscc_id:
        declaration = get_declaration_by_iscc_id(iscc_id)
        if not declaration:
            raise StateValidationError(code="NOT_FOUND", message=f"ISCC-ID not found: {iscc_id}")
        if declaration.actor != actor:
            raise StateValidationError(
                code="UNAUTHORIZED", message="Cannot update declaration owned by another actor"
            )
        # For updates, we don't check nonce uniqueness (it's a new nonce)
        # But we do check that the new nonce is not already used
        check_nonce_unused(iscc_note["nonce"])
        return

    # For new declarations, check all uniqueness constraints
    check_nonce_unused(iscc_note["nonce"])
    check_duplicate_declaration(iscc_note["iscc_code"], actor)
    check_duplicate_datahash(iscc_note["datahash"], actor)


def validate_state_atomic(iscc_note, actor, iscc_id=None):
    # type: (dict, str, str|None) -> None
    """
    Perform state validations within a database transaction.

    This ensures that the validation and subsequent operations are atomic,
    preventing race conditions in concurrent scenarios.

    :param iscc_note: The IsccNote dictionary to validate
    :param actor: The actor's public key
    :param iscc_id: Optional ISCC-ID for update operations
    :raises StateValidationError: If any state validation fails
    """
    with transaction.atomic():
        validate_state(iscc_note, actor, iscc_id)
