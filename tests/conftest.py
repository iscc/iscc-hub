"""
Pytest configuration for Django testing.
"""

import os
import sys
from pathlib import Path

import django
import pytest
from django.conf import settings

# Add project root to Python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def pytest_configure(config):
    """Configure Django settings for testing."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iscc_hub.settings")

    # Set test environment variables
    os.environ["DJANGO_DEBUG"] = "True"
    os.environ["DJANGO_SECRET_KEY"] = "test-secret-key-for-testing-only"
    os.environ["ISCC_HUB_DB_NAME"] = "test_db.sqlite3"
    os.environ["ISCC_HUB_DOMAIN"] = "testserver"
    os.environ["ISCC_HUB_SECKEY"] = "test-hub-secret-key"
    os.environ["ISCC_HUB_ID"] = "1"
    os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver,localhost"

    # Skip Ninja registry check for testing
    os.environ["NINJA_SKIP_REGISTRY"] = "1"

    # Setup Django
    django.setup()


@pytest.fixture
def api_client():
    """Provide Django Ninja TestAsyncClient for API testing."""
    from ninja.testing import TestAsyncClient

    from iscc_hub.api import api

    return TestAsyncClient(api)


@pytest.fixture
def django_db_setup():
    """Override Django's database setup for tests."""

    # Use in-memory database for tests
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
