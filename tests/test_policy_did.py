"""
Tests for the DID identity policies (A presence, B verification) and the SSRF guard.

Policy B is exercised against a real in-process DID server with real Ed25519 keys (no mocks):
the local server serves the example keypair's controller document, and an injected real
HttpClient maps the did:web HTTPS URL onto it. The SSRF guard is exercised against the real
production GuardedHttpClient. API-level tests prove the wiring and HTTP status codes.
"""

import asyncio
import json
from io import BytesIO

import iscc_core as ic
import iscc_crypto as icr
import pytest
from django.db import connection
from django.test import override_settings

from iscc_hub import identity
from iscc_hub.exceptions import IdentityError
from tests.conftest import EXAMPLE_SECKEY, LocalDidHttpClient

ISCC_NOTE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-0.8.0.json"


@pytest.fixture(autouse=True)
def _isolate_did_cache(clear_did_cache):
    """Clear the per-process DID document cache around every test in this module."""
    yield


def _sign(note, keypair):
    # type: (dict, icr.KeyPair) -> dict
    """Sign a note with the given keypair (AUTO sigtype embeds controller + pubkey)."""
    return icr.sign_json(note, keypair)


def _note(example_iscc_data, example_nonce, example_timestamp, units=True):
    # type: (dict, str, str, bool) -> dict
    """Build an unsigned IsccNote, optionally carrying 256-bit units."""
    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": example_timestamp,
    }
    if units:
        note["units"] = example_iscc_data["units"]
    return note


# ---------------------------------------------------------------------------------------------
# Policy B — verify_note_identity against a real local DID server
# ---------------------------------------------------------------------------------------------


def test_verify_identity_authorized(did_resolved, declarable_iscc_note):
    # type: (object, dict) -> None
    """A controller document that lists the signing key authorizes the note."""
    identity.verify_note_identity(declarable_iscc_note)  # no raise


def test_verify_identity_cache_hit_single_fetch(did_resolved, declarable_iscc_note):
    # type: (object, dict) -> None
    """The positive cache prevents a second resolution: two verifies, one server request."""
    identity.verify_note_identity(declarable_iscc_note)
    identity.verify_note_identity(declarable_iscc_note)
    assert len(did_resolved.requests) == 1


def test_verify_identity_unauthorized_422(did_resolved, example_iscc_data, example_nonce, example_timestamp):
    # type: (object, dict, str, str) -> None
    """A document that does not list the signing key rejects with did_unauthorized (422)."""
    # Different key, same controller -> resolves example.com's doc, which lists a different pubkey.
    other = icr.key_generate(controller="did:web:example.com")
    signed = _sign(_note(example_iscc_data, example_nonce, example_timestamp), other)
    with pytest.raises(IdentityError) as exc:
        identity.verify_note_identity(signed)
    assert exc.value.code == "did_unauthorized"
    assert exc.value.status_code == 422


def test_verify_identity_server_error_503(did_resolved, declarable_iscc_note):
    # type: (object, dict) -> None
    """A 5xx from the controller host is the can't-tell case: did_unresolvable (503 + Retry-After)."""
    did_resolved.status = 500
    with pytest.raises(IdentityError) as exc:
        identity.verify_note_identity(declarable_iscc_note)
    assert exc.value.code == "did_unresolvable"
    assert exc.value.status_code == 503
    assert exc.value.headers["Retry-After"] == "5"


def test_verify_identity_not_found_503(did_resolved, declarable_iscc_note):
    # type: (object, dict) -> None
    """A 404 from the controller host fails closed as did_unresolvable (503)."""
    did_resolved.status = 404
    with pytest.raises(IdentityError) as exc:
        identity.verify_note_identity(declarable_iscc_note)
    assert exc.value.code == "did_unresolvable"


def test_verify_identity_malformed_doc_503(did_resolved, declarable_iscc_note):
    # type: (object, dict) -> None
    """A non-JSON controller document fails closed as did_unresolvable (503)."""
    did_resolved.body = b"this is not json"
    with pytest.raises(IdentityError) as exc:
        identity.verify_note_identity(declarable_iscc_note)
    assert exc.value.code == "did_unresolvable"


def test_verify_identity_transport_failure_503(settings, did_web_server, declarable_iscc_note, clear_did_cache):
    # type: (object, object, dict, object) -> None
    """A raised transport error (simulated, no socket wait) fails closed as did_unresolvable (503)."""
    settings.ISCC_HUB_DID_HTTP_CLIENT = LocalDidHttpClient(did_web_server.base_url, fail_hosts={"example.com"})
    with pytest.raises(IdentityError) as exc:
        identity.verify_note_identity(declarable_iscc_note)
    assert exc.value.code == "did_unresolvable"


def test_verify_identity_missing_controller_did_required(
    did_resolved, example_iscc_data, example_nonce, example_timestamp
):
    # type: (object, dict, str, str) -> None
    """A SELF_VERIFYING note (no controller) is rejected with did_required before any resolution."""
    keypair = icr.key_from_secret(EXAMPLE_SECKEY, controller="did:web:example.com")
    note = _note(example_iscc_data, example_nonce, example_timestamp)
    signed = icr.sign_json(note, keypair, sigtype=icr.SigType.SELF_VERIFYING)
    with pytest.raises(IdentityError) as exc:
        identity.verify_note_identity(signed)
    assert exc.value.code == "did_required"
    assert not did_resolved.requests  # never resolved


