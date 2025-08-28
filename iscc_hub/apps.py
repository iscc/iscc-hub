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

        # Start checkpoint scheduler if we're running the server
        self.start_checkpoint_scheduler()

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

    def start_checkpoint_scheduler(self):
        # type: () -> None
        """Start the checkpoint scheduler if appropriate."""
        import os
        import sys

        # Skip during tests
        if "test" in sys.argv or "pytest" in sys.modules:
            return

        # Skip during management commands (except runserver)
        management_commands = ["migrate", "makemigrations", "collectstatic", "shell", "dbshell", "showmigrations"]
        if any(cmd in sys.argv for cmd in management_commands):
            return

        # For Django's autoreload, only run in the main process
        # RUN_MAIN is set by Django's autoreloader to avoid double-execution
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
            return

        # Check if we're in a server context (runserver, gunicorn, uvicorn)
        is_server = any(arg in sys.argv for arg in ["runserver", "runserver_plus"]) or any(
            mod in sys.modules for mod in ["gunicorn", "uvicorn"]
        )

        if is_server:
            from iscc_hub.scheduler import start_scheduler

            start_scheduler()
