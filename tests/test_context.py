"""Tests for context processors."""

from django.conf import settings
from django.test import override_settings

from iscc_hub.context import hub_context

# hub_context only reads from settings; its request argument is unused, so we pass None.


@override_settings(
    BUILD_COMMIT="unknown",
    BUILD_TAG="unknown",
    BUILD_TIMESTAMP="unknown",
    ISCC_HUB_ORG_NAME="",
    ISCC_HUB_ORG_LOGO="",
    ISCC_HUB_ORG_URL="",
    ISCC_HUB_ORG_TAGLINE="",
    ISCC_HUB_CTA_ENABLED=False,
    ISCC_HUB_CTA_TITLE="",
    ISCC_HUB_CTA_DESCRIPTION="",
    ISCC_HUB_CTA_BUTTON_TEXT="",
    ISCC_HUB_CTA_BUTTON_URL="",
)
def test_hub_context_empty_branding_defaults():
    # type: () -> None
    """Default settings expose the hub id and leave co-branding empty/disabled."""
    result = hub_context(None)

    # The context processor forwards the live settings verbatim.
    assert result["hub_id"] == settings.ISCC_HUB_ID
    assert result["debug_mode"] == settings.DEBUG
    # Build metadata defaults to "unknown" (else branch of the commit-shortening logic)
    assert result["build_commit"] == "unknown"
    assert result["build_commit_short"] == "unknown"
    assert result["build_tag"] == "unknown"
    assert result["build_timestamp"] == "unknown"
    # Co-branding stays hidden when ISCC_HUB_ORG_NAME is empty
    assert result["has_cobranding"] is False
    assert result["org_name"] == ""
    assert result["org_logo"] == ""
    assert result["org_url"] == ""
    assert result["org_tagline"] == ""
    assert result["cta_enabled"] is False
    assert result["cta_title"] == ""
    assert result["cta_description"] == ""
    assert result["cta_button_text"] == ""
    assert result["cta_button_url"] == ""


@override_settings(
    ISCC_HUB_ORG_NAME="Example University",
    ISCC_HUB_ORG_LOGO="https://example.com/logo.svg",
    ISCC_HUB_ORG_URL="https://example.com",
    ISCC_HUB_ORG_TAGLINE="Digital Archives at Example University",
    ISCC_HUB_CTA_ENABLED=True,
    ISCC_HUB_CTA_TITLE="Integrate with Our Services",
    ISCC_HUB_CTA_DESCRIPTION="Connect your systems to our content registry.",
    ISCC_HUB_CTA_BUTTON_TEXT="Explore Our Repository",
    ISCC_HUB_CTA_BUTTON_URL="https://example.com/repository",
)
def test_hub_context_populated_branding():
    # type: () -> None
    """Populated ISCC_HUB_* branding settings enable the co-branding card and flow through."""
    result = hub_context(None)

    assert result["has_cobranding"] is True
    assert result["org_name"] == "Example University"
    assert result["org_logo"] == "https://example.com/logo.svg"
    assert result["org_url"] == "https://example.com"
    assert result["org_tagline"] == "Digital Archives at Example University"
    assert result["cta_enabled"] is True
    assert result["cta_title"] == "Integrate with Our Services"
    assert result["cta_description"] == "Connect your systems to our content registry."
    assert result["cta_button_text"] == "Explore Our Repository"
    assert result["cta_button_url"] == "https://example.com/repository"


@override_settings(
    BUILD_COMMIT="a1b2c3d4e5f6789012345678901234567890abcd",
    BUILD_TAG="v1.2.3",
    BUILD_TIMESTAMP="2024-01-15T12:00:00Z",
)
def test_hub_context_with_build_metadata():
    # type: () -> None
    """A long commit hash is shortened to its first 8 characters."""
    result = hub_context(None)

    assert result["build_commit"] == "a1b2c3d4e5f6789012345678901234567890abcd"
    assert result["build_commit_short"] == "a1b2c3d4"  # First 8 chars
    assert result["build_tag"] == "v1.2.3"
    assert result["build_timestamp"] == "2024-01-15T12:00:00Z"


@override_settings(BUILD_COMMIT="abc")
def test_hub_context_with_short_commit():
    # type: () -> None
    """A commit hash shorter than 8 characters is left unchanged."""
    result = hub_context(None)

    assert result["build_commit"] == "abc"
    assert result["build_commit_short"] == "abc"
