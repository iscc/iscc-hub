import json
import re

import iscc_core as ic
import iscc_crypto as icr
from constance import config
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from ninja import NinjaAPI
from ninja.responses import Status, codes_4xx

import iscc_hub
from iscc_hub.exceptions import BaseApiException, DuplicateDeclarationError, NotFoundError, UnauthorizedError
from iscc_hub.gateway import expand_gateway_url
from iscc_hub.iscc_id import IsccID
from iscc_hub.models import Event, Hub, IsccDeclaration, PubKey
from iscc_hub.receipt import build_iscc_receipt
from iscc_hub.schema import ErrorResponse, IsccReceipt
from iscc_hub.schema import IsccDeclaration as IsccDeclarationSchema
from iscc_hub.sequencer import sequence_iscc_delete, sequence_iscc_note
from iscc_hub.validators import validate_iscc_note, validate_iscc_note_delete

api = NinjaAPI(
    title="ISCC Notary API",
    version=iscc_hub.__version__,
    description="Sign, timestamp, and discover content using ISCC",
)


@api.exception_handler(BaseApiException)
def handle_api_exception(request, exc):
    # type: (HttpRequest, BaseApiException) -> object
    """
    Handle all BaseApiException and subclasses with appropriate HTTP responses.

    :param request: The incoming HTTP request
    :param exc: The exception instance
    :return: JSON response with error details and appropriate status code
    """
    return api.create_response(
        request,
        exc.to_error_response(),
        status=exc.status_code,
    )


def declaration_to_dict(decl):
    # type: (IsccDeclaration) -> dict
    """
    Convert an IsccDeclaration model instance to a JSON-serializable dict.

    :param decl: IsccDeclaration model instance
    :return: Dictionary with declaration data and expanded gateway URL
    """
    iscc_id_obj = IsccID(decl.iscc_id)
    iscc_id_canonical = str(iscc_id_obj)

    # Prepare clean versions for template variable substitution (lowercase without prefix)
    iscc_id_clean = (
        iscc_id_canonical[5:].lower() if iscc_id_canonical.startswith("ISCC:") else iscc_id_canonical.lower()
    )
    iscc_code_clean = decl.iscc_code[5:].lower() if decl.iscc_code.startswith("ISCC:") else decl.iscc_code.lower()

    template_vars = {
        "iscc_id": iscc_id_clean,
        "iscc_code": iscc_code_clean,
        "datahash": decl.datahash,
    }

    # Build declaration dict with required fields
    result = {
        "iscc_id": iscc_id_canonical,
        "iscc_code": decl.iscc_code,
        "datahash": decl.datahash,
        "timestamp": iscc_id_obj.timestamp_iso,
        "pubkey": decl.pubkey,
    }

    # Add optional fields only if present and non-empty
    if decl.controller:
        result["controller"] = decl.controller
    if decl.gateway:
        result["gateway"] = expand_gateway_url(decl.gateway, template_vars)
    if decl.metahash:
        result["metahash"] = decl.metahash

    return result


@api.get("/search")
def search(request: HttpRequest):
    # type: (HttpRequest) -> list[dict]
    """
    Search for ISCC declarations by datahash or ISCC-CODE.

    Exactly one search parameter must be provided (mutually exclusive).

    Query Parameters:
    - datahash: Blake3 multihash (format: 1e20 + 64 hex chars)
    - iscc_code: ISCC-CODE (format: ISCC: + 29-68 alphanumeric)

    :param request: The incoming HTTP request
    :return: List of matching IsccDeclaration objects (may be empty)
    """
    # Check if parameters are provided in the query string (regardless of their values)
    datahash_provided = "datahash" in request.GET
    iscc_code_provided = "iscc_code" in request.GET

    # Validate mutual exclusivity based on parameter presence
    if not datahash_provided and not iscc_code_provided:
        raise BaseApiException("Exactly one search parameter required: datahash or iscc_code")

    if datahash_provided and iscc_code_provided:
        raise BaseApiException("Only one search parameter allowed: datahash or iscc_code (not both)")

    # Parse and normalize query parameters (empty strings become None)
    datahash = request.GET.get("datahash", None) or None
    iscc_code = request.GET.get("iscc_code", None) or None

    # Validate that the provided parameter is not empty
    if datahash_provided and not datahash:
        raise BaseApiException("datahash parameter cannot be empty")
    if iscc_code_provided and not iscc_code:
        raise BaseApiException("iscc_code parameter cannot be empty")

    # Validate format and query database
    if datahash:
        if not re.match(r"^1e20[0-9a-f]{64}$", datahash):
            raise BaseApiException("Invalid datahash format. Expected: 1e20 followed by 64 hex characters")
        results = IsccDeclaration.objects.filter(datahash=datahash, redacted=False)
    elif iscc_code:
        if not re.match(r"^ISCC:[A-Z0-9]{29,68}$", iscc_code):
            raise BaseApiException(
                "Invalid iscc_code format. Expected: ISCC: followed by 29-68 alphanumeric characters"
            )
        results = IsccDeclaration.objects.filter(iscc_code=iscc_code, redacted=False)

    # Build response list
    return [declaration_to_dict(decl) for decl in results]


