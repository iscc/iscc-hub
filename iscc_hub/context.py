"""Context processors for making common variables available in templates."""

from constance import config
from django.conf import settings


def hub_context(request):
    # type: (object) -> dict
    """
    Make hub-specific settings and build metadata available in all templates.

    :param request: The incoming HTTP request
    :return: Dictionary of context variables for templates
    """
    # Format build info for display
    build_commit = getattr(settings, "BUILD_COMMIT", "unknown")
    build_tag = getattr(settings, "BUILD_TAG", "unknown")
    build_timestamp = getattr(settings, "BUILD_TIMESTAMP", "unknown")

    # Shorten commit hash for display (first 8 chars)
    if build_commit != "unknown" and len(build_commit) >= 8:
        build_commit_short = build_commit[:8]
    else:
        build_commit_short = build_commit

    # Check if co-branding is configured
    has_cobranding = bool(config.ORG_NAME)

    return {
        "hub_id": getattr(settings, "ISCC_HUB_ID", 0),
        "debug_mode": getattr(settings, "DEBUG", False),
        "build_commit": build_commit,
        "build_commit_short": build_commit_short,
        "build_tag": build_tag,
        "build_timestamp": build_timestamp,
        # Co-branding configuration
        "has_cobranding": has_cobranding,
        "org_name": config.ORG_NAME,
        "org_logo": config.ORG_LOGO,
        "org_url": config.ORG_URL,
        "org_tagline": config.ORG_TAGLINE,
        "cta_enabled": config.CTA_ENABLED,
        "cta_title": config.CTA_TITLE,
        "cta_description": config.CTA_DESCRIPTION,
        "cta_button_text": config.CTA_BUTTON_TEXT,
        "cta_button_url": config.CTA_BUTTON_URL,
    }
