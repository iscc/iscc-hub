"""Tests that malformed input never reaches the permanent log."""

import json
import time

import iscc_crypto as icr
import jcs
import pytest
from django.conf import settings

from iscc_hub import validators
from iscc_hub.exceptions import FieldValidationError, SignatureError, TimestampError
from iscc_hub.models import LogRecord
from tests.conftest import ISCC_NOTE_DELETE_SCHEMA, ISCC_NOTE_SCHEMA, create_iscc_from_text

HEADERS = {"Content-Type": "application/json"}


def iso_week_now():
    # type: () -> str
    """Return the current time as an ISO week date, which passes the tolerance check."""
    return time.strftime("%G-W%V-%uT%H:%M:%S.000Z", time.gmtime())


def build_note(text):
    # type: (str) -> dict
    """Build an unsigned note with real, full-length ISCC units."""
    data = create_iscc_from_text(text)
    return {
        "$schema": ISCC_NOTE_SCHEMA,
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": icr.create_nonce(settings.ISCC_HUB_ID),
        "units": data["units"],
    }


def post_note(client, note):
    # type: (object, dict) -> object
    """Send a note exactly as given."""
    return client.post("/declaration", data=json.dumps(note).encode(), headers=HEADERS)


def declare(client, keypair, text):
    # type: (object, object, str) -> str
    """Declare valid content and return its ISCC-ID."""
    response = post_note(client, icr.sign_json(build_note(text), keypair))
    assert response.status_code == 201, response.content
    return response.json()["iscc_id"]


def build_deletion(iscc_id):
    # type: (str) -> dict
    """Build an unsigned deletion note."""
    return {
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
        "iscc_id": iscc_id,
        "nonce": icr.create_nonce(settings.ISCC_HUB_ID),
    }


def delete_note(client, iscc_id, note):
    # type: (object, str, dict) -> object
    """Send a deletion note exactly as given."""
    return client.delete(f"/declaration/{iscc_id}", data=json.dumps(note).encode(), headers=HEADERS)


def resign(note, keypair):
    # type: (dict, object) -> dict
    """Sign the supplied fields again without changing their types or spellings."""
    del note["signature"]["proof"]
    note["signature"]["proof"] = icr.sign_raw(jcs.canonicalize(note), keypair)
    assert icr.verify_json(note).signature_valid
    return note


def field_of(response):
    # type: (object) -> str
    """Return the field named by an error response."""
    return response.json()["error"]["field"]


@pytest.mark.parametrize(
    "value",
    [
        "2026-W36-6T13:41:51.000Z",
        "2026-249T13:41:51.000Z",
        "20260906T134151.000Z",
        "2026-09-06T24:00:00.000Z",
        "2026-09-06T13:41:51.000Z\n",
        "٢٠٢٦-09-06T13:41:51.000Z",
    ],
)
def test_validate_timestamp_rejects_other_iso_forms(value):
    """Only the exact calendar date and time syntax is valid."""
    with pytest.raises(TimestampError):
        validators.validate_timestamp(value)


def test_validate_timestamp_accepts_required_form():
    """The documented form stays valid."""
    validators.validate_timestamp("2026-09-06T13:41:51.000Z")


