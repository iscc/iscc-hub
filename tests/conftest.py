"""
Pytest configuration for Django testing.
"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import django
import iscc_core as ic
import iscc_crypto as icr
import niquests
import pytest
from django.core.cache import cache
from iscc_crypto.resolve import ResolutionError

# Add project root to Python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Test data directory
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Published schema URIs carried in the `$schema` wire field (required on every message)
ISCC_NOTE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-0.8.0.json"
ISCC_NOTE_DELETE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-delete-0.8.0.json"


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
    """Provide Django Ninja TestClient for API testing."""
    from ninja.testing import TestClient

    from iscc_hub.api import api

    # Ensure database is available and properly initialized
    return TestClient(api)


# Canned iscc-search success body with real backend bytes: chunk_matches, unknown
# top-level / match-level fields (must be dropped by the hub's response projection),
# a metadata extension key (must be preserved), and an explicit metadata null.
STUB_SEARCH_SUCCESS = {
    "query": {
        "iscc_code": "ISCC:KECYCMZIOY36XXGZ7S6QJQ2AEEXPOVEHZYPK6GMSFLU3WF54UPZMTPY",
        "backend_echo": "dropped",
    },
    "global_matches": [
        {
            "iscc_id": "ISCC:MAIGIIFJRDGEQQAA",
            "score": 0.97,
            "types": {"CONTENT_TEXT_V0": 1.0, "DATA_NONE_V0": 0.5},
            "metadata": {
                "name": "Example Article",
                "gateway": "https://example.com/articles/123",
                "custom_ext": "kept",
            },
            "match_extra": "dropped",
        },
        {
            "iscc_id": "ISCC:MAIGXXFZRDGEQQBB",
            "score": 0.75,
            "types": {"CONTENT_TEXT_V0": 1.0},
            "metadata": None,
        },
    ],
    "chunk_matches": [],
    "backend_extra": "dropped",
}


class _StubSearchHandler(BaseHTTPRequestHandler):
    """Request handler serving the configurable canned response of a StubSearchBackend."""

    def log_message(self, format, *args):
        # type: (str, object) -> None
        """Silence request logging to keep test output clean."""

    def _serve(self):
        # type: () -> None
        """Record the request and reply per the backend's current configuration."""
        backend = self.server.backend  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        parts = urlsplit(self.path)
        backend.requests.append(
            {
                "method": self.command,
                "path": parts.path,
                "query": parts.query,
                # Lowercased keys: clients may send any header casing on the wire
                "headers": {key.lower(): value for key, value in self.headers.items()},
                "body": body,
            }
        )
        if backend.required_api_key is not None and self.headers.get("X-API-Key") != backend.required_api_key:
            self._respond(401, b'{"detail": "unauthorized"}')
            return
        if backend.redirect_to:
            self.send_response(302)
            self.send_header("Location", backend.redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if backend.delay:
            time.sleep(backend.delay)
        payload = backend.body if backend.body is not None else json.dumps(STUB_SEARCH_SUCCESS).encode("utf-8")
        self._respond(backend.status, payload)

    def _respond(self, status, payload):
        # type: (int, bytes) -> None
        """Send a JSON response with the given status and payload."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _serve
    do_POST = _serve


class StubSearchBackend:
    """
    Configurable in-process HTTP server mimicking an iscc-search backend.

    Tests mutate status/body/delay/redirect_to/required_api_key between requests
    to drive success, passthrough, retryable-failure, timeout, redirect, and auth
    scenarios; every received request is recorded for assertions on forwarding
    behavior.
    """

    def __init__(self):
        # type: () -> None
        """Bind the server to a random local port and initialize behavior knobs."""
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _StubSearchHandler)
        self.server.backend = self  # type: ignore[attr-defined]
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.status = 200
        self.body = None  # type: bytes|None  # None -> canned STUB_SEARCH_SUCCESS
        self.delay = 0.0
        self.redirect_to = None  # type: str|None  # respond 302 with this Location when set
        self.required_api_key = None  # type: str|None
        self.requests = []  # type: list[dict]

    def start(self):
        # type: () -> None
        """Start serving in a background thread."""
        self.thread.start()

    def stop(self):
        # type: () -> None
        """Stop the server and release the port."""
        self.server.shutdown()
        self.server.server_close()


class _DidWebHandler(BaseHTTPRequestHandler):
    """Request handler serving a DidWebServer's controller document (or a configured failure)."""

    def log_message(self, format, *args):
        # type: (str, object) -> None
        """Silence request logging to keep test output clean."""

    def do_GET(self):
        # type: () -> None
        """Record the request path and reply per the backend's current configuration."""
        backend = self.server.backend  # type: ignore[attr-defined]
        backend.requests.append(self.path)
        if backend.redirect_to is not None:
            self.send_response(302)
            self.send_header("Location", backend.redirect_to)
            self.end_headers()
            return
        if backend.status != 200:
            self._respond(backend.status, b'{"error": "did server failure"}')
            return
        payload = backend.body if backend.body is not None else json.dumps(backend.document).encode("utf-8")
        self._respond(200, payload)

    def _respond(self, status, payload):
        # type: (int, bytes) -> None
        """Send a JSON response with the given status and payload."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class DidWebServer:
    """
    In-process HTTP stand-in serving a DID controller document for did:web resolution tests.

    Models the real iscc-search StubSearchBackend pattern: a real ThreadingHTTPServer on a random
    local port. Tests mutate status/body to drive 404/5xx/malformed-doc scenarios and inspect
    ``requests`` to assert the positive cache prevents a second fetch.
    """

    def __init__(self, document):
        # type: (dict) -> None
        """Bind the server to a random local port and serve the given controller document."""
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _DidWebHandler)
        self.server.backend = self  # type: ignore[attr-defined]
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.document = document
        self.status = 200
        self.body = None  # type: bytes|None  # None -> serialized document; set bytes for malformed-doc
        self.redirect_to = None  # type: str|None  # set a URL to make every GET reply 302 -> Location
        self.requests = []  # type: list[str]

    def start(self):
        # type: () -> None
        """Start serving in a background thread."""
        self.thread.start()

    def stop(self):
        # type: () -> None
        """Stop the server and release the port."""
        self.server.shutdown()
        self.server.server_close()


class LocalDidHttpClient:
    """
    Real HttpClient (``async get_json``) that maps did:web HTTPS URLs onto a local test server.

    Policy B builds an ``https://example.com/.well-known/did.json`` URL from the controller; this
    client rewrites the host:port to the local DidWebServer and performs a real niquests fetch
    (real crypto, no mocks). A ``fail_hosts`` set lets a test simulate a fail-closed transport
    error instantly by raising, instead of waiting on a real socket timeout.
    """

    def __init__(self, base_url, fail_hosts=()):
        # type: (str, tuple) -> None
        """Target the given local base URL; raise for any host listed in fail_hosts."""
        self.base_url = base_url.rstrip("/")
        self.fail_hosts = set(fail_hosts)
        self.requests = []  # type: list[str]

    async def get_json(self, url):
        # type: (str) -> dict
        """Fetch JSON from the local server, rewriting the did:web HTTPS URL's host."""
        parts = urlsplit(url)
        if parts.hostname in self.fail_hosts:
            raise ResolutionError(f"simulated transport failure for {parts.hostname}")
        self.requests.append(parts.path)
        response = await niquests.aget(f"{self.base_url}{parts.path}", timeout=(5, 10))
        response.raise_for_status()
        return response.json()


@pytest.fixture
def proxy_state_reset():
    """Rebuild search-proxy I/O state from current settings around a test."""
    from iscc_hub.search_proxy import reset_proxy_state

    reset_proxy_state()
    yield
    reset_proxy_state()


@pytest.fixture
def search_stub(proxy_state_reset):
    """Configurable stub iscc-search backend on a random local port."""
    backend = StubSearchBackend()
    backend.start()
    yield backend
    backend.stop()


@pytest.fixture
def search_stub2(proxy_state_reset):
    """Second stub backend for failover scenarios."""
    backend = StubSearchBackend()
    backend.start()
    yield backend
    backend.stop()


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


# Fixed secret pinning the test signing identity, bound to controller did:web:example.com.
# Deterministic so the did:web controller document a DID server serves (and the pubkey embedded
# in every signed fixture note) are stable across runs.
EXAMPLE_SECKEY = "z3u2XXtFjKC5s442BV6i9mT6V2G8mcYkNW9BxZCuiC74RMuf"


@pytest.fixture
def example_keypair():
    # type: () -> icr.KeyPair
    """Return a deterministic test keypair bound to controller did:web:example.com."""
    return icr.key_from_secret(EXAMPLE_SECKEY, controller="did:web:example.com")


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
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": example_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)
    return signed_note


@pytest.fixture
def declarable_iscc_note(example_nonce, example_timestamp, example_keypair, example_iscc_data):
    # type: (str, str, icr.KeyPair, dict) -> dict
    """
    Create a signed IsccNote that satisfies the default-ON acceptance policies.

    Minimal note plus 256-bit ``units`` (Policy C) signed by the did:web-controlled
    example keypair (Policy A); pair with the ``did_resolved`` fixture so Policy B passes.
    Use this for default-ON POST /declaration success tests; ``minimal_iscc_note`` stays the
    units-less negative/validator fixture.
    """
    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": example_timestamp,
        "units": example_iscc_data["units"],
    }
    return icr.sign_json(note, example_keypair)


