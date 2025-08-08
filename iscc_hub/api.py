from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from ninja import NinjaAPI

import iscc_hub

api = NinjaAPI(
    title="ISCC Notary API",
    version=iscc_hub.__version__,
    description="Sign, timestamp, and discover content using ISCC",
)


@api.get("/health")
async def health(request):
    # type: (HttpRequest) -> HttpResponse | JsonResponse
    """
    Health check endpoint to verify service status.

    Returns JSON for API clients or HTML for browsers based on Accept header.

    :param request: The incoming HTTP request
    :return: HealthResponse JSON or HTML page based on content negotiation
    """
    status = "pass"
    version = getattr(settings, "VERSION", iscc_hub.__version__)
    description = "ISCC-HUB service is healthy"

    result = {"status": status, "version": version, "description": description}

    # Content negotiation based on Accept header
    accept_header = request.headers.get("Accept", "").lower()

    if "text/html" in accept_header:
        # Return HTML for browsers using Django template

        return render(request, "iscc_hub/health.html", result)

    return JsonResponse(result)
