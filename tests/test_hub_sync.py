"""
Tests for hub list synchronization functionality and sync_hubs management command.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings
from django_q.models import Schedule

from iscc_hub.models import Hub
from iscc_hub.tasks import sync_hub_list


@pytest.mark.django_db(transaction=True)
def test_sync_hub_list_testnet():
    # type: () -> None
    """Test hub sync for testnet (REALM-0)."""
    # Prepare mock response data
    hub_data = {
        "version": 1,
        "network": "testnet",
        "hubs": [
            {
                "hub_id": 0,
                "pubkey": "z6MkqbHELZopsq6eKrn6qxiAgRoVvwp2Vp7mPfKsvrbYmGwJ",
                "url": "https://sb0.iscc.id/",
                "active": True,
            },
            {
                "hub_id": 1,
                "pubkey": "z6MkkGLQqKYg9cQCxiQvjy3VSDnh8LVZT5pwm6bVzRZNcXSd",
                "url": "https://sb1.iscc.id/",
                "active": True,
            },
        ],
    }

    # Mock niquests.get
    mock_response = Mock()
    mock_response.text = yaml.dump(hub_data)
    mock_response.raise_for_status = Mock()

    with patch("iscc_hub.tasks.niquests.get", return_value=mock_response) as mock_get:
        with override_settings(ISCC_HUB_REALM=0):
            result = sync_hub_list()

    # Verify the correct URL was called
    expected_url = "https://raw.githubusercontent.com/iscc/iscc-hub/main/hubs/testnet.yaml"
    mock_get.assert_called_once_with(expected_url, timeout=30.0)

    # Check the result
    assert result["status"] == "success"
    assert result["network"] == "testnet"
    assert result["created"] == 2
    assert result["updated"] == 0
    assert result["deactivated"] == 0
    assert result["total_hubs"] == 2

    # Verify hubs were created in database
    assert Hub.objects.count() == 2
    hub0 = Hub.objects.get(hub_id=0)
    assert hub0.pubkey == "z6MkqbHELZopsq6eKrn6qxiAgRoVvwp2Vp7mPfKsvrbYmGwJ"
    assert hub0.url == "https://sb0.iscc.id/"
    assert hub0.active is True


@pytest.mark.django_db(transaction=True)
def test_sync_hub_list_mainnet():
    # type: () -> None
    """Test hub sync for mainnet (REALM-1)."""
    # Prepare mock response data
    hub_data = {
        "version": 1,
        "network": "mainnet",
        "hubs": [
            {
                "hub_id": 100,
                "pubkey": "z6MkmQZLN5yNPa8vAeViKY6kPtYVLrzFsFCr2cgEdVDPmVbt",
                "url": "https://hub100.iscc.id/",
                "active": True,
            },
        ],
    }

    # Mock niquests.get
    mock_response = Mock()
    mock_response.text = yaml.dump(hub_data)
    mock_response.raise_for_status = Mock()

    with patch("iscc_hub.tasks.niquests.get", return_value=mock_response) as mock_get:
        with override_settings(ISCC_HUB_REALM=1):
            result = sync_hub_list()

    # Verify the correct URL was called
    expected_url = "https://raw.githubusercontent.com/iscc/iscc-hub/main/hubs/mainnet.yaml"
    mock_get.assert_called_once_with(expected_url, timeout=30.0)

    # Check the result
    assert result["status"] == "success"
    assert result["network"] == "mainnet"


@pytest.mark.django_db(transaction=True)
def test_sync_hub_list_update_existing():
    # type: () -> None
    """Test hub sync updates existing hubs."""
    # Create an existing hub
    Hub.objects.create(
        hub_id=0,
        pubkey="z6MkqbHELZopsq6eKrn6qxiAgRoVvwp2Vp7mPfKsvrbYmGwJ",
        url="https://old-url.example/",
        active=False,
    )

    # Prepare mock response data with updated info
    hub_data = {
        "version": 1,
        "network": "testnet",
        "hubs": [
            {
                "hub_id": 0,
                "pubkey": "z6MkqbHELZopsq6eKrn6qxiAgRoVvwp2Vp7mPfKsvrbYmGwJ",
                "url": "https://new-url.example/",
                "active": True,
            },
        ],
    }

    # Mock niquests.get
    mock_response = Mock()
    mock_response.text = yaml.dump(hub_data)
    mock_response.raise_for_status = Mock()

    with patch("iscc_hub.tasks.niquests.get", return_value=mock_response):
        with override_settings(ISCC_HUB_REALM=0):
            result = sync_hub_list()

    # Check the result
    assert result["status"] == "success"
    assert result["created"] == 0
    assert result["updated"] == 1

    # Verify hub was updated
    hub = Hub.objects.get(hub_id=0)
    assert hub.url == "https://new-url.example/"
    assert hub.active is True


@pytest.mark.django_db(transaction=True)
def test_sync_hub_list_deactivate_removed():
    # type: () -> None
    """Test hub sync deactivates hubs not in authoritative list."""
    # Create existing hubs, one will be removed
    Hub.objects.create(
        hub_id=0,
        pubkey="z6MkqbHELZopsq6eKrn6qxiAgRoVvwp2Vp7mPfKsvrbYmGwJ",
        url="https://sb0.iscc.id/",
        active=True,
    )
    Hub.objects.create(
        hub_id=999,
        pubkey="z6MkmQZLN5yNPa8vAeViKY6kPtYVLrzFsFCr2cgEdVDPmVbt",
        url="https://removed.example/",
        active=True,
    )

    # Prepare mock response data without hub 999
    hub_data = {
        "version": 1,
        "network": "testnet",
        "hubs": [
            {
                "hub_id": 0,
                "pubkey": "z6MkqbHELZopsq6eKrn6qxiAgRoVvwp2Vp7mPfKsvrbYmGwJ",
                "url": "https://sb0.iscc.id/",
                "active": True,
            },
        ],
    }

    # Mock niquests.get
    mock_response = Mock()
    mock_response.text = yaml.dump(hub_data)
    mock_response.raise_for_status = Mock()

    with patch("iscc_hub.tasks.niquests.get", return_value=mock_response):
        with override_settings(ISCC_HUB_REALM=0):
            result = sync_hub_list()

    # Check the result
    assert result["status"] == "success"
    assert result["deactivated"] == 1

    # Verify hub 999 was deactivated
    hub_999 = Hub.objects.get(hub_id=999)
    assert hub_999.active is False

    # Verify hub 0 is still active
    hub_0 = Hub.objects.get(hub_id=0)
    assert hub_0.active is True


@pytest.mark.django_db(transaction=True)
def test_sync_hub_list_network_mismatch():
    # type: () -> None
    """Test hub sync fails on network mismatch."""
    # Prepare mock response data with wrong network
    hub_data = {
        "version": 1,
        "network": "mainnet",  # Wrong network for REALM-0
        "hubs": [],
    }

    # Mock niquests.get
    mock_response = Mock()
    mock_response.text = yaml.dump(hub_data)
    mock_response.raise_for_status = Mock()

    with patch("iscc_hub.tasks.niquests.get", return_value=mock_response):
        with override_settings(ISCC_HUB_REALM=0):
            result = sync_hub_list()

    # Check error result
    assert result["status"] == "error"
    assert "Network mismatch" in result["error"]


@pytest.mark.django_db(transaction=True)
def test_sync_hub_list_http_error():
    # type: () -> None
    """Test hub sync handles HTTP errors gracefully."""
    # Mock niquests.get to raise an exception
    with patch("iscc_hub.tasks.niquests.get") as mock_get:
        mock_get.side_effect = Exception("Connection failed")

        with override_settings(ISCC_HUB_REALM=0):
            result = sync_hub_list()

    # Check error result
    assert result["status"] == "error"
    assert "Connection failed" in result["error"]


@pytest.mark.django_db(transaction=True)
def test_install_tasks_command_creates_hub_sync_schedule():
    # type: () -> None
    """Test that install_tasks command creates hub sync schedule."""
    from django.core.management import call_command

    # Ensure no schedule exists initially
    Schedule.objects.filter(func="iscc_hub.tasks.sync_hub_list").delete()

    # Run the management command
    call_command("install_tasks")

    # Verify hub sync schedule was created
    schedule = Schedule.objects.get(func="iscc_hub.tasks.sync_hub_list")
    assert schedule.name == "Hub List Synchronization"
    assert schedule.schedule_type == Schedule.CRON
    assert schedule.cron == "0 * * * *"  # Every hour
    assert schedule.repeats == -1


@pytest.mark.django_db(transaction=True)
def test_install_tasks_command_idempotent():
    # type: () -> None
    """Test that install_tasks command is idempotent."""
    from django.core.management import call_command

    # Run command twice
    call_command("install_tasks")
    call_command("install_tasks")

    # Should only have one hub sync schedule
    schedules = Schedule.objects.filter(func="iscc_hub.tasks.sync_hub_list")
    assert schedules.count() == 1


# Tests for sync_hubs management command


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_from_github_success():
    # type: () -> None
    """Test successful sync from GitHub via management command."""
    success_result = {
        "status": "success",
        "created": 2,
        "updated": 3,
        "deactivated": 1,
    }

    with patch("iscc_hub.management.commands.sync_hubs.sync_hub_list") as mock_sync:
        mock_sync.return_value = success_result
        out = StringIO()
        call_command("sync_hubs", stdout=out)

        # Verify the mock was called
        assert mock_sync.called
        output = out.getvalue()
        assert "Syncing hub list from GitHub..." in output
        assert "Hub sync completed successfully" in output
        assert "2 created, 3 updated, 1 deactivated" in output


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_from_github_partial():
    # type: () -> None
    """Test partial sync from GitHub with errors via management command."""
    partial_result = {
        "status": "partial",
        "errors": ["Error 1", "Error 2"],
    }

    with patch("iscc_hub.management.commands.sync_hubs.sync_hub_list") as mock_sync:
        mock_sync.return_value = partial_result
        out = StringIO()
        call_command("sync_hubs", stdout=out)

        output = out.getvalue()
        assert "Hub sync completed with errors" in output


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_from_github_failure():
    # type: () -> None
    """Test failed sync from GitHub via management command."""
    failure_result = {
        "status": "error",
        "error": "Connection timeout",
    }

    with patch("iscc_hub.management.commands.sync_hubs.sync_hub_list", return_value=failure_result):
        out = StringIO()
        err = StringIO()
        call_command("sync_hubs", stdout=out, stderr=err)

        error_output = err.getvalue()
        assert "Hub sync failed: Connection timeout" in error_output


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_from_github_quiet():
    # type: () -> None
    """Test quiet mode suppresses output for management command."""
    success_result = {
        "status": "success",
        "created": 1,
        "updated": 0,
        "deactivated": 0,
    }

    with patch("iscc_hub.management.commands.sync_hubs.sync_hub_list", return_value=success_result):
        out = StringIO()
        call_command("sync_hubs", "--quiet", stdout=out)

        output = out.getvalue()
        assert "Syncing hub list from GitHub..." not in output


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_import_from_file_success():
    # type: () -> None
    """Test successful import from YAML file via management command."""
    # Create temporary YAML file
    hub_data = {
        "network": "testnet",
        "hubs": [
            {
                "hub_id": 1,
                "pubkey": "z6MkqCganwv6TXSy5r3XLJf5KsjadEWDgbTP5apycN4zbdhk",
                "url": "https://hub1.example.com",
                "active": True,
            },
            {
                "hub_id": 2,
                "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
                "url": "https://hub2.example.com",
                "active": False,
            },
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(hub_data, f)
        temp_path = f.name

    try:
        out = StringIO()
        call_command("sync_hubs", f"--file={temp_path}", stdout=out)

        # Check that hubs were created
        assert Hub.objects.count() == 2
        hub1 = Hub.objects.get(hub_id=1)
        assert hub1.pubkey == "z6MkqCganwv6TXSy5r3XLJf5KsjadEWDgbTP5apycN4zbdhk"
        assert hub1.url == "https://hub1.example.com"
        assert hub1.active is True

        hub2 = Hub.objects.get(hub_id=2)
        assert hub2.pubkey == "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB"
        assert hub2.url == "https://hub2.example.com"
        assert hub2.active is False

        output = out.getvalue()
        assert "Import complete: 2 created, 0 updated" in output
    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_import_from_file_update_existing():
    # type: () -> None
    """Test importing updates existing hubs via management command."""
    # Create initial hub
    Hub.objects.create(
        hub_id=1,
        pubkey="z6MkqCganwv6TXSy5r3XLJf5KsjadEWDgbTP5apycN4zbdhk",
        url="https://old.example.com",
        active=False,
    )

    # Create YAML with updated data
    hub_data = {
        "network": "testnet",
        "hubs": [
            {
                "hub_id": 1,
                "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
                "url": "https://new.example.com",
                "active": True,
            },
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(hub_data, f)
        temp_path = f.name

    try:
        out = StringIO()
        call_command("sync_hubs", f"--file={temp_path}", stdout=out)

        # Check that hub was updated
        assert Hub.objects.count() == 1
        hub = Hub.objects.get(hub_id=1)
        assert hub.pubkey == "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB"
        assert hub.url == "https://new.example.com"
        assert hub.active is True

        output = out.getvalue()
        assert "Import complete: 0 created, 1 updated" in output
    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_import_from_file_clear_existing():
    # type: () -> None
    """Test importing with --clear removes existing hubs via management command."""
    # Create initial hubs
    Hub.objects.create(
        hub_id=1,
        pubkey="z6MkqCganwv6TXSy5r3XLJf5KsjadEWDgbTP5apycN4zbdhk",
        url="https://hub1.example.com",
    )
    Hub.objects.create(
        hub_id=2,
        pubkey="z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
        url="https://hub2.example.com",
    )

    # Create YAML with different hub
    hub_data = {
        "network": "testnet",
        "hubs": [
            {
                "hub_id": 3,
                "pubkey": "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
                "url": "https://hub3.example.com",
            },
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(hub_data, f)
        temp_path = f.name

    try:
        out = StringIO()
        call_command("sync_hubs", f"--file={temp_path}", "--clear", stdout=out)

        # Check that only new hub exists
        assert Hub.objects.count() == 1
        hub = Hub.objects.get(hub_id=3)
        assert hub.pubkey == "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1"

        output = out.getvalue()
        assert "Cleared existing hubs" in output
    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_import_file_not_found():
    # type: () -> None
    """Test error when file doesn't exist for management command."""
    out = StringIO()
    err = StringIO()
    call_command("sync_hubs", "--file=nonexistent.yaml", stdout=out, stderr=err)

    error_output = err.getvalue()
    assert "File not found: nonexistent.yaml" in error_output


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_import_invalid_yaml():
    # type: () -> None
    """Test error with invalid YAML file for management command."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("invalid: yaml: content: [")
        temp_path = f.name

    try:
        out = StringIO()
        err = StringIO()
        call_command("sync_hubs", f"--file={temp_path}", stdout=out, stderr=err)

        error_output = err.getvalue()
        assert "Failed to read YAML file" in error_output
    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_import_missing_hubs_section():
    # type: () -> None
    """Test error when YAML file has no 'hubs' section for management command."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"network": "testnet"}, f)
        temp_path = f.name

    try:
        out = StringIO()
        err = StringIO()
        call_command("sync_hubs", f"--file={temp_path}", stdout=out, stderr=err)

        error_output = err.getvalue()
        assert "No 'hubs' section found in YAML file" in error_output
    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_import_skip_hub_without_id():
    # type: () -> None
    """Test that hubs without hub_id are skipped for management command."""
    hub_data = {
        "network": "testnet",
        "hubs": [
            {
                "hub_id": 1,
                "pubkey": "z6MkqCganwv6TXSy5r3XLJf5KsjadEWDgbTP5apycN4zbdhk",
                "url": "https://hub1.example.com",
            },
            {
                "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
                "url": "https://hub2.example.com",
            },  # Missing hub_id
            {
                "hub_id": 3,
                "pubkey": "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
                "url": "https://hub3.example.com",
            },
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(hub_data, f)
        temp_path = f.name

    try:
        out = StringIO()
        err = StringIO()
        call_command("sync_hubs", f"--file={temp_path}", stdout=out, stderr=err)

        # Only 2 hubs should be created (the one without hub_id is skipped)
        assert Hub.objects.count() == 2
        assert Hub.objects.filter(hub_id__in=[1, 3]).count() == 2

        error_output = err.getvalue()
        assert "Skipping hub without hub_id" in error_output
    finally:
        Path(temp_path).unlink()


@pytest.mark.django_db(transaction=True)
def test_sync_hubs_command_import_quiet_mode():
    # type: () -> None
    """Test quiet mode for file import via management command."""
    hub_data = {
        "network": "testnet",
        "hubs": [
            {
                "hub_id": 1,
                "pubkey": "z6MkqCganwv6TXSy5r3XLJf5KsjadEWDgbTP5apycN4zbdhk",
                "url": "https://hub1.example.com",
            },
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(hub_data, f)
        temp_path = f.name

    try:
        out = StringIO()
        call_command("sync_hubs", f"--file={temp_path}", "--quiet", stdout=out)

        output = out.getvalue()
        # In quiet mode, all output is suppressed
        assert "Created hub 1" not in output
        assert "Import complete" not in output
        assert output.strip() == ""

        # But the hub should still be created
        assert Hub.objects.count() == 1
    finally:
        Path(temp_path).unlink()
