"""Tests for the ISCC-HUB Django app configuration."""

import threading
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from iscc_hub.apps import IsccHubConfig


def test_app_config_basic_attributes():
    """Test basic app configuration attributes."""
    # Get the actual registered app config
    app_config = apps.get_app_config("iscc_hub")

    assert app_config.name == "iscc_hub"
    assert app_config.verbose_name == "ISCC-HUB"
    assert app_config.default_auto_field == "django.db.models.BigAutoField"


def test_app_config_is_registered():
    """Test that the app is properly registered with Django."""
    assert "iscc_hub" in apps.all_models
    app_config = apps.get_app_config("iscc_hub")
    assert isinstance(app_config, IsccHubConfig)


@override_settings(ISCC_HUB_ID=42)
def test_validate_hub_id_valid():
    """Test validation with a valid node ID."""
    app_config = apps.get_app_config("iscc_hub")
    # Should not raise any exception
    app_config.validate_hub_id()


@override_settings(ISCC_HUB_ID=0)
def test_validate_hub_id_minimum():
    """Test validation with minimum valid node ID."""
    app_config = apps.get_app_config("iscc_hub")
    app_config.validate_hub_id()


@override_settings(ISCC_HUB_ID=4095)
def test_validate_hub_id_maximum():
    """Test validation with maximum valid node ID."""
    app_config = apps.get_app_config("iscc_hub")
    app_config.validate_hub_id()


def test_validate_hub_id_missing():
    """Test validation when ISCC_HUB_ID is not configured."""
    app_config = apps.get_app_config("iscc_hub")

    # Mock settings to simulate missing ISCC_HUB_ID
    with patch("iscc_hub.apps.settings") as mock_settings:
        mock_settings.ISCC_HUB_ID = None

        with pytest.raises(ImproperlyConfigured, match="ISCC_HUB_ID is not configured"):
            app_config.validate_hub_id()


@override_settings(ISCC_HUB_ID="not_an_int")
def test_validate_hub_id_wrong_type():
    """Test validation when ISCC_HUB_ID is not an integer."""
    app_config = apps.get_app_config("iscc_hub")

    with pytest.raises(ImproperlyConfigured, match="ISCC_HUB_ID must be an integer"):
        app_config.validate_hub_id()


@override_settings(ISCC_HUB_ID=-1)
def test_validate_hub_id_negative():
    """Test validation with negative node ID."""
    app_config = apps.get_app_config("iscc_hub")

    with pytest.raises(ImproperlyConfigured, match="ISCC_HUB_ID must be between 0 and 4095"):
        app_config.validate_hub_id()


@override_settings(ISCC_HUB_ID=4096)
def test_validate_hub_id_too_large():
    """Test validation with node ID exceeding 12-bit range."""
    app_config = apps.get_app_config("iscc_hub")

    with pytest.raises(ImproperlyConfigured, match="ISCC_HUB_ID must be between 0 and 4095"):
        app_config.validate_hub_id()


@override_settings(ISCC_HUB_ID=42)
def test_ready_method():
    """Test the ready() method initializes properly."""
    app_config = apps.get_app_config("iscc_hub")
    # Should not raise any exception
    app_config.ready()


def test_validate_hub_id_none_value():
    """Test validation when ISCC_HUB_ID is explicitly None."""
    app_config = apps.get_app_config("iscc_hub")

    # Mock getattr to return None for ISCC_HUB_ID
    with patch("iscc_hub.apps.getattr") as mock_getattr:
        mock_getattr.return_value = None

        with pytest.raises(ImproperlyConfigured, match="ISCC_HUB_ID is not configured"):
            app_config.validate_hub_id()


@override_settings(ISCC_HUB_SYNC_ON_STARTUP=False)
def test_sync_hub_list_on_startup_disabled():
    """Test that hub sync can be disabled via settings."""
    app_config = apps.get_app_config("iscc_hub")

    with patch("threading.Thread") as mock_thread_class:
        with patch("iscc_hub.apps.logger") as mock_logger:
            app_config.sync_hub_list_on_startup()
            # Thread should not be created when sync is disabled
            mock_thread_class.assert_not_called()
            mock_logger.debug.assert_called_with("Hub list sync on startup is disabled")


