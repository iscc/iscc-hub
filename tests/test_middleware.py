"""Tests for content negotiation middleware."""

from unittest.mock import Mock

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
    response = middleware(request)

    # Check that urlconf was set correctly
    assert request.urlconf == "iscc_hub.urls_api"
    # Check Vary header was added
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_format_param_html(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to views when format=html parameter is present."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/?format=html")
    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_accept_header_json(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to API when Accept header contains application/json."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="application/json")
    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_accept_header_vendor_json(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to API for vendor-specific JSON types."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="application/vnd.api+json")
    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_accept_header_html(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware routes to views when Accept header contains text/html."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="text/html")
    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    assert "Accept" in response.get("Vary", "")
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

    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_mixed_accept_header(request_factory):
    # type: (RequestFactory) -> None
    """Test middleware handles mixed Accept headers with JSON preference."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="text/html, application/json;q=0.9")
    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_format_param_overrides_accept(request_factory):
    # type: (RequestFactory) -> None
    """Test that format parameter takes precedence over Accept header."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    # Request with JSON Accept header but format=html parameter
    request = request_factory.get("/?format=html", HTTP_ACCEPT="application/json")
    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_sync_format_json(request_factory):
    # type: (RequestFactory) -> None
    """Test sync middleware routes to API when format=json."""

    # Create sync get_response
    def sync_get_response(request):
        # type: (object) -> HttpResponse
        """Mock sync response handler."""
        return HttpResponse("OK")

    get_response = Mock(side_effect=sync_get_response)

    # Get middleware instance
    middleware = ContentNegotiationMiddleware(get_response)

    # Create request
    request = request_factory.get("/?format=json")

    # Process request
    response = middleware(request)

    # Check that urlconf was set correctly
    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_sync_accept_json(request_factory):
    # type: (RequestFactory) -> None
    """Test sync middleware routes to API with JSON Accept header."""

    def sync_get_response(request):
        # type: (object) -> HttpResponse
        """Mock sync response handler."""
        return HttpResponse("OK")

    get_response = Mock(side_effect=sync_get_response)
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="application/json")
    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_sync_default_html(request_factory):
    # type: (RequestFactory) -> None
    """Test sync middleware defaults to views."""

    def sync_get_response(request):
        # type: (object) -> HttpResponse
        """Mock sync response handler."""
        return HttpResponse("OK")

    get_response = Mock(side_effect=sync_get_response)
    middleware = ContentNegotiationMiddleware(get_response)

    request = request_factory.get("/", HTTP_ACCEPT="text/html")
    response = middleware(request)

    assert request.urlconf == "iscc_hub.urls_views"
    assert "Accept" in response.get("Vary", "")
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
    response = middleware(request)

    # Should fall back to Accept header
    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")
    get_response.assert_called_once_with(request)


def test_middleware_format_param_case_insensitive(request_factory):
    # type: (RequestFactory) -> None
    """Test format parameter is case-insensitive."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    # Test uppercase JSON
    request = request_factory.get("/?format=JSON")
    response = middleware(request)
    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")

    # Test mixed case HTML
    request = request_factory.get("/?format=Html")
    response = middleware(request)
    assert request.urlconf == "iscc_hub.urls_views"
    assert "Accept" in response.get("Vary", "")


def test_middleware_accept_header_case_insensitive(request_factory):
    # type: (RequestFactory) -> None
    """Test Accept header matching is case-insensitive."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    # Test uppercase APPLICATION/JSON
    request = request_factory.get("/", HTTP_ACCEPT="APPLICATION/JSON")
    response = middleware(request)
    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")

    # Test mixed case
    request = request_factory.get("/", HTTP_ACCEPT="Application/Json")
    response = middleware(request)
    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")


def test_middleware_wildcard_accept_with_json_content_type(request_factory):
    # type: (RequestFactory) -> None
    """Test wildcard Accept header uses Content-Type as hint."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    # Wildcard Accept with JSON Content-Type should route to API
    request = request_factory.post("/", HTTP_ACCEPT="*/*", content_type="application/json")
    response = middleware(request)
    assert request.urlconf == "iscc_hub.urls_api"
    assert "Accept" in response.get("Vary", "")


def test_middleware_wildcard_accept_without_json_content(request_factory):
    # type: (RequestFactory) -> None
    """Test wildcard Accept without JSON content defaults to HTML."""
    get_response = Mock(return_value=HttpResponse("OK"))
    middleware = ContentNegotiationMiddleware(get_response)

    # Wildcard Accept without JSON Content-Type should default to HTML
    request = request_factory.get("/", HTTP_ACCEPT="*/*")
    response = middleware(request)
    assert request.urlconf == "iscc_hub.urls_views"
    assert "Accept" in response.get("Vary", "")