@pytest.mark.django_db(transaction=True)
def test_iso_week_timestamp_writes_nothing(api_client, example_keypair, did_resolved):
    """A current ISO week date is rejected on a declaration."""
    note = build_note("iso week")
    note["timestamp"] = iso_week_now()
    response = post_note(api_client, icr.sign_json(note, example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "timestamp"
    assert not LogRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_iso_week_timestamp_rejected_on_deletion(api_client, example_keypair, did_resolved):
    """A current ISO week date is rejected on a deletion, and the declaration stays."""
    iscc_id = declare(api_client, example_keypair, "iso week deletion")
    note = build_deletion(iscc_id)
    note["timestamp"] = iso_week_now()
    response = delete_note(api_client, iscc_id, icr.sign_json(note, example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "timestamp"
    assert not LogRecord.objects.filter(type="deletion").exists()


@pytest.mark.django_db(transaction=True)
def test_required_timestamp_form_still_accepted(api_client, example_keypair, did_resolved):
    """A declaration with a current timestamp in the required form is accepted."""
    note = build_note("valid timestamp")
    note["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    response = post_note(api_client, icr.sign_json(note, example_keypair))
    assert response.status_code == 201
    entry = json.loads(bytes(LogRecord.objects.get().record))
    assert entry["note"]["timestamp"] == note["timestamp"]


@pytest.mark.parametrize("field", ["proof", "pubkey"])
@pytest.mark.parametrize("value", [0, None, "", "z", "6MkNoMultibasePrefix", "z0OIl", "zAbc ", "zAbc\n", "zAbc\t"])
def test_signature_structure_rejects_invalid_encoding(field, value):
    """The proof and public key must match the schema pattern exactly."""
    signature = {"version": validators.SIGNATURE_VERSION, "proof": "zProof", "pubkey": "zKey"}
    signature[field] = value
    with pytest.raises(SignatureError, match=f"Invalid {field} in signature"):
        validators.validate_signature_structure(signature)


@pytest.mark.parametrize("field", ["controller", "keyid"])
@pytest.mark.parametrize("value", [False, True, 0, 1, 1.5, {}, {"a": 1}, ["a"]])
def test_signature_structure_rejects_non_string_optional_field(field, value):
    """Optional signature fields must be strings, whether or not the value is truthy."""
    signature = {"version": validators.SIGNATURE_VERSION, "proof": "zProof", "pubkey": "zKey", field: value}
    with pytest.raises(FieldValidationError, match="must be a string") as error:
        validators.validate_signature_structure(signature)
    assert error.value.field == field


def test_signature_structure_accepts_all_valid_fields():
    """A signature with every field in its documented form is valid."""
    validators.validate_signature_structure(
        {
            "version": validators.SIGNATURE_VERSION,
            "controller": "did:web:example.com",
            "keyid": "iscc",
            "proof": "zProof",
            "pubkey": "zKey",
        }
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("keyid", [False, 0, {}])
def test_falsy_keyid_writes_nothing(api_client, example_keypair, did_resolved, keyid):
    """A correctly signed non-string key ID is rejected under the default policies."""
    note = icr.sign_json(build_note("falsy keyid"), example_keypair)
    note["signature"]["keyid"] = keyid
    response = post_note(api_client, resign(note, example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "keyid"
    assert not LogRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_truthy_keyid_writes_nothing_without_did_verification(api_client, example_keypair, settings):
    """DID verification does not catch a truthy non-string key ID when it is off, so the structure check must."""
    settings.ISCC_HUB_VERIFY_DID = False
    note = icr.sign_json(build_note("truthy keyid"), example_keypair)
    note["signature"]["keyid"] = 1
    response = post_note(api_client, resign(note, example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "keyid"
    assert not LogRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_non_string_controller_writes_nothing_without_did_policies(api_client, example_keypair, settings):
    """The string rule for the controller holds when both DID policies are off."""
    settings.ISCC_HUB_VERIFY_DID = False
    settings.ISCC_HUB_REQUIRE_DID = False
    note = icr.sign_json(build_note("controller"), example_keypair)
    note["signature"]["controller"] = 1
    response = post_note(api_client, resign(note, example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "controller"
    assert not LogRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("padding", [" ", "\n", "\t"])
def test_proof_with_whitespace_writes_nothing(api_client, example_keypair, did_resolved, padding):
    """Whitespace after a valid proof is rejected, although the Base58 decoder would strip it."""
    note = icr.sign_json(build_note("proof"), example_keypair)
    note["signature"]["proof"] += padding
    assert icr.verify_json(note).signature_valid
    response = post_note(api_client, note)
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "invalid_signature"
    assert error["message"] == "Invalid proof in signature: must be multibase base58-btc"
    assert not LogRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_pubkey_with_whitespace_writes_nothing_without_did_verification(api_client, example_keypair, settings):
    """A signed public key with trailing whitespace is rejected when DID verification is off."""
    settings.ISCC_HUB_VERIFY_DID = False
    note = icr.sign_json(build_note("pubkey"), example_keypair)
    note["signature"]["pubkey"] += " "
    response = post_note(api_client, resign(note, example_keypair))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_signature"
    assert not LogRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_malformed_signature_fields_rejected_on_deletion(api_client, example_keypair, did_resolved):
    """Deletions follow the same signature rules, and the declaration stays."""
    iscc_id = declare(api_client, example_keypair, "signature deletion")
    padded = icr.sign_json(build_deletion(iscc_id), example_keypair)
    padded["signature"]["proof"] += " "
    assert delete_note(api_client, iscc_id, padded).status_code == 401
    falsy = icr.sign_json(build_deletion(iscc_id), example_keypair)
    falsy["signature"]["keyid"] = False
    response = delete_note(api_client, iscc_id, resign(falsy, example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "keyid"
    assert not LogRecord.objects.filter(type="deletion").exists()
    assert api_client.get(f"/{iscc_id}").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_string_keyid_of_authorized_key_still_accepted(api_client, example_keypair, did_resolved):
    """A key ID that names a key in the DID document is accepted and stored unchanged."""
    method_id = example_keypair.controller_document["verificationMethod"][0]["id"]
    keyid = method_id.split("#")[-1]
    note = icr.sign_json(build_note("string keyid"), example_keypair)
    note["signature"]["keyid"] = keyid
    assert post_note(api_client, resign(note, example_keypair)).status_code == 201
    entry = json.loads(bytes(LogRecord.objects.get().record))
    assert entry["note"]["signature"]["keyid"] == keyid
