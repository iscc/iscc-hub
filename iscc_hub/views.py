"""HTML views for ISCC Hub."""

import iscc_core as ic
from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render

import iscc_hub
from iscc_hub.gateway import expand_gateway_url
from iscc_hub.models import IsccDeclaration


def homepage(request):
    # type: (HttpRequest) -> HttpResponse
    """
    Homepage view that displays the ISCC logo centered on the page.

    :param request: The incoming HTTP request
    :return: HTML page with centered ISCC logo
    """
    return render(request, "iscc_hub/homepage.html")


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

    :param request: The incoming HTTP request
    :param iscc_id: The ISCC-ID to resolve (can be in various formats)
    :return: 404, redirect, or detail page
    """
    # Validate and normalize ISCC-ID format using iscc_core
    try:
        # iscc_decode handles various formats (with/without prefix, case-insensitive, etc.)
        mt, st, vs, ln, body = ic.iscc_decode(iscc_id)
        if mt != ic.MT.ID or vs != ic.VS.V1:
            # Not a valid ISCC-ID
            return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)

        # Get canonical representation for database lookup
        iscc_id_canonical = ic.iscc_normalize(iscc_id)

        # Extract just the code part (without ISCC: prefix) and lowercase for URLs
        iscc_id_clean = (
            iscc_id_canonical[5:].lower() if iscc_id_canonical.startswith("ISCC:") else iscc_id_canonical.lower()
        )

    except Exception:
        # Invalid format
        return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)

    # Query for the declaration using the canonical ISCC-ID
    try:
        declaration = IsccDeclaration.objects.get(iscc_id=iscc_id_canonical)

        # Check if redacted
        if declaration.redacted:
            return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)

        # Check for gateway
        if declaration.gateway:
            # Prepare template variables for expansion
            # Strip "ISCC:" prefix from iscc_code if present for cleaner URLs
            iscc_code_clean = declaration.iscc_code
            if iscc_code_clean.startswith("ISCC:"):
                iscc_code_clean = iscc_code_clean[5:]

            template_vars = {
                "iscc_id": iscc_id_clean,  # Use clean version without ISCC: prefix
                "iscc_code": iscc_code_clean,
                "datahash": declaration.datahash,
            }

            # Build the full request URL for query parameter forwarding
            request_url = request.build_absolute_uri()

            # Expand gateway URL with template substitution and query params
            redirect_url = expand_gateway_url(declaration.gateway, template_vars, request_url)

            # 307 Temporary Redirect (preserves method and body)
            return HttpResponseRedirect(redirect_url, status=307)

        # No gateway - render detail view
        context = {
            "declaration": declaration,
            "iscc_id": iscc_id_canonical,  # Use canonical version for display
        }
        return render(request, "iscc_hub/declaration_detail.html", context)

    except IsccDeclaration.DoesNotExist:
        # ISCC-ID not found
        return render(request, "iscc_hub/404.html", {"iscc_id": iscc_id}, status=404)
