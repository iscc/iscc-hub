"""
Pytest configuration for Django testing.
"""

import os
import sys
from io import BytesIO
from pathlib import Path

import django
import iscc_core as ic
import iscc_crypto as icr
import pytest

# Add project root to Python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Test data directory
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def pytest_configure(config):
    """Configure Django settings for testing."""
    # Set test environment variables
    test_env_vars = {
        "DJANGO_SETTINGS_MODULE": "iscc_hub.settings",
        "DJANGO_DEBUG": "True",
        "DJANGO_SECRET_KEY": "test-secret-key-for-testing-only",
        "ISCC_HUB_DB_NAME": str(DATA_DIR / "test_db.sqlite3"),
        "ISCC_HUB_DOMAIN": "testserver",
        "ISCC_HUB_SECKEY": "z3u2hnGm6Vp6zXdB4x51vp2VMGqHfB6BcF3cvgkC5aDxPsJR",
        "ISCC_HUB_ID": "1",
        "DJANGO_ALLOWED_HOSTS": "testserver,localhost",
        "NINJA_SKIP_REGISTRY": "1",  # Skip Ninja registry check for testing
    }

    # Override environment
    for key, value in test_env_vars.items():
        os.environ[key] = value

    # Setup Django
    django.setup()


@pytest.fixture(scope="session")
def django_db_use_migrations():
    """
    Disable migrations for test database creation.

    This makes test database setup faster by creating tables directly from models
    rather than running all migrations.
    """
    return False


@pytest.fixture
def api_client(db):
    """Provide Django Ninja TestAsyncClient for API testing."""
    from ninja.testing import TestAsyncClient

    from iscc_hub.api import api

    # Ensure database is available and properly initialized
    return TestAsyncClient(api)


def create_iscc_from_text(text="Hello World!"):
    # type: (str) -> dict
    """Create deterministic ISCC components from text."""
    mcode = ic.gen_meta_code(text, "Test Description", bits=256)
    ccode = ic.gen_text_code(text, bits=256)
    dcode = ic.gen_data_code(BytesIO(text.encode("utf-8")), bits=256)
    icode = ic.gen_instance_code(BytesIO(text.encode("utf-8")), bits=256)
    iscc_code = ic.gen_iscc_code([mcode["iscc"], ccode["iscc"], dcode["iscc"], icode["iscc"]])["iscc"]

    result = {}
    result.update(mcode)
    result.update(ccode)
    result.update(dcode)
    result.update(icode)
    result["iscc"] = iscc_code
    result["units"] = [mcode["iscc"], ccode["iscc"], dcode["iscc"]]
    return result


@pytest.fixture
def example_keypair():
    # type: () -> icr.KeyPair
    """Generate a deterministic test keypair."""
    # Use a fixed controller for deterministic output
    controller = "did:web:example.com"
    return icr.key_generate(controller=controller)


def generate_test_iscc_id(hub_id=1, seq=1):
    # type: (int, int) -> str
    """Generate a valid test ISCC-ID with deterministic timestamp."""
    from iscc_hub.iscc_id import IsccID

    # Use a base timestamp (2025-01-01) plus sequence number for uniqueness
    base_timestamp_us = 1735689600_000_000  # 2025-01-01 00:00:00 UTC
    timestamp_us = base_timestamp_us + seq
    return str(IsccID.from_timestamp(timestamp_us, hub_id))


@pytest.fixture
def example_nonce():
    # type: () -> str
    """Return a deterministic test nonce."""
    # First 12 bits = 0x001 = hub_id 1 (matches ISCC_HUB_ID in test env)
    return "001faa3f18c7b9407a48536a9b00c4cb"


@pytest.fixture
def example_timestamp():
    # type: () -> str
    """Return a deterministic test timestamp."""
    return "2025-01-15T12:00:00.000Z"


