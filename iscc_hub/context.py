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

    return {
        "hub_id": getattr(settings, "ISCC_HUB_ID", 0),
        "debug_mode": getattr(settings, "DEBUG", False),
        "build_commit": build_commit,
        "build_commit_short": build_commit_short,
        "build_tag": build_tag,
        "build_timestamp": build_timestamp,
    }
