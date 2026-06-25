"""Content negotiation and cross-origin read middleware for ISCC Hub."""

import re
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.utils.cache import patch_vary_headers

# Precompile regex with case-insensitive flag
JSON_PATTERN = re.compile(r"application/(json|.*\+json)", re.IGNORECASE)

# Non-mutating HTTP methods (reads plus the OPTIONS metadata method). Cross-origin
# reads of the public API carry no credentials, so responses to these may be
# shared with any origin.
CORS_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# URL configurations making up the public, machine-readable read surface (JSON
# API + binary ISCC-Log). The HTML views urlconf is deliberately excluded.
CORS_READ_URLCONFS = frozenset({"iscc_hub.urls_api", "iscc_hub.urls_log"})


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
        # Path-route the binary / JSON-only / static endpoints before any Accept
        # logic. These have no HTML representation and are consumed by clients
        # (Go net/http, fsck, curl) that send no Accept header, so they must be
        # reachable independent of content negotiation.
        path = request.path
        if path.startswith("/log/"):
            request.urlconf = "iscc_hub.urls_log"  # type: ignore
            return
        if (
            path.startswith("/search")
            or path.startswith("/lookup")
            or path.startswith("/declaration")
            or path.startswith("/.well-known/")
        ):
            # The /.well-known/ prefix subsumes the did.json special-case.
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

    def middleware(request):
        # type: (HttpRequest) -> HttpResponse
        """Sync middleware handler."""
        determine_urlconf(request)
        response = get_response(request)  # type: ignore
        patch_vary_headers(response, ("Accept",))
        return response

    return middleware


def CorsReadMiddleware(get_response):
    # type: (Any) -> Any
    """
    Expose the public read surface to cross-origin browser clients.

    Stamps ``Access-Control-Allow-Origin: *`` on safe-method responses routed to
    the JSON API or ISCC-Log url configurations, so a Hub homepage served from one
    origin can resolve declarations, look-ups, and log tiles from another Hub (and
    Monitors/Aggregators can read the log from any origin). Write endpoints
    (POST/DELETE) and the HTML views are never exposed.

    The data is public and unauthenticated, so a wildcard origin is safe; it is
    never paired with ``Access-Control-Allow-Credentials``. Must be listed after
    ContentNegotiationMiddleware, which selects ``request.urlconf``.
    """

    def middleware(request):
        # type: (HttpRequest) -> HttpResponse
        """Add a permissive CORS header to read-surface responses."""
        response = get_response(request)  # type: ignore
        if request.method in CORS_SAFE_METHODS and getattr(request, "urlconf", None) in CORS_READ_URLCONFS:
            response["Access-Control-Allow-Origin"] = "*"
        return response

    return middleware
