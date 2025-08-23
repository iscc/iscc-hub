"""HTML views for ISCC Hub."""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

import iscc_hub


async def homepage(request):
    # type: (HttpRequest) -> HttpResponse
    """
    Homepage view that displays the ISCC logo centered on the page.

    :param request: The incoming HTTP request
    :return: HTML page with centered ISCC logo
    """
    return render(request, "iscc_hub/homepage.html")


async def health(request):
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
