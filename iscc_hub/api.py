import json

import iscc_crypto as icr
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from ninja import NinjaAPI
from ninja.responses import codes_4xx

import iscc_hub
from iscc_hub.exceptions import BaseApiException, DuplicateDeclarationError, NonceError, ValidationError
from iscc_hub.iscc_id import IsccID
from iscc_hub.models import Event, IsccDeclaration
from iscc_hub.receipt import abuild_iscc_receipt
from iscc_hub.schema import ErrorResponse, IsccReceipt
from iscc_hub.sequencer import asequence_iscc_note
from iscc_hub.validators import avalidate_iscc_note

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


@api.post("/declaration", response={201: IsccReceipt, codes_4xx: ErrorResponse})
async def declaration(request):
    # Parse JSON with error handling
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BaseApiException("Invalid JSON in request body") from e

    # Offline pre-validation
    valid_data = await avalidate_iscc_note(data, True, settings.ISCC_HUB_ID, True)

    # Online pre-validation
    if await Event.objects.filter(nonce=valid_data["nonce"]).aexists():
        raise NonceError("Nonce already used", is_reuse=True)

    # Check for duplicate declarations (only if force header not present)
    force_declaration = request.headers.get("X-Force-Declaration", "").lower() in ("true", "1")
    if not force_declaration:
        existing = await Event.objects.filter(datahash=valid_data["datahash"]).afirst()
        if existing:
            message = f"Duplicate declaration for datahash: {valid_data['datahash']}"
            existing_actor = existing.iscc_note.get("signature", {}).get("pubkey", "")
            raise DuplicateDeclarationError(
                message, existing_iscc_id=str(IsccID(existing.iscc_id)), existing_actor=existing_actor
            )

    # Sequencing
    seq, iscc_id = await asequence_iscc_note(valid_data)

    # Create the declaration using Django's async ORM
    await IsccDeclaration.objects.acreate(
        iscc_id=iscc_id,
        event_seq=seq,
        iscc_code=valid_data["iscc_code"],
        datahash=valid_data["datahash"],
        nonce=valid_data["nonce"],
        actor=valid_data["signature"]["pubkey"],
        gateway=valid_data.get("gateway", ""),
        metahash=valid_data.get("metahash", ""),
    )

    # Create and return IsccReceipt
    declaration_data = {
        "iscc_note": valid_data,
        "seq": seq,
        "iscc_id_str": str(IsccID(iscc_id)),
    }
    receipt = await abuild_iscc_receipt(declaration_data)
    return api.create_response(request, receipt, status=201)


@api.get("/health")
async def health(request):
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

    return {"status": status, "version": version, "description": description}


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
