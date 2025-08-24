"""Tests for HTML views."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from iscc_hub import views


def test_health_view_returns_html():
    # type: () -> None
    """Test that health view returns HTML with correct context."""
    # Create a request
    factory = RequestFactory()
    request = factory.get("/health/")

    # Mock the render function to capture the context
    with patch("iscc_hub.views.render") as mock_render:
        mock_response = MagicMock()
        mock_render.return_value = mock_response

        # Call the view
        response = views.health(request)

        # Verify render was called with correct arguments
        mock_render.assert_called_once()
        call_args = mock_render.call_args

        # Check the request argument
        assert call_args[0][0] == request

        # Check the template name
        assert call_args[0][1] == "iscc_hub/health.html"

        # Check the context
        context = call_args[0][2]
        assert context["status"] == "pass"
        assert context["version"] == "0.1.0"
        assert context["description"] == "ISCC-HUB service is healthy"

        # Check build metadata with default values
        assert context["build_commit"] == "unknown"
        assert context["build_commit_short"] == "unknown"
        assert context["build_tag"] == "unknown"
        assert context["build_timestamp"] == "unknown"

        # Check the response
        assert response == mock_response


def test_health_view_with_custom_version():
    # type: () -> None
    """Test that health view uses custom VERSION from settings if available."""
    factory = RequestFactory()
    request = factory.get("/health/")

    with patch("iscc_hub.views.render") as mock_render:
        with patch("iscc_hub.views.settings", VERSION="2.0.0"):
            mock_response = MagicMock()
            mock_render.return_value = mock_response

            views.health(request)

            # Check the context has custom version
            context = mock_render.call_args[0][2]
            assert context["version"] == "2.0.0"


def test_health_view_with_build_metadata():
    # type: () -> None
    """Test that health view correctly formats build metadata."""
    factory = RequestFactory()
    request = factory.get("/health/")

    with patch("iscc_hub.views.render") as mock_render:
        # Patch settings with build metadata
        with patch(
            "iscc_hub.views.settings",
            BUILD_COMMIT="a1b2c3d4e5f6789012345678901234567890abcd",
            BUILD_TAG="v1.2.3",
            BUILD_TIMESTAMP="2024-01-15T12:00:00Z",
        ):
            mock_response = MagicMock()
            mock_render.return_value = mock_response

            views.health(request)

            # Check the context has build metadata
            context = mock_render.call_args[0][2]
            assert context["build_commit"] == "a1b2c3d4e5f6789012345678901234567890abcd"
            assert context["build_commit_short"] == "a1b2c3d4"  # First 8 chars
            assert context["build_tag"] == "v1.2.3"
            assert context["build_timestamp"] == "2024-01-15T12:00:00Z"


def test_homepage_view_returns_html():
    # type: () -> None
    """Test that homepage view returns HTML with correct template."""
    # Create a request
    factory = RequestFactory()
    request = factory.get("/")

    # Mock the render function
    with patch("iscc_hub.views.render") as mock_render:
        mock_response = MagicMock()
        mock_render.return_value = mock_response

        # Call the view
        response = views.homepage(request)

        # Verify render was called with correct arguments
        mock_render.assert_called_once_with(request, "iscc_hub/homepage.html")

        # Check the response
        assert response == mock_response