@override_settings(ISCC_HUB_SYNC_ON_STARTUP=True)
def test_sync_hub_list_on_startup_runs_in_thread():
    """Test that hub sync runs in a background thread when enabled."""
    app_config = apps.get_app_config("iscc_hub")

    # Reset the sync flag to allow the sync to run
    if hasattr(app_config.__class__, "_hub_sync_done"):
        delattr(app_config.__class__, "_hub_sync_done")

    with patch("threading.Thread") as mock_thread_class:
        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        app_config.sync_hub_list_on_startup()

        # Verify thread was created with correct parameters
        mock_thread_class.assert_called_once()
        call_kwargs = mock_thread_class.call_args.kwargs
        assert call_kwargs["daemon"] is True
        assert callable(call_kwargs["target"])

        # Verify thread was started
        mock_thread.start.assert_called_once()


@override_settings(ISCC_HUB_SYNC_ON_STARTUP=True)
def test_sync_hub_list_on_startup_success():
    """Test successful hub sync on startup."""
    app_config = apps.get_app_config("iscc_hub")

    # Reset the sync flag to allow the sync to run
    if hasattr(app_config.__class__, "_hub_sync_done"):
        delattr(app_config.__class__, "_hub_sync_done")

    # Create a successful sync result
    success_result = {"status": "success", "created": 2, "updated": 3, "deactivated": 1}

    with patch("iscc_hub.apps.logger") as mock_logger:
        with patch("iscc_hub.tasks.sync_hub_list", return_value=success_result):
            # Call the inner function directly to test its logic
            with patch("threading.Thread") as mock_thread_class:
                app_config.sync_hub_list_on_startup()

                # Get the target function from Thread creation
                target_func = mock_thread_class.call_args.kwargs["target"]

                # Run the target function
                target_func()

                # Verify success was logged
                mock_logger.info.assert_any_call("Starting hub list synchronization on startup")
                expected_log = "Hub list sync completed successfully: 2 created, 3 updated, 1 deactivated"
                mock_logger.info.assert_any_call(expected_log)


@override_settings(ISCC_HUB_SYNC_ON_STARTUP=True)
def test_sync_hub_list_on_startup_partial():
    """Test partial hub sync on startup with errors."""
    app_config = apps.get_app_config("iscc_hub")

    # Reset the sync flag to allow the sync to run
    if hasattr(app_config.__class__, "_hub_sync_done"):
        delattr(app_config.__class__, "_hub_sync_done")

    # Create a partial result with errors
    partial_result = {"status": "partial", "errors": ["Error 1", "Error 2"]}

    with patch("iscc_hub.apps.logger") as mock_logger:
        with patch("iscc_hub.tasks.sync_hub_list", return_value=partial_result):
            with patch("threading.Thread") as mock_thread_class:
                app_config.sync_hub_list_on_startup()

                # Get and run the target function
                target_func = mock_thread_class.call_args.kwargs["target"]
                target_func()

                # Verify warning was logged
                mock_logger.warning.assert_called_with(f"Hub list sync completed with errors: {partial_result}")


@override_settings(ISCC_HUB_SYNC_ON_STARTUP=True)
def test_sync_hub_list_on_startup_failure():
    """Test failed hub sync on startup."""
    app_config = apps.get_app_config("iscc_hub")

    # Reset the sync flag to allow the sync to run
    if hasattr(app_config.__class__, "_hub_sync_done"):
        delattr(app_config.__class__, "_hub_sync_done")

    # Create a failure result
    failure_result = {"status": "error", "error": "Connection timeout"}

    with patch("iscc_hub.apps.logger") as mock_logger:
        with patch("iscc_hub.tasks.sync_hub_list", return_value=failure_result):
            with patch("threading.Thread") as mock_thread_class:
                app_config.sync_hub_list_on_startup()

                # Get and run the target function
                target_func = mock_thread_class.call_args.kwargs["target"]
                target_func()

                # Verify error was logged
                mock_logger.error.assert_called_with("Hub list sync failed: Connection timeout")


@override_settings(ISCC_HUB_SYNC_ON_STARTUP=True)
def test_sync_hub_list_on_startup_exception():
    """Test hub sync on startup handles exceptions gracefully."""
    app_config = apps.get_app_config("iscc_hub")

    # Reset the sync flag to allow the sync to run
    if hasattr(app_config.__class__, "_hub_sync_done"):
        delattr(app_config.__class__, "_hub_sync_done")

    with patch("iscc_hub.apps.logger") as mock_logger:
        with patch("iscc_hub.tasks.sync_hub_list", side_effect=Exception("Unexpected error")):
            with patch("threading.Thread") as mock_thread_class:
                app_config.sync_hub_list_on_startup()

                # Get and run the target function
                target_func = mock_thread_class.call_args.kwargs["target"]
                target_func()

                # Verify exception was logged
                mock_logger.error.assert_called_with(
                    "Failed to sync hub list on startup: Unexpected error", exc_info=True
                )
