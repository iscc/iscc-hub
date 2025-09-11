import logging
import os
import threading

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class IsccHubConfig(AppConfig):
    # type: (None) -> None
    """Configuration for the ISCC-HUB Django app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "iscc_hub"
    verbose_name = "ISCC-HUB"
    _hub_sync_done = False

    def ready(self):
        # type: () -> None
        """Perform app initialization when Django starts."""
        # Validate HUB ID configuration
        self.validate_hub_id()

        # Sync hub list on startup in background thread
        self.sync_hub_list_on_startup()

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

    def sync_hub_list_on_startup(self):
        # type: () -> None
        """Sync hub list from GitHub on application startup."""
        # Check if sync is enabled via settings (defaults to True in production, False in tests)
        import sys

        # Default: sync enabled unless we're in test mode
        default_sync = not ("test" in sys.argv or "pytest" in sys.modules)
        sync_enabled = getattr(settings, "ISCC_HUB_SYNC_ON_STARTUP", default_sync)

        if not sync_enabled:
            logger.debug("Hub list sync on startup is disabled")
            return

        # Skip if we're in a reloader process that has already synced
        # Django's autoreloader sets RUN_MAIN when it's the actual server process
        if os.environ.get("RUN_MAIN") != "true" and "runserver" in sys.argv:
            logger.debug("Skipping hub sync in reloader parent process")
            return

        # Use a class variable to track if we've already synced in this process
        # This prevents multiple syncs during auto-reload
        if hasattr(self.__class__, "_hub_sync_done"):
            logger.debug("Hub list sync already performed in this process")
            return
        self.__class__._hub_sync_done = True

        def run_sync():
            # type: () -> None
            """Run hub list sync in background."""
            try:
                logger.info("Starting hub list synchronization on startup")
                from iscc_hub.tasks import sync_hub_list

                result = sync_hub_list()
                if result["status"] == "success":
                    logger.info(
                        f"Hub list sync completed successfully: "
                        f"{result['created']} created, {result['updated']} updated, "
                        f"{result['deactivated']} deactivated"
                    )
                elif result["status"] == "partial":
                    logger.warning(f"Hub list sync completed with errors: {result}")
                else:
                    logger.error(f"Hub list sync failed: {result.get('error', 'Unknown error')}")
            except Exception as e:
                # Don't fail startup if sync fails
                logger.error(f"Failed to sync hub list on startup: {e}", exc_info=True)

        # Run in background thread to avoid blocking startup
        sync_thread = threading.Thread(target=run_sync, daemon=True)
        sync_thread.start()
        logger.debug("Hub list sync initiated in background thread")
