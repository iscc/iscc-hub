"""Tests for content negotiation middleware."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from iscc_hub.middleware import ContentNegotiationMiddleware


@pytest.fixture
def request_factory():
    # type: () -> RequestFactory
    """Create a Django RequestFactory instance."""
    return RequestFactory()


def test_middleware_format_param_json(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to API when format=json parameter is present."""
    # Create sync get_response
    get_response = Mock(return_value=HttpResponse("OK"))

    # Get middleware instance
    middleware = ContentNegotiationMiddleware(get_response)

    # Create request with format=json
    request = request_factory.get("/?format=json")

    # Process request
    middleware(request)

    # Check that urlconf was set correctly
    assert request.urlconf == "iscc_hub.urls_api"
    get_response.assert_called_once_with(request)


def test_middleware_format_param_html(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to views when format=html parameter is present."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/?format=html")
    middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    get_response.assert_called_once_with(request)


def test_middleware_accept_header_json(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to API when Accept header contains application/json."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="application/json")
    middleware(request)

    assert request.urlconf == "iscc_hub.urls_api"
    get_response.assert_called_once_with(request)


def test_middleware_accept_header_vendor_json(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to API for vendor-specific JSON types."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="application/vnd.api+json")
    middleware(request)

    assert request.urlconf == "iscc_hub.urls_api"
    get_response.assert_called_once_with(request)


def test_middleware_accept_header_html(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to views when Accept header contains text/html."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="text/html")
    middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    get_response.assert_called_once_with(request)


def test_middleware_no_accept_header(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware defaults to views when no Accept header is present."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    # Remove Accept header entirely
    request = request_factory.get("/")
    if "HTTP_ACCEPT" in request.META:
        del request.META["HTTP_ACCEPT"]

    middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    get_response.assert_called_once_with(request)


def test_middleware_mixed_accept_header(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware handles mixed Accept headers with JSON preference."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="text/html, application/json;q=0.9")
    middleware(request)

    assert request.urlconf == "iscc_hub.urls_api"
    get_response.assert_called_once_with(request)


def test_middleware_format_param_overrides_accept(request_factory):
    # type: (RequestFactory) -> None
    """Test that format parameter takes precedence over Accept header."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    # Request with JSON Accept header but format=html parameter
    request = request_factory.get("/?format=html", HTTP_ACCEPT="application/json")
    middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    get_response.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_middleware_async_format_json(request_factory):
    # type: (RequestFactory) -> None
    """Test async middleware routes to API when format=json."""

    # Create async get_response
    async def async_get_response(request):
        # type: (object) -> HttpResponse
        """Mock async response handler."""
        return HttpResponse("OK")

    get_response = AsyncMock(side_effect=async_get_response)

    # Get middleware instance
    middleware = ContentNegotiationMiddleware(get_response)

    # Create request
    request = request_factory.get("/?format=json")

    # Process request
    await middleware(request)

    # Check that urlconf was set correctly
    assert request.urlconf == "iscc_hub.urls_api"
    get_response.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_middleware_async_accept_json(request_factory):
    # type: (RequestFactory) -> None
    """Test async middleware routes to API with JSON Accept header."""

    async def async_get_response(request):
        # type: (object) -> HttpResponse
        """Mock async response handler."""
        return HttpResponse("OK")

    get_response = AsyncMock(side_effect=async_get_response)
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="application/json")
    await middleware(request)

    assert request.urlconf == "iscc_hub.urls_api"
    get_response.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_middleware_async_default_html(request_factory):
    # type: (RequestFactory) -> None
    """Test async middleware defaults to views."""

    async def async_get_response(request):
        # type: (object) -> HttpResponse
        """Mock async response handler."""
        return HttpResponse("OK")

    get_response = AsyncMock(side_effect=async_get_response)
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="text/html")
    await middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    get_response.assert_called_once_with(request)


def test_middleware_response_passthrough(request_factory):
    # type: (RequestFactory) -> None
    """Test that middleware passes through the response unchanged."""
    response = HttpResponse("Test Response", status=201)
    get_response = Mock(return_value=response)
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/")
    result = middleware(request)

    assert result is response
    assert result.status_code == 201
    assert result.content == b"Test Response"


def test_middleware_invalid_format_param(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware ignores invalid format parameter values."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    # Invalid format parameter should be ignored
    request = request_factory.get("/?format=xml", HTTP_ACCEPT="application/json")
    middleware(request)

    # Should fall back to Accept header
    assert request.urlconf == "iscc_hub.urls_api"
    get_response.assert_called_once_with(request)
