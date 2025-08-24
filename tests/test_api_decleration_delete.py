"""
Test DELETE /declaration/<iscc_id> endpoint.
"""

import json

import iscc_crypto as icr
import pytest


@pytest.mark.django_db(transaction=True)
def test_delete_declaration_success(api_client, example_keypair, example_iscc_data, current_timestamp):
    # type: (object, icr.KeyPair, dict, str) -> None
    """
    Test successful deletion of a declaration.

    Creates a declaration first, then deletes it with proper authorization.
    """
    # Create a declaration using fresh nonce
    declaration_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    # Sign the declaration
    signed_declaration = icr.sign_json(declaration_note, example_keypair)

    # POST the declaration (API expects bytes)
    response = api_client.post(
        "/declaration",
        data=json.dumps(signed_declaration).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201, f"POST failed: {response.json()}"
    receipt = response.json()
    # The ISCC-ID is in credentialSubject.declaration.iscc_id
    iscc_id = receipt["credentialSubject"]["declaration"]["iscc_id"]

    # Now prepare the deletion request with a new unique nonce
    deletion_note = {
        "iscc_id": iscc_id,
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    # Sign the deletion request with the same keypair (same actor)
    signed_deletion = icr.sign_json(deletion_note, example_keypair)

    # DELETE the declaration (API expects bytes)
    response = api_client.delete(
        f"/declaration/{iscc_id}",
        data=json.dumps(signed_deletion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    # Should return 204 No Content with empty body
    assert response.status_code == 204
    assert response.content == b""

    # Verify the declaration is actually deleted by trying to delete it again
    deletion_note2 = {
        "iscc_id": iscc_id,
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    signed_deletion2 = icr.sign_json(deletion_note2, example_keypair)

    # Second deletion should fail with 404 (already deleted)
    response = api_client.delete(
        f"/declaration/{iscc_id}",
        data=json.dumps(signed_deletion2).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 404
    error_response = response.json()
    # Check for error message in either 'detail' or 'error.message'
    error_message = error_response.get("detail") or error_response.get("error", {}).get("message", "")
    assert "already deleted" in error_message.lower()


@pytest.mark.django_db(transaction=True)
def test_delete_declaration_iscc_id_mismatch(api_client, example_keypair, example_iscc_data, current_timestamp):
    # type: (object, icr.KeyPair, dict, str) -> None
    """
    Test deletion with ISCC-ID mismatch between URL and body.

    This test creates two different declarations to get two valid ISCC-IDs,
    then attempts to delete one using the other's ISCC-ID in the body.
    """
    # Create first declaration
    declaration_note1 = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    signed_declaration1 = icr.sign_json(declaration_note1, example_keypair)

    response = api_client.post(
        "/declaration",
        data=json.dumps(signed_declaration1).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201
    receipt1 = response.json()
    iscc_id1 = receipt1["credentialSubject"]["declaration"]["iscc_id"]

    # Create second declaration with different content
    import tests.conftest as conftest

    different_iscc_data = conftest.create_iscc_from_text("Different content for test!")
    declaration_note2 = {
        "iscc_code": different_iscc_data["iscc"],
        "datahash": different_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    signed_declaration2 = icr.sign_json(declaration_note2, example_keypair)

    response = api_client.post(
        "/declaration",
        data=json.dumps(signed_declaration2).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201
    receipt2 = response.json()
    iscc_id2 = receipt2["credentialSubject"]["declaration"]["iscc_id"]

    # Ensure we have two different ISCC-IDs
    assert iscc_id1 != iscc_id2

    # Now try to delete iscc_id1 but put iscc_id2 in the body (mismatch)
    deletion_note = {
        "iscc_id": iscc_id2,  # Body has different ISCC-ID
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    signed_deletion = icr.sign_json(deletion_note, example_keypair)

    # URL has iscc_id1 but body has iscc_id2
    response = api_client.delete(
        f"/declaration/{iscc_id1}",
        data=json.dumps(signed_deletion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 404
    error_response = response.json()
    error_message = error_response.get("detail") or error_response.get("error", {}).get("message", "")
    assert "mismatch" in error_message.lower()


@pytest.mark.django_db(transaction=True)
def test_delete_declaration_not_found(api_client, example_keypair, current_timestamp):
    # type: (object, icr.KeyPair, str) -> None
    """
    Test deletion of non-existent declaration.
    """
    # Use a valid ISCC-ID format that doesn't exist in the database
    # Generate an ISCC-ID with hub_id=1 and a high sequence number that won't exist
    import tests.conftest as conftest

    fake_iscc_id = conftest.generate_test_iscc_id(hub_id=1, seq=999999)

    deletion_note = {
        "iscc_id": fake_iscc_id,
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    signed_deletion = icr.sign_json(deletion_note, example_keypair)

    response = api_client.delete(
        f"/declaration/{fake_iscc_id}",
        data=json.dumps(signed_deletion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 404
    error_response = response.json()
    error_message = error_response.get("detail") or error_response.get("error", {}).get("message", "")
    assert "not found" in error_message.lower()


@pytest.mark.django_db(transaction=True)
def test_delete_declaration_unauthorized(api_client, example_keypair, example_iscc_data, current_timestamp):
    # type: (object, icr.KeyPair, dict, str) -> None
    """
    Test deletion by different controller (unauthorized).
    """
    # Create a declaration with first keypair
    declaration_note = {
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    signed_declaration = icr.sign_json(declaration_note, example_keypair)

    response = api_client.post(
        "/declaration",
        data=json.dumps(signed_declaration).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201
    receipt = response.json()
    iscc_id = receipt["credentialSubject"]["declaration"]["iscc_id"]

    # Try to delete with different keypair
    different_keypair = icr.key_generate(controller="did:web:different.com")

    deletion_note = {
        "iscc_id": iscc_id,
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }

    signed_deletion = icr.sign_json(deletion_note, different_keypair)

    response = api_client.delete(
        f"/declaration/{iscc_id}",
        data=json.dumps(signed_deletion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401
    error_response = response.json()
    error_message = error_response.get("detail") or error_response.get("error", {}).get("message", "")
    assert "not authorized" in error_message.lower()
