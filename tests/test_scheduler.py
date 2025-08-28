"""
Tests for the checkpoint scheduler.
"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from iscc_hub.scheduler import CheckpointScheduler, start_scheduler, stop_scheduler


@pytest.fixture
def cleanup_scheduler():
    # type: () -> None
    """Fixture to ensure schedulers are properly stopped after tests."""
    yield
    # Stop any running global scheduler
    stop_scheduler()


@pytest.mark.django_db
def test_scheduler_disabled_when_setting_false():
    # type: () -> None
    """Test that scheduler doesn't start when disabled."""
    with override_settings(ISCC_HUB_CHECKPOINT_ENABLED=False):
        scheduler = CheckpointScheduler()
        scheduler.start()
        assert scheduler.thread is None
        assert not scheduler.is_leader


@pytest.mark.django_db
def test_scheduler_enabled_when_setting_true(tmp_path, cleanup_scheduler):
    # type: () -> None
    """Test that scheduler starts when enabled."""
    with override_settings(ISCC_HUB_CHECKPOINT_ENABLED=True, ISCC_HUB_DB_PATH=tmp_path / "test.db"):
        scheduler = CheckpointScheduler()
        scheduler.start()
        assert scheduler.thread is not None
        assert scheduler.is_leader
        assert scheduler.thread.is_alive()
        # Clean up
        scheduler.stop_event.set()
        scheduler.release_leader_lock()


@pytest.mark.django_db
def test_lock_file_creation(tmp_path):
    # type: () -> None
    """Test that lock file is created correctly."""
    with override_settings(ISCC_HUB_DB_PATH=tmp_path / "test.db"):
        scheduler = CheckpointScheduler()
        assert scheduler.acquire_leader_lock()
        assert scheduler.lock_file.exists()
        scheduler.is_leader = True  # Need to set this for release to work
        scheduler.release_leader_lock()
        assert not scheduler.lock_file.exists()


@pytest.mark.django_db
def test_only_one_leader(tmp_path):
    # type: () -> None
    """Test that only one scheduler can be leader."""
    with override_settings(ISCC_HUB_DB_PATH=tmp_path / "test.db"):
        scheduler1 = CheckpointScheduler()
        scheduler2 = CheckpointScheduler()

        assert scheduler1.acquire_leader_lock()
        assert not scheduler2.acquire_leader_lock()

        scheduler1.is_leader = True  # Need to set this for release
        scheduler1.release_leader_lock()
        assert scheduler2.acquire_leader_lock()
        scheduler2.is_leader = True  # Need to set this for release
        scheduler2.release_leader_lock()


@pytest.mark.django_db
def test_dead_process_lock_takeover(tmp_path):
    # type: () -> None
    """Test that scheduler takes over lock from dead process."""
    lock_file = tmp_path / ".scheduler.lock"
    # Write a non-existent PID
    lock_file.write_text("99999999")

    with override_settings(ISCC_HUB_DB_PATH=tmp_path / "test.db"):
        scheduler = CheckpointScheduler()
        assert scheduler.acquire_leader_lock()
        scheduler.is_leader = True  # Need to set this for release
        scheduler.release_leader_lock()


@pytest.mark.django_db
def test_invalid_lock_file(tmp_path):
    # type: () -> None
    """Test that scheduler handles invalid lock file."""
    lock_file = tmp_path / ".scheduler.lock"
    # Write invalid content
    lock_file.write_text("not-a-pid")

    with override_settings(ISCC_HUB_DB_PATH=tmp_path / "test.db"):
        scheduler = CheckpointScheduler()
        assert scheduler.acquire_leader_lock()
        scheduler.is_leader = True  # Need to set this for release
        scheduler.release_leader_lock()


@pytest.mark.django_db
def test_scheduler_no_lock_when_another_leader(tmp_path, cleanup_scheduler):
    # type: () -> None
    """Test that scheduler doesn't acquire lock when another leader exists."""
    with override_settings(ISCC_HUB_CHECKPOINT_ENABLED=True, ISCC_HUB_DB_PATH=tmp_path / "test.db"):
        scheduler1 = CheckpointScheduler()
        scheduler2 = CheckpointScheduler()

        # First scheduler becomes leader
        scheduler1.start()
        assert scheduler1.is_leader

        # Second scheduler can't become leader
        scheduler2.start()
        assert not scheduler2.is_leader

        # Clean up
        scheduler1.stop_event.set()
        scheduler1.release_leader_lock()


@pytest.mark.django_db
def test_release_lock_when_not_leader(tmp_path):
    # type: () -> None
    """Test releasing lock when not leader doesn't crash."""
    with override_settings(ISCC_HUB_DB_PATH=tmp_path / "test.db"):
        scheduler = CheckpointScheduler()
        scheduler.release_leader_lock()  # Should not raise


