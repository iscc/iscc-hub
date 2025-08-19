"""Minimal tests for POST /declaration endpoint to achieve 100% coverage."""

import json

import httpx
import pytest
from django.db import connection


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


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_declaration_success_minimal(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test successful declaration with minimal IsccNote returns IsccReceipt."""
    import iscc_crypto as icr

    # Create a minimal note with current timestamp
    minimal_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    # Use httpx async client with live server
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{live_server.url}/declaration", json=signed_note)

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


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_declaration_invalid_json(live_server):
    """Test invalid JSON returns 400 error."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{live_server.url}/declaration",
            content=b"invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = response.json()

        # Verify ErrorResponse structure
        assert "error" in data
        error = data["error"]
        assert "message" in error
        assert "code" in error
        assert error["message"] == "Invalid JSON in request body"
        assert error["code"] == "error"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_declaration_duplicate_rejected(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test duplicate declaration is rejected with 409 Conflict."""
    import iscc_crypto as icr

    # Create and sign first declaration
    first_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_first = icr.sign_json(first_note, example_keypair)

    async with httpx.AsyncClient() as client:
        # First declaration should succeed
        response = await client.post(f"{live_server.url}/declaration", json=signed_first)
        assert response.status_code == 201

        # Create second declaration with same datahash but different nonce
        second_nonce = "001abcd1234567890abcdef123456700"  # Different nonce, same hub_id prefix
        second_note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],  # Same datahash
            "nonce": second_nonce,
            "timestamp": current_timestamp,
        }
        signed_second = icr.sign_json(second_note, example_keypair)

        # Second declaration should be rejected with 409
        response = await client.post(f"{live_server.url}/declaration", json=signed_second)
        assert response.status_code == 409

        data = response.json()
        assert "error" in data
        error = data["error"]
        assert error["code"] == "duplicate_declaration"
        assert error["field"] == "datahash"
        assert "existing_iscc_id" in error
        assert "existing_actor" in error
        assert example_iscc_data["datahash"] in error["message"]


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_declaration_duplicate_forced(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test duplicate declaration succeeds with force header."""
    import iscc_crypto as icr

    # Create and sign first declaration
    first_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_first = icr.sign_json(first_note, example_keypair)

    async with httpx.AsyncClient() as client:
        # First declaration should succeed
        response = await client.post(f"{live_server.url}/declaration", json=signed_first)
        assert response.status_code == 201

        # Create second declaration with same datahash but different nonce
        second_nonce = "001abcd1234567890abcdef123456700"  # Different nonce, same hub_id prefix
        second_note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],  # Same datahash
            "nonce": second_nonce,
            "timestamp": current_timestamp,
        }
        signed_second = icr.sign_json(second_note, example_keypair)

        # Second declaration should succeed with force header
        headers = {"X-Force-Declaration": "true"}
        response = await client.post(f"{live_server.url}/declaration", json=signed_second, headers=headers)
        assert response.status_code == 201

        # Should return valid receipt
        data = response.json()
        assert "credentialSubject" in data
        assert "declaration" in data["credentialSubject"]


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_declaration_duplicate_force_variations(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test various force header values work correctly."""
    import iscc_crypto as icr

    # Create and sign first declaration
    first_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }
    signed_first = icr.sign_json(first_note, example_keypair)

    async with httpx.AsyncClient() as client:
        # First declaration
        response = await client.post(f"{live_server.url}/declaration", json=signed_first)
        assert response.status_code == 201

        # Test force="1" works
        second_nonce = "001abcd1234567890abcdef123456700"
        second_note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": second_nonce,
            "timestamp": current_timestamp,
        }
        signed_second = icr.sign_json(second_note, example_keypair)

        headers = {"X-Force-Declaration": "1"}
        response = await client.post(f"{live_server.url}/declaration", json=signed_second, headers=headers)
        assert response.status_code == 201

        # Test force="TRUE" (case insensitive) works
        third_nonce = "001abcd1234567890abcdef123456701"
        third_note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": third_nonce,
            "timestamp": current_timestamp,
        }
        signed_third = icr.sign_json(third_note, example_keypair)

        headers = {"X-Force-Declaration": "TRUE"}
        response = await client.post(f"{live_server.url}/declaration", json=signed_third, headers=headers)
        assert response.status_code == 201

        # Test force="false" is rejected
        fourth_nonce = "001abcd1234567890abcdef123456702"
        fourth_note = {
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": fourth_nonce,
            "timestamp": current_timestamp,
        }
        signed_fourth = icr.sign_json(fourth_note, example_keypair)

        headers = {"X-Force-Declaration": "false"}
        response = await client.post(f"{live_server.url}/declaration", json=signed_fourth, headers=headers)
        assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_declaration_nonce_reuse_error(
    live_server, current_timestamp, example_nonce, example_keypair, example_iscc_data
):
    """Test nonce reuse returns 400 error."""
    import iscc_crypto as icr

    # Create a minimal note with current timestamp
    minimal_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": example_nonce,
        "timestamp": current_timestamp,
    }

    # Sign the note
    signed_note = icr.sign_json(minimal_note, example_keypair)

    async with httpx.AsyncClient() as client:
        # First declaration should succeed
        response1 = await client.post(f"{live_server.url}/declaration", json=signed_note)
        assert response1.status_code == 201

        # Second declaration with same nonce should fail (use force header to bypass duplicate check)
        response2 = await client.post(
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


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_declaration_validation_error(live_server):
    """Test validation error returns 422."""
    # Send IsccNote with missing required field
    invalid_note = {
        "iscc_code": "ISCC:KACWN77F73NA44D6EUG3S3QNJIL2BPPQFMW6ZX6CZNOKPAK23S2IJ2I",
        "datahash": "1e205ca7815adcb484e9a136c11efe69c1d530176d549b5d18d038eb5280b4b3470c",
        # Missing nonce, timestamp, signature
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{live_server.url}/declaration", json=invalid_note)

        assert response.status_code == 422
        data = response.json()

        # Verify ErrorResponse structure
        assert "error" in data
        error = data["error"]
        assert "message" in error
        assert "code" in error
        assert "field" in error


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_declaration_signature_error(live_server, current_timestamp, example_nonce, example_iscc_data):
    """Test invalid signature returns 401."""
    # Create an IsccNote with an invalid signature
    invalid_note = {
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

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{live_server.url}/declaration", json=invalid_note)

        assert response.status_code == 401
        data = response.json()

        # Verify ErrorResponse structure
        assert "error" in data
        error = data["error"]
        assert "message" in error
        assert "code" in error
        assert error["message"] == "Invalid signature"
        assert error["code"] == "invalid_signature"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_health_endpoint(live_server):
    """Test health endpoint returns correct status."""
    async with httpx.AsyncClient() as client:
        # Use Accept header for JSON API
        response = await client.get(
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


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=False)
async def test_did_document_endpoint(live_server):
    """Test DID document endpoint returns correct document."""
    async with httpx.AsyncClient() as client:
        # Use Accept header for JSON API
        response = await client.get(
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