@api.post("/declaration", response={201: IsccReceipt, codes_4xx: ErrorResponse})
def declaration(request):
    # Validate and parse request body (includes size check and JSON parsing)
    # Timestamp handling is policy-driven (admin-editable Constance values)
    valid_data = validate_iscc_note(
        request.body,
        True,
        settings.ISCC_HUB_ID,
        require_timestamp=config.REQUIRE_CLIENT_TIMESTAMP,
        timestamp_tolerance_seconds=config.TIMESTAMP_TOLERANCE_SECONDS,
    )

    # Check for permission
    if not config.OPEN_ACCESS:
        pubkey = valid_data.get("signature", {}).get("pubkey")
        pubkey_obj = PubKey.objects.filter(pubkey=pubkey).first()
        if not pubkey_obj or not pubkey_obj.is_active:
            raise UnauthorizedError("Invalid or inactive pubkey")

    # Check for duplicate declarations (only if force header not present)
    force_declaration = request.headers.get("X-Force-Declaration", "").lower() in ("true", "1")
    if not force_declaration:
        existing = Event.objects.filter(datahash=valid_data["datahash"]).first()
        if existing:
            message = f"Duplicate declaration for datahash: {valid_data['datahash']}"
            existing_data = json.loads(existing.event_data.decode("utf-8"))
            existing_actor = existing_data.get("note", {}).get("signature", {}).get("pubkey", "")
            raise DuplicateDeclarationError(
                message, existing_iscc_id=str(IsccID(existing.iscc_id)), existing_actor=existing_actor
            )

    # Sequencing (now includes materialized view creation)
    seq, iscc_id = sequence_iscc_note(valid_data)

    # Create and return IsccReceipt
    declaration_data = {
        "iscc_note": valid_data,
        "seq": seq,
        "iscc_id_str": str(IsccID(iscc_id)),
    }
    receipt = build_iscc_receipt(declaration_data)
    return api.create_response(request, receipt, status=201)


@api.delete("/declaration/{iscc_id}", response={204: None, codes_4xx: ErrorResponse})
def delete_declaration(request, iscc_id: str):
    # type: (HttpRequest, str) -> object
    """
    Delete a previously timestamped ISCC declaration.

    Validates the deletion request, ensures the requester is authorized,
    and creates a deletion event in the log.

    :param request: The incoming HTTP request
    :param iscc_id: The ISCC-ID of the declaration to delete
    :return: 204 No Content on success, or error response
    """
    # Validate and parse request body
    # The deletion timestamp follows the same Hub policy as a declaration: optional unless
    # REQUIRE_CLIENT_TIMESTAMP is set, and range-checked against the tolerance when present.
    valid_data = validate_iscc_note_delete(
        request.body,
        True,
        settings.ISCC_HUB_ID,
        require_timestamp=config.REQUIRE_CLIENT_TIMESTAMP,
        timestamp_tolerance_seconds=config.TIMESTAMP_TOLERANCE_SECONDS,
    )

    # Check that the ISCC-ID from the URL matches the one in the body
    if valid_data["iscc_id"] != iscc_id:
        raise NotFoundError(f"ISCC-ID mismatch: URL {iscc_id} != body {valid_data['iscc_id']}")

    # Find the original declaration with matching ISCC-ID
    original_event = Event.objects.filter(iscc_id=bytes(IsccID(iscc_id)), event_type=1).select_related().first()

    if not original_event:
        raise NotFoundError(f"Declaration not found: {iscc_id}")

    # Check if already deleted (look for a deletion event)
    deletion_event = Event.objects.filter(iscc_id=bytes(IsccID(iscc_id)), event_type=3).first()

    if deletion_event:
        raise NotFoundError(f"Declaration already deleted: {iscc_id}")

    # Verify that the requester is the same controller who created the declaration
    original_data = json.loads(original_event.event_data.decode("utf-8"))
    original_pubkey = original_data.get("note", {}).get("signature", {}).get("pubkey", "")
    request_pubkey = valid_data["signature"]["pubkey"]

    if original_pubkey != request_pubkey:
        raise UnauthorizedError("Not authorized to delete this declaration")

    # Sequence the deletion event (now includes materialized view deletion)
    sequence_iscc_delete(valid_data, original_event.datahash)

    # Return 204 No Content with empty body
    return Status(204, None)