def test_verify_identity_requires_did_web_even_when_a_off(
    did_resolved, example_iscc_data, example_nonce, example_timestamp
):
    # type: (object, dict, str, str) -> None
    """B supersets A: a did:key controller is rejected by B independently of Policy A."""
    keypair = icr.key_generate()
    didkey = f"did:key:{keypair.public_key}"
    note = _note(example_iscc_data, example_nonce, example_timestamp)
    signed = icr.sign_json(note, keypair)
    signed["signature"]["controller"] = didkey  # not did:web (signature not re-verified before A check)
    with pytest.raises(IdentityError) as exc:
        identity.verify_note_identity(signed)
    assert exc.value.code == "did_required"


# ---------------------------------------------------------------------------------------------
# SSRF guard — the real production GuardedHttpClient
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.1", "169.254.1.1", "::1"])
def test_guard_blocks_non_public_hosts(host):
    # type: (str) -> None
    """The SSRF guard rejects loopback, private, and link-local hosts before any fetch."""
    from iscc_crypto.resolve import ResolutionError

    with pytest.raises(ResolutionError):
        identity.guard_public_host(host)


@pytest.mark.parametrize("host", ["8.8.8.8", "93.184.216.34"])
def test_guard_allows_public_hosts(host):
    # type: (str) -> None
    """The SSRF guard admits globally-routable hosts (IP literals resolve without network)."""
    identity.guard_public_host(host)  # no raise


def test_guard_rejects_unresolvable_host():
    # type: () -> None
    """An unresolvable host fails closed (rejected before any fetch)."""
    from iscc_crypto.resolve import ResolutionError

    with pytest.raises(ResolutionError):
        identity.guard_public_host("nonexistent.invalid.host.example.test")


def test_guarded_client_rejects_missing_host():
    # type: () -> None
    """GuardedHttpClient refuses a URL without a host."""
    from iscc_crypto.resolve import ResolutionError

    guarded = identity.GuardedHttpClient()
    with pytest.raises(ResolutionError):
        asyncio.run(guarded.get_json("https:///.well-known/did.json"))


def test_guarded_client_delegates_after_guard(did_web_server):
    # type: (object) -> None
    """After the guard admits a public host, GuardedHttpClient delegates to its inner client."""
    inner = LocalDidHttpClient(did_web_server.base_url)
    guarded = identity.GuardedHttpClient(client=inner)
    # 8.8.8.8 passes the guard; the inner client rewrites the path onto the local server.
    document = asyncio.run(guarded.get_json("https://8.8.8.8/.well-known/did.json"))
    assert document["id"] == "did:web:example.com"


def test_http_client_defaults_to_guarded(settings):
    # type: (object) -> None
    """With no injected client, http_client() returns the SSRF-guarded production client."""
    settings.ISCC_HUB_DID_HTTP_CLIENT = None
    assert isinstance(identity.http_client(), identity.GuardedHttpClient)


def test_redirect_safe_client_fetches_without_redirect(did_web_server):
    # type: (object) -> None
    """With no redirect, the production inner client fetches and parses the controller document."""
    client = identity.RedirectSafeHttpClient()
    document = asyncio.run(client.get_json(f"{did_web_server.base_url}/.well-known/did.json"))
    assert document["id"] == "did:web:example.com"


def test_redirect_safe_client_refuses_redirect_to_private(did_web_server):
    # type: (object) -> None
    """A 30x toward a private address is refused, not followed: the SSRF guard cannot be bypassed."""
    from iscc_crypto.resolve import ResolutionError

    did_web_server.redirect_to = "http://127.0.0.1/private/did.json"
    client = identity.RedirectSafeHttpClient()
    with pytest.raises(ResolutionError):
        asyncio.run(client.get_json(f"{did_web_server.base_url}/.well-known/did.json"))
    # Only the initial request was made; the private redirect target was never fetched.
    assert did_web_server.requests == ["/.well-known/did.json"]


def test_guarded_client_defaults_to_redirect_safe_inner():
    # type: () -> None
    """The default GuardedHttpClient delegates to the redirect-safe production client."""
    assert isinstance(identity.GuardedHttpClient()._client, identity.RedirectSafeHttpClient)


def test_verify_identity_ssrf_loopback_503(example_iscc_data, example_nonce, example_timestamp):
    # type: (dict, str, str) -> None
    """A did:web controller resolving to loopback is blocked by the guard -> did_unresolvable (503)."""
    keypair = icr.key_from_secret(EXAMPLE_SECKEY, controller="did:web:127.0.0.1")
    signed = _sign(_note(example_iscc_data, example_nonce, example_timestamp), keypair)
    with override_settings(ISCC_HUB_DID_HTTP_CLIENT=None):  # real GuardedHttpClient
        with pytest.raises(IdentityError) as exc:
            identity.verify_note_identity(signed)
    assert exc.value.code == "did_unresolvable"
    assert exc.value.status_code == 503


