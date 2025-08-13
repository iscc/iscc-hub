import json

import iscc_crypto as icr
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from ninja import NinjaAPI
from ninja.responses import codes_4xx

import iscc_hub
from iscc_hub.exceptions import BaseApiException, NonceError
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
async def handle_api_exception(request, exc):
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
    data = json.loads(request.body)

    # Offline pre-validation
    valid_data = await avalidate_iscc_note(data, True, settings.ISCC_HUB_ID, True)

    # Online pre-validation
    if await IsccDeclaration.objects.filter(nonce=valid_data["nonce"]).aexists():
        raise NonceError("Nonce already used", is_reuse=True)

    # Sequencing
    seq, iscc_id = await asequence_iscc_note(valid_data)

    # Create and return IsccReceipt
    event = await Event.objects.aget(seq=seq)
    receipt = await abuild_iscc_receipt(event)
    return receipt


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
