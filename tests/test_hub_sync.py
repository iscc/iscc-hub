"""
Tests for hub list synchronization functionality.
"""

from unittest.mock import Mock, patch

import pytest
import yaml
from django.conf import settings
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
