"""Minimal tests for POST /declaration endpoint to achieve 100% coverage."""

import json

import httpx
import iscc_core as ic
import pytest
from constance.test import override_config
from django.db import connection

from iscc_hub.models import PubKey

# Published schema URI carried in the `$schema` wire field (required on every IsccNote)
ISCC_NOTE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-0.8.0.json"


@pytest.fixture(autouse=True)
def clear_database():
    """Clear database before each test."""
    # Clear database before test
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM iscc_event")
            cursor.execute("DELETE FROM iscc_declaration")
            connection.commit()
    except Exception:
        pass  # Tables might not exist yet
    yield
    # Clean up after test
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM iscc_event")
            cursor.execute("DELETE FROM iscc_declaration")
            connection.commit()
    except Exception:
        pass


@pytest.mark.django_db(transaction=False)
def test_declaration_permission_denied_no_pubkey(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test declaration denied when OPEN_ACCESS=False and pubkey not authorized."""
    import iscc_crypto as icr

    # Clear any existing PubKey records
    PubKey.objects.all().delete()

    # Create a minimal note
    minimal_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    # Test with OPEN_ACCESS=False
    with override_config(OPEN_ACCESS=False):
        # Use httpx client with live server
        with httpx.Client(base_url=live_server.url) as client:
            response = client.post(
                "/declaration",
                json=signed_note,
                headers={"Accept": "application/json"},
            )

        # Should be unauthorized
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "unauthorized"
        assert "Invalid or inactive pubkey" in data["error"]["message"]


@pytest.mark.django_db(transaction=False)
def test_declaration_permission_denied_inactive_pubkey(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test declaration denied when OPEN_ACCESS=False and pubkey is inactive."""
    import iscc_crypto as icr

    # Clear any existing PubKey records
    PubKey.objects.all().delete()

    # Create a minimal note
    minimal_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    # Get pubkey from signed note and create an inactive PubKey record
    pubkey = signed_note["signature"]["pubkey"]
    PubKey.objects.create(pubkey=pubkey, is_active=False, label="Test inactive key")

    # Test with OPEN_ACCESS=False
    with override_config(OPEN_ACCESS=False):
        # Use httpx client with live server
        with httpx.Client(base_url=live_server.url) as client:
            response = client.post(
                "/declaration",
                json=signed_note,
                headers={"Accept": "application/json"},
            )

        # Should be unauthorized
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "unauthorized"
        assert "Invalid or inactive pubkey" in data["error"]["message"]


@pytest.mark.django_db(transaction=False)
def test_declaration_permission_allowed_with_active_pubkey(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test declaration allowed when OPEN_ACCESS=False and pubkey is active."""
    import iscc_crypto as icr

    # Clear any existing PubKey records
    PubKey.objects.all().delete()

    # Create a minimal note
    minimal_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    # Get pubkey from signed note and create an active PubKey record
    pubkey = signed_note["signature"]["pubkey"]
    PubKey.objects.create(pubkey=pubkey, is_active=True, label="Test active key")

    # Test with OPEN_ACCESS=False
    with override_config(OPEN_ACCESS=False):
        # Use httpx client with live server
        with httpx.Client(base_url=live_server.url) as client:
            response = client.post(
                "/declaration",
                json=signed_note,
                headers={"Accept": "application/json"},
            )

        # Should be successful
        assert response.status_code == 201
        data = response.json()
        # Response is an IsccReceipt (W3C Verifiable Credential)
        assert "@context" in data
        assert "credentialSubject" in data
        assert "declaration" in data["credentialSubject"]
        assert "iscc_id" in data["credentialSubject"]["declaration"]


@pytest.mark.django_db(transaction=False)
def test_declaration_success_minimal(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test successful declaration with minimal IsccNote returns IsccReceipt."""
    import iscc_crypto as icr

    # Create a minimal note with current timestamp
    minimal_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    # Use httpx client with live server
    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

        if response.status_code != 201:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.json()}")
        assert response.status_code == 201
        data = response.json()

        # Verify IsccReceipt structure
        assert "@context" in data
        assert "type" in data
        assert "issuer" in data
        assert "credentialSubject" in data
        assert "proof" in data

        # Verify credential subject contains declaration
        credential_subject = data["credentialSubject"]
        assert "id" in credential_subject
        assert "declaration" in credential_subject

        # Verify declaration contains expected fields
        declaration = credential_subject["declaration"]
        assert "seq" in declaration
        assert "iscc_id" in declaration
        assert "iscc_note" in declaration


@pytest.mark.django_db(transaction=False)
def test_declaration_invalid_json(live_server):
    """Test invalid JSON returns 400 error."""
    with httpx.Client() as client:
        response = client.post(
            f"{live_server.url}/declaration",
            content=b"invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422  # Unprocessable Entity for invalid JSON
        data = response.json()

        # Verify ErrorResponse structure
        assert "error" in data
        error = data["error"]
        assert "message" in error
        assert "code" in error
        assert error["message"] == "Invalid JSON in request body"
        assert error["code"] == "invalid_format"  # ValidationError uses specific codes


@pytest.mark.django_db(transaction=False)
def test_declaration_duplicate_rejected(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test duplicate declaration is rejected with 409 Conflict."""
    import iscc_crypto as icr

    # Create and sign first declaration
    first_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_first = icr.sign_json(first_note, example_keypair)

    with httpx.Client() as client:
        # First declaration should succeed
        response = client.post(f"{live_server.url}/declaration", json=signed_first)
        assert response.status_code == 201

        # Create second declaration with same datahash but different nonce
        second_nonce = "001abcd1234567890abcdef123456700"  # Different nonce, same hub_id prefix
        second_note = {
            "$schema": ISCC_NOTE_SCHEMA,
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],  # Same datahash
            "nonce": second_nonce,
            "timestamp": current_timestamp,
        }
        signed_second = icr.sign_json(second_note, example_keypair)

        # Second declaration should be rejected with 409
        response = client.post(f"{live_server.url}/declaration", json=signed_second)
        assert response.status_code == 409

        data = response.json()
        assert "error" in data
        error = data["error"]
        assert error["code"] == "duplicate_declaration"
        assert error["field"] == "datahash"
        assert "existing_iscc_id" in error
        assert "existing_actor" in error
        assert example_iscc_data["datahash"] in error["message"]


@pytest.mark.django_db(transaction=False)
def test_declaration_duplicate_forced(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test duplicate declaration succeeds with force header."""
    import iscc_crypto as icr

    # Create and sign first declaration
    first_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_first = icr.sign_json(first_note, example_keypair)

    with httpx.Client() as client:
        # First declaration should succeed
        response = client.post(f"{live_server.url}/declaration", json=signed_first)
        assert response.status_code == 201

        # Create second declaration with same datahash but different nonce
        second_nonce = "001abcd1234567890abcdef123456700"  # Different nonce, same hub_id prefix
        second_note = {
            "$schema": ISCC_NOTE_SCHEMA,
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],  # Same datahash
            "nonce": second_nonce,
            "timestamp": current_timestamp,
        }
        signed_second = icr.sign_json(second_note, example_keypair)

        # Second declaration should succeed with force header
        headers = {"X-Force-Declaration": "true"}
        response = client.post(f"{live_server.url}/declaration", json=signed_second, headers=headers)
        assert response.status_code == 201

        # Should return valid receipt
        data = response.json()
        assert "credentialSubject" in data
        assert "declaration" in data["credentialSubject"]


@pytest.mark.django_db(transaction=False)
def test_declaration_duplicate_force_variations(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test various force header values work correctly."""
    import iscc_crypto as icr

    # Create and sign first declaration
    first_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_first = icr.sign_json(first_note, example_keypair)

    with httpx.Client() as client:
        # First declaration
        response = client.post(f"{live_server.url}/declaration", json=signed_first)
        assert response.status_code == 201

        # Test force="1" works
        second_nonce = "001abcd1234567890abcdef123456700"
        second_note = {
            "$schema": ISCC_NOTE_SCHEMA,
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": second_nonce,
            "timestamp": current_timestamp,
        }
        signed_second = icr.sign_json(second_note, example_keypair)

        headers = {"X-Force-Declaration": "1"}
        response = client.post(f"{live_server.url}/declaration", json=signed_second, headers=headers)
        assert response.status_code == 201

        # Test force="TRUE" (case insensitive) works
        third_nonce = "001abcd1234567890abcdef123456701"
        third_note = {
            "$schema": ISCC_NOTE_SCHEMA,
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": third_nonce,
            "timestamp": current_timestamp,
        }
        signed_third = icr.sign_json(third_note, example_keypair)

        headers = {"X-Force-Declaration": "TRUE"}
        response = client.post(f"{live_server.url}/declaration", json=signed_third, headers=headers)
        assert response.status_code == 201

        # Test force="false" is rejected
        fourth_nonce = "001abcd1234567890abcdef123456702"
        fourth_note = {
            "$schema": ISCC_NOTE_SCHEMA,
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": fourth_nonce,
            "timestamp": current_timestamp,
        }
        signed_fourth = icr.sign_json(fourth_note, example_keypair)

        headers = {"X-Force-Declaration": "false"}
        response = client.post(f"{live_server.url}/declaration", json=signed_fourth, headers=headers)
        assert response.status_code == 409


@pytest.mark.django_db(transaction=False)
def test_declaration_nonce_reuse_error(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test nonce reuse returns 400 error."""
    import iscc_crypto as icr

    # Create a minimal note with current timestamp
    minimal_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    with httpx.Client() as client:
        # First declaration should succeed
        response1 = client.post(f"{live_server.url}/declaration", json=signed_note)
        assert response1.status_code == 201

        # Second declaration with same nonce should fail (use force header to bypass duplicate check)
        response2 = client.post(
            f"{live_server.url}/declaration", json=signed_note, headers={"X-Force-Declaration": "true"}
        )

        assert response2.status_code == 400
        data = response2.json()

        # Verify ErrorResponse structure
        assert "error" in data
        error = data["error"]
        assert "message" in error
        assert "code" in error
        assert "Nonce already used" in error["message"]
        assert error["code"] == "nonce_reuse"
        assert error["field"] == "nonce"


@pytest.mark.django_db(transaction=False)
def test_declaration_validation_error(live_server):
    """Test validation error returns 422."""
    # Send IsccNote with missing required field
    invalid_note = {
        "iscc_code": "ISCC:KACWN77F73NA44D6EUG3S3QNJIL2BPPQFMW6ZX6CZNOKPAK23S2IJ2I",
        "datahash": "1e205ca7815adcb484e9a136c11efe69c1d530176d549b5d18d038eb5280b4b3470c",
        # Missing nonce, timestamp, signature
    }

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=invalid_note)

        assert response.status_code == 422
        data = response.json()

        # Verify ErrorResponse structure
        assert "error" in data
        error = data["error"]
        assert "message" in error
        assert "code" in error
        assert "field" in error


@pytest.mark.django_db(transaction=False)
def test_declaration_signature_error(live_server, current_timestamp, example_nonce, example_iscc_data):
    """Test invalid signature returns 401."""
    # Create an IsccNote with an invalid signature
    invalid_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,  # Hub ID 1
        "timestamp": current_timestamp,
        "signature": {
            "version": "ISCC-SIG v1.0",
            "pubkey": "z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
            "proof": "zInvalidSignature",
        },
    }

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=invalid_note)

        assert response.status_code == 401
        data = response.json()

        # Verify ErrorResponse structure
        assert "error" in data
        error = data["error"]
        assert "message" in error
        assert "code" in error
        assert error["message"] == "Invalid signature"
        assert error["code"] == "invalid_signature"