@api.get("/health")
def health(request):
    # type: (HttpRequest) -> dict
    """
    Health check endpoint to verify service status.

    Returns JSON status information for API clients.

    :param request: The incoming HTTP request
    :return: HealthResponse JSON with status, version, and description
    """
    status = "pass"
    version = getattr(settings, "VERSION", iscc_hub.__version__)
    description = "ISCC-HUB service is healthy"

    # Include build metadata
    build_info = {
        "commit": getattr(settings, "BUILD_COMMIT", "unknown"),
        "tag": getattr(settings, "BUILD_TAG", "unknown"),
        "timestamp": getattr(settings, "BUILD_TIMESTAMP", "unknown"),
    }

    return {
        "status": status,
        "version": version,
        "description": description,
        "build": build_info,
    }


@api.get("/.well-known/did.json")
def did_document(request):
    # type: (object) -> JsonResponse
    """
    Serve the notary's DID document for DID:WEB resolution.

    Implements W3C DID Method Web specification requirements:
    - Always returns application/json content type
    - Includes CORS headers for cross-origin access

    :param request: The incoming HTTP request
    :return: JsonResponse with DID document or error
    """
    controller = f"did:web:{settings.ISCC_HUB_DOMAIN}"
    keypair = icr.key_from_secret(settings.ISCC_HUB_SECKEY, controller=controller)

    response = JsonResponse(keypair.controller_document, content_type="application/json")

    # Add CORS header as required by W3C DID Method Web spec
    response["Access-Control-Allow-Origin"] = "*"

    return response


@api.get("/{iscc_id}")
def resolve(request, iscc_id: str):
    # type: (HttpRequest, str) -> dict
    """
    Resolve an ISCC-ID to its declaration data.

    :param request: The incoming HTTP request
    :param iscc_id: The ISCC-ID to resolve
    :return: Declaration data as JSON dict
    """
    # Validate and normalize ISCC-ID format
    try:
        mt, st, vs, ln, body = ic.iscc_decode(iscc_id)
        if mt != ic.MT.ID or vs != ic.VS.V1:
            raise NotFoundError(f"Invalid ISCC-ID: {iscc_id}")
        iscc_id_canonical = ic.iscc_normalize(iscc_id)
    except NotFoundError:
        raise
    except Exception:
        raise NotFoundError(f"Invalid ISCC-ID: {iscc_id}") from None

    # Check if ISCC-ID belongs to a remote hub
    iscc_id_obj = IsccID(iscc_id_canonical)
    if iscc_id_obj.hub_id != settings.ISCC_HUB_ID:
        try:
            hub = Hub.objects.get(hub_id=iscc_id_obj.hub_id, active=True)
            raise NotFoundError(f"ISCC-ID belongs to remote hub: {hub.url}")
        except Hub.DoesNotExist:
            raise NotFoundError(f"ISCC-ID belongs to unknown remote hub (ID: {iscc_id_obj.hub_id})") from None

    # Query for the declaration
    try:
        decl = IsccDeclaration.objects.get(iscc_id=iscc_id_canonical)
    except IsccDeclaration.DoesNotExist:
        raise NotFoundError(f"Declaration not found: {iscc_id_canonical}") from None

    if decl.redacted:
        raise NotFoundError(f"Declaration not found: {iscc_id_canonical}")

    return declaration_to_dict(decl)
