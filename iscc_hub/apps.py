import iscc_crypto as icr
from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class IsccHubConfig(AppConfig):
    # type: (None) -> None
    """Configuration for the ISCC-HUB Django app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "iscc_hub"
    verbose_name = "ISCC-HUB"

    def ready(self):
        # type: () -> None
        """Perform app initialization when Django starts."""
        # Validate HUB ID configuration
        self.validate_hub_id()
        self.validate_hub_seckey()

    def validate_hub_seckey(self):
        # type: () -> None
        """
        Validate that the signing key decodes to an Ed25519 key.

        The hub uses the key only when it signs, so an empty or broken value would otherwise start a hub that
        reports healthy but fails on every receipt, checkpoint and DID document request.
        """
        try:
            icr.key_from_secret(settings.ISCC_HUB_SECKEY)
        except (ValueError, AttributeError) as error:
            raise ImproperlyConfigured(f"ISCC_HUB_SECKEY is not a valid Ed25519 secret key: {error}") from error

    def validate_hub_id(self):
        # type: () -> None
        """Validate that the hub id is within the 12-bit range (0-4095)."""
        hub_id = getattr(settings, "ISCC_HUB_ID", None)

        if hub_id is None:
            raise ImproperlyConfigured("ISCC_HUB_ID is not configured in settings")

        if not isinstance(hub_id, int):
            raise ImproperlyConfigured(f"ISCC_HUB_ID must be an integer, got {type(hub_id).__name__}")

        if hub_id < 0 or hub_id > 4095:
            raise ImproperlyConfigured(f"ISCC_HUB_ID must be between 0 and 4095 (12-bit range), got {hub_id}")