@pytest.mark.django_db(transaction=False)
def test_health_endpoint(live_server):
    """Test health endpoint returns correct status."""
    with httpx.Client() as client:
        # Use Accept header for JSON API
        response = client.get(
            f"{live_server.url}/health",
            headers={"Accept": "application/json"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify health response structure
        assert "status" in data
        assert "version" in data
        assert "description" in data
        assert data["status"] == "pass"
        assert data["description"] == "ISCC-HUB service is healthy"


@pytest.mark.django_db(transaction=False)
def test_did_document_endpoint(live_server):
    """Test DID document endpoint returns correct document."""
    with httpx.Client() as client:
        # Use Accept header for JSON API
        response = client.get(
            f"{live_server.url}/.well-known/did.json",
            headers={"Accept": "application/json"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.headers["access-control-allow-origin"] == "*"

        data = response.json()

        # Verify DID document structure
        assert "id" in data
        assert "verificationMethod" in data
        assert "authentication" in data
        assert "assertionMethod" in data
        assert data["id"] == "did:web:testserver"


@pytest.mark.django_db(transaction=True)
def test_issued_iscc_id_passes_iscc_core_validation(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    # type: (object, str, str, object, dict) -> None
    """End-to-end test: ISCC-ID issued by hub passes iscc_core.iscc_validate.

    This test verifies that ISCC-IDs actually issued by the hub through the
    API are valid according to the iscc_core library's strict validation.
    """
    import iscc_crypto as icr

    # Create a minimal note with current timestamp
    minimal_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    with httpx.Client() as client:
        # Submit declaration to hub API
        response = client.post(
            f"{live_server.url}/declaration",
            json=signed_note,
            headers={"Accept": "application/json"},
        )

        # Verify successful response
        assert response.status_code == 201
        data = response.json()

        # Extract ISCC-ID from receipt (it's in credentialSubject.declaration)
        assert "credentialSubject" in data
        assert "declaration" in data["credentialSubject"]
        assert "iscc_id" in data["credentialSubject"]["declaration"]

        iscc_id = data["credentialSubject"]["declaration"]["iscc_id"]

        # Validate format
        assert isinstance(iscc_id, str)
        assert iscc_id.startswith("ISCC:")

        # Validate with iscc_core library (strict mode)
        assert ic.iscc_validate(iscc_id, strict=True) is True

        # Also verify it decodes correctly
        mt, st, vs, ln, body = ic.iscc_decode(iscc_id)
        assert mt == 6  # MAINTYPE = ISCC-ID
        assert vs == 1  # VERSION = 1
        assert ln == 0  # LENGTH = 0 (64-bit, no counter)
        assert len(body) == 8  # Body is 8 bytes


@pytest.mark.django_db(transaction=True)
def test_declaration_without_timestamp_succeeds(live_server, example_nonce, example_keypair, example_iscc_data):
    # type: (object, str, object, dict) -> None
    """A declaration without a timestamp is accepted under the default policy."""
    import iscc_crypto as icr

    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
    }
    signed_note = icr.sign_json(note, example_keypair)

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_declaration_require_client_timestamp(live_server, example_nonce, example_keypair, example_iscc_data):
    # type: (object, str, object, dict) -> None
    """A declaration without a timestamp is rejected when REQUIRE_CLIENT_TIMESTAMP is enabled."""
    import iscc_crypto as icr

    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
    }
    signed_note = icr.sign_json(note, example_keypair)

    with override_config(REQUIRE_CLIENT_TIMESTAMP=True), httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "timestamp"


@pytest.mark.django_db(transaction=True)
def test_declaration_timestamp_out_of_tolerance(live_server, example_nonce, example_keypair, example_iscc_data):
    # type: (object, str, object, dict) -> None
    """A declaration with a provided timestamp outside the default tolerance is rejected."""
    import iscc_crypto as icr

    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": "2020-01-01T00:00:00.000Z",
    }
    signed_note = icr.sign_json(note, example_keypair)

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "timestamp_out_of_range"


@pytest.mark.django_db(transaction=True)
def test_declaration_timestamp_tolerance_disabled(live_server, example_nonce, example_keypair, example_iscc_data):
    # type: (object, str, object, dict) -> None
    """A provided out-of-range timestamp is accepted when TIMESTAMP_TOLERANCE_SECONDS is 0."""
    import iscc_crypto as icr

    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": "2020-01-01T00:00:00.000Z",
    }
    signed_note = icr.sign_json(note, example_keypair)

    with override_config(TIMESTAMP_TOLERANCE_SECONDS=0), httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_declaration_gateway_internal_whitespace_rejected(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    # type: (object, str, str, object, dict) -> None
    """A declaration whose gateway contains internal whitespace is rejected."""
    import iscc_crypto as icr

    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
        "gateway": "https://example.com/a b",
    }
    signed_note = icr.sign_json(note, example_keypair)

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "gateway"


@pytest.mark.django_db(transaction=True)
def test_declaration_missing_schema(live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data):
    # type: (object, str, str, object, dict) -> None
    """A declaration without $schema is rejected with 422."""
    import iscc_crypto as icr

    note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_note = icr.sign_json(note, example_keypair)

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "$schema"


@pytest.mark.django_db(transaction=True)
def test_declaration_unsupported_schema(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    # type: (object, str, str, object, dict) -> None
    """A declaration with an unsupported $schema URI is rejected with 422."""
    import iscc_crypto as icr

    note = {
        "$schema": "http://purl.org/iscc/schema/iscc-note-9.9.9.json",
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_note = icr.sign_json(note, example_keypair)

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "$schema"


@pytest.mark.django_db(transaction=True)
def test_declaration_rejects_context(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    # type: (object, str, str, object, dict) -> None
    """A declaration carrying @context (JSON-LD framing) is rejected as an unknown field."""
    import iscc_crypto as icr

    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "@context": "https://schema.iscc.codes/context.jsonld",
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_note = icr.sign_json(note, example_keypair)

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 422
    assert "Unknown fields not allowed" in response.json()["error"]["message"]


@pytest.mark.django_db(transaction=True)
def test_declaration_schema_signature_scope(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    # type: (object, str, str, object, dict) -> None
    """Injecting $schema after signing fails signature verification (401) — proves $schema is signed."""
    import iscc_crypto as icr

    note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_note = icr.sign_json(note, example_keypair)  # signed WITHOUT $schema
    tampered = {"$schema": ISCC_NOTE_SCHEMA, **signed_note}  # injected AFTER signing

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=tampered)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_signature"


@pytest.mark.django_db(transaction=True)
def test_declaration_proof_only_rejected(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    # type: (object, str, str, object, dict) -> None
    """A PROOF_ONLY signature (no embedded pubkey) is rejected (401)."""
    import iscc_crypto as icr

    note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_note = icr.sign_json(note, example_keypair, sigtype=icr.SigType.PROOF_ONLY)

    with httpx.Client() as client:
        response = client.post(f"{live_server.url}/declaration", json=signed_note)

    assert response.status_code == 401
    assert "pubkey" in response.json()["error"]["message"]