# ---------------------------------------------------------------------------------------------
# API integration — full default-ON pipeline through the in-process client
# ---------------------------------------------------------------------------------------------


def _wipe_log_tables():
    """Reset the append-only log/declaration tables between API tests."""
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM iscc_declaration")
        cursor.execute("DELETE FROM iscc_logrecord")
        cursor.execute("DELETE FROM iscc_logstate")
        connection.commit()


@pytest.fixture
def clean_log():
    """Provide a clean log around an API test."""
    _wipe_log_tables()
    yield
    _wipe_log_tables()


def _post(api_client, note):
    # type: (object, dict) -> object
    """POST a signed note to /declaration through the in-process client."""
    return api_client.post(
        "/declaration",
        data=json.dumps(note).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


@pytest.mark.django_db(transaction=True)
def test_api_declaration_missing_units_returns_422(
    api_client, clean_log, did_resolved, example_keypair, example_iscc_data, example_nonce, current_timestamp
):
    # type: (object, object, object, icr.KeyPair, dict, str, str) -> None
    """Policy C: a declaration without units is rejected with 422 (units field)."""
    signed = _sign(_note(example_iscc_data, example_nonce, current_timestamp, units=False), example_keypair)
    response = _post(api_client, signed)
    assert response.status_code == 422
    assert response.json()["error"]["field"] == "units"


@pytest.mark.django_db(transaction=True)
def test_api_declaration_short_units_returns_422(
    api_client, clean_log, did_resolved, example_keypair, example_iscc_data, example_nonce, current_timestamp
):
    # type: (object, object, object, icr.KeyPair, dict, str, str) -> None
    """Policy C: 64-bit units are rejected with 422 and the error names the offending MainType."""
    text = "Hello World!"
    units64 = [
        ic.gen_meta_code(text, "Test Description", bits=64)["iscc"],
        ic.gen_text_code(text, bits=64)["iscc"],
        ic.gen_data_code(BytesIO(text.encode("utf-8")), bits=64)["iscc"],
    ]
    note = _note(example_iscc_data, example_nonce, current_timestamp, units=False)
    note["units"] = units64
    response = _post(api_client, _sign(note, example_keypair))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["field"] == "units"
    assert "META" in error["message"]


@pytest.mark.django_db(transaction=True)
def test_api_declaration_did_unauthorized_returns_422(
    api_client, clean_log, did_resolved, example_iscc_data, example_nonce, current_timestamp
):
    # type: (object, object, object, dict, str, str) -> None
    """Policy B: a controller that does not authorize the key is rejected with 422 did_unauthorized."""
    other = icr.key_generate(controller="did:web:example.com")
    response = _post(api_client, _sign(_note(example_iscc_data, example_nonce, current_timestamp), other))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "did_unauthorized"


@pytest.mark.django_db(transaction=True)
def test_api_declaration_did_unresolvable_returns_503(
    api_client, clean_log, did_resolved, example_keypair, example_iscc_data, example_nonce, current_timestamp
):
    # type: (object, object, object, icr.KeyPair, dict, str, str) -> None
    """Policy B: an unreachable controller host yields 503 with a Retry-After header."""
    did_resolved.status = 503
    signed = _sign(_note(example_iscc_data, example_nonce, current_timestamp), example_keypair)
    response = _post(api_client, signed)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "did_unresolvable"
    assert response["Retry-After"] == "5"


@pytest.mark.django_db(transaction=True)
def test_api_declaration_verify_did_off_skips_resolution(
    api_client, clean_log, clear_did_cache, example_keypair, example_iscc_data, example_nonce, current_timestamp
):
    # type: (object, object, object, icr.KeyPair, dict, str, str) -> None
    """With Policy B off, a declaration succeeds without any DID resolution (no client injected)."""
    signed = _sign(_note(example_iscc_data, example_nonce, current_timestamp), example_keypair)
    with override_settings(ISCC_HUB_VERIFY_DID=False):
        response = _post(api_client, signed)
    assert response.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_api_declaration_require_did_off_accepts_did_key(
    api_client, clean_log, clear_did_cache, example_iscc_data, example_nonce, current_timestamp
):
    # type: (object, object, object, dict, str, str) -> None
    """With both DID policies off, a did:key-controlled declaration is accepted."""
    keypair = icr.key_generate()  # did:key only, no did:web controller
    signed = _sign(_note(example_iscc_data, example_nonce, current_timestamp), keypair)
    with override_settings(ISCC_HUB_REQUIRE_DID=False, ISCC_HUB_VERIFY_DID=False):
        response = _post(api_client, signed)
    assert response.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_api_declaration_non_did_web_controller_returns_422(
    api_client, clean_log, did_resolved, example_iscc_data, example_nonce, current_timestamp
):
    # type: (object, object, object, dict, str, str) -> None
    """Policy A: a note whose signature carries no did:web controller is rejected with 422 did_required."""
    keypair = icr.key_generate()  # AUTO embeds no controller (key has none)
    response = _post(api_client, _sign(_note(example_iscc_data, example_nonce, current_timestamp), keypair))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "did_required"