@pytest.fixture
def current_timestamp():
    # type: () -> str
    """Return a timestamp close to current time for tolerance testing."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@pytest.fixture
def example_iscc_data():
    # type: () -> dict
    """Return deterministic ISCC data from 'Hello World!' text."""
    return create_iscc_from_text()


@pytest.fixture
def minimal_iscc_note(example_nonce, example_timestamp, example_keypair, example_iscc_data):
    # type: (str, str, icr.KeyPair, dict) -> dict
    """Create a minimal signed IsccNote with deterministic values."""
    minimal_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": example_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)
    return signed_note


@pytest.fixture
def full_iscc_note(example_nonce, example_timestamp, example_keypair, example_iscc_data):
    # type: (str, str, icr.KeyPair, dict) -> dict
    """Create a full signed IsccNote with all optional fields."""
    full_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": example_timestamp,
        "gateway": "https://example.com/iscc_id/{iscc_id}/metadata",
        "units": example_iscc_data["units"],
        "metahash": example_iscc_data["metahash"],
    }

    # Sign the note
    signed_note = icr.sign_json(full_note, example_keypair)
    return signed_note


@pytest.fixture
def unsigned_iscc_note(example_nonce, example_timestamp, example_iscc_data):
    # type: (str, str, dict) -> dict
    """Create an unsigned IsccNote with a placeholder signature."""
    return {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": example_timestamp,
        "signature": {
            "version": "ISCC-SIG v1.0",
            "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
            "proof": "zInvalidSignature",
        },
    }


@pytest.fixture
def invalid_signature_note(example_nonce, example_timestamp, example_keypair, example_iscc_data):
    # type: (str, str, icr.KeyPair, dict) -> dict
    """Create an IsccNote with a tampered signature."""
    note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": example_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(note, example_keypair)

    # Tamper with the data after signing
    signed_note["nonce"] = "fffaaa3f18c7b9407a48536a9b00c4cb"

    return signed_note


# Factory functions for test objects
def create_test_declaration(seq=1, **overrides):
    # type: (int, dict) -> object
    """Factory function for creating test IsccDeclaration objects."""
    from iscc_hub.models import IsccDeclaration

    defaults = {
        "iscc_id": generate_test_iscc_id(seq=seq),
        "event_seq": seq,
        "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
        "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
        "nonce": f"{seq:032x}",  # Generate unique nonce based on seq
        "actor": "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
        "deleted": False,
    }
    defaults.update(overrides)
    return IsccDeclaration.objects.create(**defaults)


def create_test_event(seq=1, **overrides):
    # type: (int, dict) -> object
    """Factory function for creating test Event objects."""
    from iscc_hub.models import Event

    defaults = {
        "seq": seq,
        "note": {"test": "data"},
        "iscc_id": generate_test_iscc_id(seq=seq),
    }
    defaults.update(overrides)
    return Event.objects.create(**defaults)


# Helper functions for testing
def assert_validation_error(func, *args, expected_message=None, **kwargs):
    # type: (callable, tuple, str|None, dict) -> Exception
    """Helper for testing validation errors."""
    with pytest.raises(ValueError) as exc_info:
        func(*args, **kwargs)
    if expected_message:
        assert expected_message in str(exc_info.value)
    return exc_info.value


@pytest.fixture
def sample_declaration_data():
    # type: () -> dict
    """Sample data for creating IsccDeclaration objects."""
    return {
        "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
        "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
        "nonce": "fedcba9876543210fedcba9876543210",
        "actor": "7VWFd39mGRe6B9KwFa5qPQkqbTYXBgTRgGPvs3QHrEV5",
    }


@pytest.fixture
def sample_validation_data():
    # type: () -> dict
    """Common validation test data."""
    return {
        "valid_nonce": "000faa3f18c7b9407a48536a9b00c4cb",
        "invalid_nonce": "INVALID_NONCE",
        "valid_timestamp": "2025-01-15T12:00:00.000Z",
        "invalid_timestamp": "not-a-timestamp",
        "valid_iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
        "invalid_iscc_code": "INVALID:CODE",
        "valid_datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
        "invalid_datahash": "not-a-hash",
    }
