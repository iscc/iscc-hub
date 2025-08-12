import iscc_crypto as icr
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from ninja import NinjaAPI

import iscc_hub

api = NinjaAPI(
    title="ISCC Notary API",
    version=iscc_hub.__version__,
    description="Sign, timestamp, and discover content using ISCC",
)


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
