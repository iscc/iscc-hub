"""HTML views for ISCC Hub."""

import iscc_core as ic
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render

import iscc_hub
from iscc_hub.gateway import expand_gateway_url, preserve_query_params
from iscc_hub.iscc_id import IsccID
from iscc_hub.models import Hub, IsccDeclaration


def homepage(request):
    # type: (HttpRequest) -> HttpResponse
    """
    Homepage view with the lookup/search surface and progressive-enhancement result cards.

    Serializes the active Hub list (hub_id -> url) into the page so the client can map an
    ISCC-ID's decoded hub_id to its issuing hub for "where it's logged" display and for the
    Tier-1 declaration resolve that hydrates each result card.

    :param request: The incoming HTTP request
    :return: Rendered homepage with the active-hub map embedded
    """
    hubs = list(Hub.objects.filter(active=True).order_by("hub_id").values("hub_id", "url"))
    context = {"hubs": hubs, "search_min_score": settings.ISCC_HUB_SEARCH_MIN_SCORE}
    return render(request, "iscc_hub/homepage.html", context)


def health(request):
    # type: (HttpRequest) -> HttpResponse
    """
    Health check view that returns HTML.

    :param request: The incoming HTTP request
    :return: HTML page showing health status
    """
    status = "pass"
    version = getattr(settings, "VERSION", iscc_hub.__version__)
    description = "ISCC-HUB service is healthy"

    # Include build metadata
    build_commit = getattr(settings, "BUILD_COMMIT", "unknown")
    build_tag = getattr(settings, "BUILD_TAG", "unknown")
    build_timestamp = getattr(settings, "BUILD_TIMESTAMP", "unknown")

    # Shorten commit hash for display
    if build_commit != "unknown" and len(build_commit) >= 8:
        build_commit_short = build_commit[:8]
    else:
        build_commit_short = build_commit

    context = {
        "status": status,
        "version": version,
        "description": description,
        "build_commit": build_commit,
        "build_commit_short": build_commit_short,
        "build_tag": build_tag,
        "build_timestamp": build_timestamp,
    }

    return render(request, "iscc_hub/health.html", context)


def iscc_id_resolve(request, iscc_id):
    # type: (HttpRequest, str) -> HttpResponse
    """
    Resolve ISCC-ID for browser/HTML requests.

    Handles three cases:
    1. Invalid/non-existent ISCC-ID → 404 page
    2. ISCC-ID with gateway → 307 redirect to gateway URL
    3. ISCC-ID without gateway → declaration detail page

    Query parameters:
    - redirect=false: Disable redirects and show declaration details instead

    :param request: The incoming HTTP request
    :param iscc_id: The ISCC-ID to resolve (can be in various formats)
    :return: 404, redirect, or detail page
    """
    # Check if redirects should be disabled
    should_redirect = request.GET.get("redirect", "true").lower() != "false"
    # Validate and normalize ISCC-ID format using iscc_core
    try:
        # iscc_decode handles various formats (with/without prefix, case-insensitive, etc.)
        mt, st, vs, ln, body = ic.iscc_decode(iscc_id)
        if mt != ic.MT.ID or vs != ic.VS.V1:
            # Not a valid ISCC-ID
            return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)

        # Get canonical representation for database lookup
        iscc_id_canonical = ic.iscc_normalize(iscc_id)

        # Extract the lowercase URI-form body (without ISCC: prefix, per ISO 24138) for URLs
        iscc_id_clean = iscc_id_canonical.removeprefix("ISCC:").lower()

    except Exception:
        # Invalid format
        return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)

    # Check if ISCC-ID belongs to a remote hub and forward if needed
    iscc_id_obj = IsccID(iscc_id_canonical)
    remote_hub_id = iscc_id_obj.hub_id
    local_hub_id = settings.ISCC_HUB_ID

    if remote_hub_id != local_hub_id:
        # ISCC-ID from remote hub
        try:
            hub = Hub.objects.get(hub_id=remote_hub_id, active=True)

            if not should_redirect:
                # Show info page about remote ISCC-ID instead of redirecting
                details_url = f"{hub.url.rstrip('/')}/{iscc_id_clean}?redirect=false"
                context = {
                    "iscc_id": iscc_id_clean,
                    "iscc_id_canonical": iscc_id_canonical,
                    "hub": hub,
                    "hub_id": remote_hub_id,
                    "details_url": details_url,
                }
                return render(request, "iscc_hub/remote_declaration.html", context)

            # Forward to remote hub using same path structure
            redirect_url = f"{hub.url.rstrip('/')}/{iscc_id_clean}"
            # Preserve query parameters from the original request
            request_url = request.build_absolute_uri()
            redirect_url = preserve_query_params(redirect_url, request_url)
            return HttpResponseRedirect(redirect_url, status=307)
        except Hub.DoesNotExist:
            # Remote hub not found or not active
            if not should_redirect:
                # Show info page even without hub details
                context = {
                    "iscc_id": iscc_id_clean,
                    "iscc_id_canonical": iscc_id_canonical,
                    "hub_id": remote_hub_id,
                    "hub": None,
                }
                return render(request, "iscc_hub/remote_declaration.html", context)
            return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)

    # Query for the declaration using the canonical ISCC-ID
    try:
        declaration = IsccDeclaration.objects.get(iscc_id=iscc_id_canonical)

        # Check if redacted
        if declaration.redacted:
            return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)

        # Prepare template variables for gateway URL expansion
        expanded_gateway_url = None
        if declaration.gateway:
            # Lowercase URI-form body (without ISCC: prefix, per ISO 24138), matching {iscc_id}
            iscc_code_clean = declaration.iscc_code.removeprefix("ISCC:").lower()

            template_vars = {
                "iscc_id": iscc_id_clean,  # Use clean version without ISCC: prefix
                "iscc_code": iscc_code_clean,
                "datahash": declaration.datahash,
            }

            # Build the full request URL for query parameter forwarding
            request_url = request.build_absolute_uri()

            # Expand gateway URL with template substitution and query params
            expanded_gateway_url = expand_gateway_url(declaration.gateway, template_vars, request_url)

            # Check if we should redirect to gateway
            if should_redirect:
                # 307 Temporary Redirect (preserves method and body)
                return HttpResponseRedirect(expanded_gateway_url, status=307)

        # Render detail view
        context = {
            "declaration": declaration,
            "iscc_id": iscc_id_canonical,  # Use canonical version for display
            "expanded_gateway_url": expanded_gateway_url,  # Pass expanded URL to template
        }
        return render(request, "iscc_hub/declaration_detail.html", context)

    except IsccDeclaration.DoesNotExist:
        # ISCC-ID not found
        return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)
