"""Tests for context processors."""

from unittest.mock import MagicMock, patch

from iscc_hub.context import hub_context


def test_hub_context_returns_hub_id():
    # type: () -> None
    """Test that hub_context returns the correct hub ID from settings."""
    request = MagicMock()

    with patch("iscc_hub.context.settings", ISCC_HUB_ID=42, DEBUG=True):
        result = hub_context(request)

        assert result["notary_node_id"] == 42
        assert result["debug_mode"] is True


def test_hub_context_with_missing_settings():
    # type: () -> None
    """Test that hub_context handles missing settings gracefully."""
    request = MagicMock()

    # Mock settings without the ISCC_HUB_ID and DEBUG attributes
    mock_settings = MagicMock(spec=[])

    with patch("iscc_hub.context.settings", mock_settings):
        result = hub_context(request)

        assert result["notary_node_id"] == 0
        assert result["debug_mode"] is False
