"""Context processors for making common variables available in templates."""

from django.conf import settings


def hub_context(request):
    """Make notary-specific settings available in all templates."""
    return {
        "notary_node_id": getattr(settings, "ISCC_HUB_ID", 0),
        "debug_mode": getattr(settings, "DEBUG", False),
    }
