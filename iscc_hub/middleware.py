"""Content negotiation middleware for ISCC Hub."""

import re
from typing import Any

from asgiref.sync import iscoroutinefunction
from django.http import HttpRequest, HttpResponse
from django.utils.cache import patch_vary_headers
from django.utils.decorators import sync_and_async_middleware

# Precompile regex with case-insensitive flag
JSON_PATTERN = re.compile(r"application/(json|.*\+json)", re.IGNORECASE)


@sync_and_async_middleware
def ContentNegotiationMiddleware(get_response):
    # type: (Any) -> Any
    """
    Middleware for content negotiation between JSON API and HTML views.

    Routes requests to different URL configurations based on:
    - Query parameter 'format' (json/html)
    - Accept header (application/json or text/html)
    """

    def determine_urlconf(request):
        # type: (HttpRequest) -> None
        """Determine and set the appropriate URL configuration."""
        # Always serve .well-known/did.json as JSON API per W3C DID Method Web spec
        if request.path == "/.well-known/did.json":
            request.urlconf = "iscc_hub.urls_api"  # type: ignore
            return

        # Check for explicit format override via query parameter
        format_param = request.GET.get("format")
        if format_param:
            format_param = format_param.lower()
            if format_param == "json":
                request.urlconf = "iscc_hub.urls_api"  # type: ignore
                return
            elif format_param == "html":
                request.urlconf = "iscc_hub.urls_views"  # type: ignore
                return

        # Check Accept header
        accept = request.META.get("HTTP_ACCEPT", "text/html")

        # For wildcard Accept, check Content-Type as hint
        if accept == "*/*":
            content_type = request.META.get("CONTENT_TYPE", "").lower()
            if "json" in content_type:
                request.urlconf = "iscc_hub.urls_api"  # type: ignore
                return

        # Check for JSON in Accept header
        if JSON_PATTERN.search(accept):
            request.urlconf = "iscc_hub.urls_api"  # type: ignore
        else:
            # Default to HTML views
            request.urlconf = "iscc_hub.urls_views"  # type: ignore

    if iscoroutinefunction(get_response):
        # Async version
        async def async_middleware(request):
            # type: (HttpRequest) -> HttpResponse
            """Async middleware handler."""
            determine_urlconf(request)
            response = await get_response(request)
            patch_vary_headers(response, ("Accept",))
            return response

        return async_middleware
    else:
        # Sync version
        def sync_middleware(request):
            # type: (HttpRequest) -> HttpResponse
            """Sync middleware handler."""
            determine_urlconf(request)
            response = get_response(request)  # type: ignore
            patch_vary_headers(response, ("Accept",))
            return response

        return sync_middleware
