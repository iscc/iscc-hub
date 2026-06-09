"""Context processors for making common variables available in templates."""

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

    # Co-branding is read from set-once server settings; defaults keep the branding card hidden.
    org_name = getattr(settings, "ISCC_HUB_ORG_NAME", "")
    has_cobranding = bool(org_name)

    return {
        "hub_id": getattr(settings, "ISCC_HUB_ID", 0),
        "debug_mode": getattr(settings, "DEBUG", False),
        "build_commit": build_commit,
        "build_commit_short": build_commit_short,
        "build_tag": build_tag,
        "build_timestamp": build_timestamp,
        # Co-branding configuration
        "has_cobranding": has_cobranding,
        "org_name": org_name,
        "org_logo": getattr(settings, "ISCC_HUB_ORG_LOGO", ""),
        "org_url": getattr(settings, "ISCC_HUB_ORG_URL", ""),
        "org_tagline": getattr(settings, "ISCC_HUB_ORG_TAGLINE", ""),
        "cta_enabled": getattr(settings, "ISCC_HUB_CTA_ENABLED", False),
        "cta_title": getattr(settings, "ISCC_HUB_CTA_TITLE", ""),
        "cta_description": getattr(settings, "ISCC_HUB_CTA_DESCRIPTION", ""),
        "cta_button_text": getattr(settings, "ISCC_HUB_CTA_BUTTON_TEXT", ""),
        "cta_button_url": getattr(settings, "ISCC_HUB_CTA_BUTTON_URL", ""),
    }
