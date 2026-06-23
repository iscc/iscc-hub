"""
Test DELETE /declaration/<iscc_id> endpoint.
"""

import json

import iscc_crypto as icr
import pytest

# Published schema URIs carried in the `$schema` wire field (required on every message)
ISCC_NOTE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-0.8.0.json"
ISCC_NOTE_DELETE_SCHEMA = "http://purl.org/iscc/schema/iscc-note-delete-0.8.0.json"


@pytest.fixture(autouse=True)
def _default_on_did(did_resolved):
    """
    Run this module under the default-ON identity policy with a resolvable controller.

    Declarations and deletions here are signed by the did:web example keypair (Policy A passes);
    ``did_resolved`` injects a local DID server so Policy B resolves offline. POSTed declarations
    carry 256-bit ``units`` for Policy C. Deletions that fail before the ownership check
    (not-found, mismatch, missing schema, proof-only) never trigger DID resolution.
    """
    yield did_resolved


@pytest.mark.django_db(transaction=True)
def test_delete_declaration_success(api_client, example_keypair, example_iscc_data, current_timestamp):
    # type: (object, icr.KeyPair, dict, str) -> None
    """
    Test successful deletion of a declaration.

    Creates a declaration first, then deletes it with proper authorization.
    """
    # Create a declaration using fresh nonce
    declaration_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
        "units": example_iscc_data["units"],
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
    # POST returns the minimal ack containing the assigned ISCC-ID.
    iscc_id = response.json()["iscc_id"]

    # Now prepare the deletion request with a new unique nonce
    deletion_note = {
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
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
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
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
def test_redeclaration_after_deletion_is_blocked(api_client, example_keypair, example_iscc_data, current_timestamp):
    # type: (object, icr.KeyPair, dict, str) -> None
    """Dedup reads append-only history: a declared-then-deleted datahash stays blocked.

    The declaration leaf remains in the log after deletion (only a deletion leaf is appended),
    so re-declaring the same datahash returns 409 by default; X-Force-Declaration overrides it.
    This pins the load-bearing distinction between LogRecord (history) and IsccDeclaration
    (current state) — if dedup were repointed at the current-state view, this would regress to 201.
    """

    def _declare(headers=None):
        # type: (dict|None) -> object
        note = {
            "$schema": ISCC_NOTE_SCHEMA,
            "iscc_code": example_iscc_data["iscc"],
            "datahash": example_iscc_data["datahash"],
            "nonce": icr.create_nonce(1),
            "timestamp": current_timestamp,
            "units": example_iscc_data["units"],
        }
        signed = icr.sign_json(note, example_keypair)
        return api_client.post(
            "/declaration",
            data=json.dumps(signed).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
        )

    # Declare, then delete.
    response = _declare()
    assert response.status_code == 201, f"POST failed: {response.json()}"
    iscc_id = response.json()["iscc_id"]

    deletion = icr.sign_json(
        {
            "$schema": ISCC_NOTE_DELETE_SCHEMA,
            "iscc_id": iscc_id,
            "nonce": icr.create_nonce(1),
            "timestamp": current_timestamp,
        },
        example_keypair,
    )
    response = api_client.delete(
        f"/declaration/{iscc_id}",
        data=json.dumps(deletion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 204

    # Re-declaring the same datahash (fresh nonce, no force header) is blocked by the history dedup.
    response = _declare()
    assert response.status_code == 409, f"expected duplicate block, got {response.status_code}: {response.json()}"
    assert response.json()["error"]["code"] == "duplicate_declaration"

    # X-Force-Declaration overrides the block and mints a fresh ISCC-ID.
    response = _declare(headers={"X-Force-Declaration": "true"})
    assert response.status_code == 201, f"forced re-declaration failed: {response.json()}"
    assert response.json()["iscc_id"] != iscc_id


@pytest.mark.django_db(transaction=True)
def test_delete_declaration_without_timestamp(api_client, example_keypair, example_iscc_data, current_timestamp):
    # type: (object, icr.KeyPair, dict, str) -> None
    """
    A deletion that omits `timestamp` is accepted under the default policy.

    Under default policy (REQUIRE_CLIENT_TIMESTAMP disabled) the Hub assigns its own
    authoritative timestamp, so a declarer-supplied deletion timestamp is optional.
    """
    # Create a declaration to delete
    declaration_note = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
        "units": example_iscc_data["units"],
    }
    signed_declaration = icr.sign_json(declaration_note, example_keypair)
    response = api_client.post(
        "/declaration",
        data=json.dumps(signed_declaration).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201, f"POST failed: {response.json()}"
    iscc_id = response.json()["iscc_id"]

    # Delete it with a signed request that carries no `timestamp` field
    deletion_note = {
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
        "iscc_id": iscc_id,
        "nonce": icr.create_nonce(1),
    }
    signed_deletion = icr.sign_json(deletion_note, example_keypair)
    response = api_client.delete(
        f"/declaration/{iscc_id}",
        data=json.dumps(signed_deletion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    # Should succeed with 204 No Content and an empty body
    assert response.status_code == 204, f"DELETE failed: {response.content!r}"
    assert response.content == b""


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
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
        "units": example_iscc_data["units"],
    }

    signed_declaration1 = icr.sign_json(declaration_note1, example_keypair)

    response = api_client.post(
        "/declaration",
        data=json.dumps(signed_declaration1).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201
    iscc_id1 = response.json()["iscc_id"]

    # Create second declaration with different content
    import tests.conftest as conftest

    different_iscc_data = conftest.create_iscc_from_text("Different content for test!")
    declaration_note2 = {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": different_iscc_data["iscc"],
        "datahash": different_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
        "units": different_iscc_data["units"],
    }

    signed_declaration2 = icr.sign_json(declaration_note2, example_keypair)

    response = api_client.post(
        "/declaration",
        data=json.dumps(signed_declaration2).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201
    iscc_id2 = response.json()["iscc_id"]

    # Ensure we have two different ISCC-IDs
    assert iscc_id1 != iscc_id2

    # Now try to delete iscc_id1 but put iscc_id2 in the body (mismatch)
    deletion_note = {
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
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
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
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
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": example_iscc_data["iscc"],
        "datahash": example_iscc_data["datahash"],
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
        "units": example_iscc_data["units"],
    }

    signed_declaration = icr.sign_json(declaration_note, example_keypair)

    response = api_client.post(
        "/declaration",
        data=json.dumps(signed_declaration).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 201
    iscc_id = response.json()["iscc_id"]

    # Try to delete with different keypair
    different_keypair = icr.key_generate(controller="did:web:different.com")

    deletion_note = {
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
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


@pytest.mark.django_db(transaction=True)
def test_delete_missing_schema(api_client, example_keypair, current_timestamp):
    # type: (object, icr.KeyPair, str) -> None
    """A deletion request without $schema is rejected with 422."""
    deletion_note = {
        "iscc_id": "ISCC:MAIGFKM3UDDAAEAB",
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }
    signed_deletion = icr.sign_json(deletion_note, example_keypair)

    response = api_client.delete(
        "/declaration/ISCC:MAIGFKM3UDDAAEAB",
        data=json.dumps(signed_deletion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "$schema"


@pytest.mark.django_db(transaction=True)
def test_delete_proof_only_rejected(api_client, example_keypair, current_timestamp):
    # type: (object, icr.KeyPair, str) -> None
    """A deletion whose signature omits pubkey (PROOF_ONLY) is rejected (401)."""
    deletion_note = {
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
        "iscc_id": "ISCC:MAIGFKM3UDDAAEAB",
        "nonce": icr.create_nonce(1),
        "timestamp": current_timestamp,
    }
    signed_deletion = icr.sign_json(deletion_note, example_keypair, sigtype=icr.SigType.PROOF_ONLY)

    response = api_client.delete(
        "/declaration/ISCC:MAIGFKM3UDDAAEAB",
        data=json.dumps(signed_deletion).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401
    assert "pubkey" in response.json()["error"]["message"]
