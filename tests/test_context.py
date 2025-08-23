"""Tests for context processors."""

from unittest.mock import MagicMock, patch

from iscc_hub.context import hub_context


def test_hub_context_returns_hub_id():
    # type: () -> None
    """Test that hub_context returns the correct hub ID from settings."""
    request = MagicMock()

    # Create mock settings without BUILD_* attributes
    mock_settings = MagicMock(spec=["ISCC_HUB_ID", "DEBUG"])
    mock_settings.ISCC_HUB_ID = 42
    mock_settings.DEBUG = True

    with patch("iscc_hub.context.settings", mock_settings):
        result = hub_context(request)

        assert result["hub_id"] == 42
        assert result["debug_mode"] is True
        # Check default build metadata
        assert result["build_commit"] == "unknown"
        assert result["build_commit_short"] == "unknown"
        assert result["build_tag"] == "unknown"
        assert result["build_timestamp"] == "unknown"


def test_hub_context_with_missing_settings():
    # type: () -> None
    """Test that hub_context handles missing settings gracefully."""
    request = MagicMock()

    # Mock settings without the ISCC_HUB_ID and DEBUG attributes
    mock_settings = MagicMock(spec=[])

    with patch("iscc_hub.context.settings", mock_settings):
        result = hub_context(request)

        assert result["hub_id"] == 0
        assert result["debug_mode"] is False
        assert result["build_commit"] == "unknown"
        assert result["build_commit_short"] == "unknown"
        assert result["build_tag"] == "unknown"
        assert result["build_timestamp"] == "unknown"


def test_hub_context_with_build_metadata():
    # type: () -> None
    """Test that hub_context correctly handles build metadata."""
    request = MagicMock()

    with patch(
        "iscc_hub.context.settings",
        ISCC_HUB_ID=123,
        DEBUG=False,
        BUILD_COMMIT="a1b2c3d4e5f6789012345678901234567890abcd",
        BUILD_TAG="v1.2.3",
        BUILD_TIMESTAMP="2024-01-15T12:00:00Z",
    ):
        result = hub_context(request)

        assert result["hub_id"] == 123
        assert result["debug_mode"] is False
        assert result["build_commit"] == "a1b2c3d4e5f6789012345678901234567890abcd"
        assert result["build_commit_short"] == "a1b2c3d4"  # First 8 chars
        assert result["build_tag"] == "v1.2.3"
        assert result["build_timestamp"] == "2024-01-15T12:00:00Z"


def test_hub_context_with_short_commit():
    # type: () -> None
    """Test hub_context with commit hash shorter than 8 chars."""
    request = MagicMock()

    # Create mock settings with short commit
    mock_settings = MagicMock(spec=["BUILD_COMMIT"])
    mock_settings.BUILD_COMMIT = "abc"

    with patch("iscc_hub.context.settings", mock_settings):
        result = hub_context(request)

        # Should not shorten if already less than 8 chars
        assert result["build_commit"] == "abc"
        assert result["build_commit_short"] == "abc"