@pytest.fixture
def did_web_server(example_keypair):
    # type: (icr.KeyPair) -> DidWebServer
    """Run a local DID server serving the example keypair's controller document (did.json)."""
    server = DidWebServer(example_keypair.controller_document)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def did_resolved(settings, did_web_server):
    # type: (object, DidWebServer) -> DidWebServer
    """
    Make Policy B resolve did:web:example.com offline against the local DID server.

    Injects a real ``LocalDidHttpClient`` (bypassing the production SSRF-guarded client so the
    loopback test server is reachable) via the ``ISCC_HUB_DID_HTTP_CLIENT`` setting, and clears
    the per-process DID cache around the test so resolved documents do not leak between tests.
    """
    cache.clear()
    settings.ISCC_HUB_DID_HTTP_CLIENT = LocalDidHttpClient(did_web_server.base_url)
    yield did_web_server
    cache.clear()


@pytest.fixture
def clear_did_cache():
    """Clear the per-process DID document cache around a test (request explicitly in B tests)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def full_iscc_note(example_nonce, example_timestamp, example_keypair, example_iscc_data):
    # type: (str, str, icr.KeyPair, dict) -> dict
    """Create a full signed IsccNote with all optional fields."""
    full_note = {
        "$schema": ISCC_NOTE_SCHEMA,
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
        "$schema": ISCC_NOTE_SCHEMA,
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
        "$schema": ISCC_NOTE_SCHEMA,
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
        "iscc_code": "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY",
        "datahash": "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c",
        "nonce": f"{seq:032x}",  # Generate unique nonce based on seq
        "pubkey": "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",  # Valid Ed25519 public key
    }
    defaults.update(overrides)
    return IsccDeclaration.objects.create(**defaults)


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
        "pubkey": "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",  # Valid Ed25519 public key
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