@pytest.mark.django_db
def test_global_start_scheduler_function(tmp_path, cleanup_scheduler):
    # type: () -> None
    """Test the global start_scheduler function."""
    with override_settings(ISCC_HUB_CHECKPOINT_ENABLED=True, ISCC_HUB_DB_PATH=tmp_path / "test.db"):
        # Start scheduler
        start_scheduler()

        # Try to start again (should use existing instance)
        start_scheduler()


@pytest.mark.django_db
def test_apps_config_scheduler_not_started_during_tests():
    # type: () -> None
    """Test that AppConfig doesn't start scheduler during tests."""
    import iscc_hub
    from iscc_hub.apps import IsccHubConfig

    app_config = IsccHubConfig("iscc_hub", iscc_hub)

    # Test with pytest in modules (should not start)
    with patch("iscc_hub.scheduler.start_scheduler") as mock_start:
        app_config.start_checkpoint_scheduler()
        mock_start.assert_not_called()


@pytest.mark.django_db
def test_apps_config_scheduler_started_with_runserver():
    # type: () -> None
    """Test that AppConfig starts scheduler with runserver."""
    import iscc_hub
    from iscc_hub.apps import IsccHubConfig

    app_config = IsccHubConfig("iscc_hub", iscc_hub)

    # Test with runserver (should start)
    original_modules = dict(sys.modules)
    # Remove pytest from modules temporarily
    if "pytest" in sys.modules:
        del sys.modules["pytest"]
    try:
        with patch("sys.argv", ["manage.py", "runserver"]):
            with patch.dict("os.environ", {"RUN_MAIN": "true"}):
                with patch("iscc_hub.scheduler.start_scheduler") as mock_start:
                    app_config.start_checkpoint_scheduler()
                    mock_start.assert_called_once()
    finally:
        # Restore original modules
        sys.modules.update(original_modules)


@pytest.mark.django_db
def test_apps_config_scheduler_not_started_without_run_main():
    # type: () -> None
    """Test that AppConfig doesn't start scheduler without RUN_MAIN during runserver."""
    import iscc_hub
    from iscc_hub.apps import IsccHubConfig

    app_config = IsccHubConfig("iscc_hub", iscc_hub)

    # Test with runserver but without RUN_MAIN (should NOT start)
    original_modules = dict(sys.modules)
    # Remove pytest from modules temporarily
    if "pytest" in sys.modules:
        del sys.modules["pytest"]
    try:
        with patch("sys.argv", ["manage.py", "runserver"]):
            with patch.dict("os.environ", {}, clear=True):  # No RUN_MAIN
                with patch("iscc_hub.scheduler.start_scheduler") as mock_start:
                    app_config.start_checkpoint_scheduler()
                    mock_start.assert_not_called()
    finally:
        # Restore original modules
        sys.modules.update(original_modules)


@pytest.mark.django_db
def test_apps_config_scheduler_started_with_gunicorn():
    # type: () -> None
    """Test that AppConfig starts scheduler with gunicorn."""
    import iscc_hub
    from iscc_hub.apps import IsccHubConfig

    app_config = IsccHubConfig("iscc_hub", iscc_hub)

    # Test with gunicorn module (should start)
    # Temporarily remove pytest to simulate production environment
    pytest_module = sys.modules.pop("pytest", None)
    try:
        with patch("sys.argv", []):
            with patch.dict("sys.modules", {"gunicorn": MagicMock()}):
                with patch("iscc_hub.scheduler.start_scheduler") as mock_start:
                    app_config.start_checkpoint_scheduler()
                    mock_start.assert_called_once()
    finally:
        if pytest_module:
            sys.modules["pytest"] = pytest_module


@pytest.mark.django_db
def test_apps_config_scheduler_not_started_during_migrations():
    # type: () -> None
    """Test that AppConfig doesn't start scheduler during migrations."""
    import iscc_hub
    from iscc_hub.apps import IsccHubConfig

    app_config = IsccHubConfig("iscc_hub", iscc_hub)

    # Test with migrate command (should not start)
    with patch("sys.argv", ["manage.py", "migrate"]):
        with patch("iscc_hub.scheduler.start_scheduler") as mock_start:
            app_config.start_checkpoint_scheduler()
            mock_start.assert_not_called()


@pytest.mark.django_db
def test_apps_config_scheduler_not_started_during_other_commands():
    # type: () -> None
    """Test that AppConfig doesn't start scheduler during other management commands."""
    import iscc_hub
    from iscc_hub.apps import IsccHubConfig

    app_config = IsccHubConfig("iscc_hub", iscc_hub)

    # Remove pytest module temporarily to simulate non-test environment
    original_modules = dict(sys.modules)
    if "pytest" in sys.modules:
        del sys.modules["pytest"]

    try:
        # Test with various management commands (should not start)
        for command in ["collectstatic", "shell", "dbshell", "showmigrations"]:
            with patch("sys.argv", ["manage.py", command]):
                with patch("iscc_hub.scheduler.start_scheduler") as mock_start:
                    app_config.start_checkpoint_scheduler()
                    mock_start.assert_not_called()
    finally:
        # Restore original modules
        sys.modules.update(original_modules)
