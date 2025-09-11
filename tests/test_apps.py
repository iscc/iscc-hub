"""Tests for the ISCC-HUB Django app configuration."""

from unittest.mock import patch

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
