"""
Test DELETE /declaration/<iscc_id> endpoint.
"""

import json

import iscc_crypto as icr
import pytest


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_delete_declaration_success(api_client, example_keypair, example_iscc_data, current_timestamp):
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
    response = await api_client.post(
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
    response = await api_client.delete(
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
    response = await api_client.delete(
        f"/declaration/{iscc_id}",
        data=json.dumps(signed_deletion2).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 404
    error_response = response.json()
    # Check for error message in either 'detail' or 'error.message'
    error_message = error_response.get("detail") or error_response.get("error", {}).get("message", "")
    assert "already deleted" in error_message.lower()
