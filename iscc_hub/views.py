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

    context = {"status": status, "version": version, "description": description}

    return render(request, "iscc_hub/health.html", context)
