"""Tests that malformed input never reaches the permanent log."""

import json
import time
from io import BytesIO

import iscc_core as ic
import iscc_crypto as icr
import jcs
import pytest
from django.conf import settings

from iscc_hub import validators
from iscc_hub.exceptions import FieldValidationError, IsccIdError, SignatureError, TimestampError
from iscc_hub.iscc_id import IsccID
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


def raw_unit(unit):
    # type: (str) -> bytearray
    """Decode a canonical ISCC-UNIT to its header and body bytes."""
    return bytearray(ic.decode_base32(unit.removeprefix("ISCC:")))


def encode_unit(raw):
    # type: (bytes) -> str
    """Encode header and body bytes in canonical form, whether or not they are valid."""
    return "ISCC:" + ic.encode_base32(bytes(raw))


def with_version_1(unit):
    # type: (str) -> str
    """Change a V0 unit to the unsupported V1 and keep its length code and body."""
    raw = raw_unit(unit)
    raw[1] |= 0x10
    return encode_unit(raw)


def with_length_code(unit, length):
    # type: (str, int) -> str
    """Replace the length code of a unit and keep its body."""
    raw = raw_unit(unit)
    raw[1] = (raw[1] & 0xF0) | length
    return encode_unit(raw)


MALFORMED_UNITS = {
    "version 1": with_version_1,
    "no prefix": lambda unit: unit.removeprefix("ISCC:"),
    "lowercase body": lambda unit: "ISCC:" + unit[5:].lower(),
    "lowercase scheme": lambda unit: "iscc:" + unit[5:],
    "dashes": lambda unit: unit[:12] + "-" + unit[12:],
    "trailing newline": lambda unit: unit + "\n",
    "surrounding spaces": lambda unit: f" {unit} ",
    "length code 0": lambda unit: with_length_code(unit, 0),
    "length code 3": lambda unit: with_length_code(unit, 3),
    "truncated body": lambda unit: encode_unit(raw_unit(unit)[:-4]),
    "extra body bytes": lambda unit: encode_unit(raw_unit(unit) + b"\x00" * 4),
}


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


@pytest.mark.parametrize("index", [0, 1, 2], ids=["meta", "content", "data"])
@pytest.mark.parametrize("kind", list(MALFORMED_UNITS))
def test_validate_units_rejects_malformed_unit(kind, index):
    """Every unit must be strictly well-formed, even when the units still reconstruct the ISCC-CODE."""
    data = create_iscc_from_text("malformed unit")
    units = list(data["units"])
    units[index] = MALFORMED_UNITS[kind](units[index])
    with pytest.raises(FieldValidationError, match="Invalid ISCC unit") as error:
        validators.validate_units_reconstruction(units, data["datahash"], data["iscc"])
    assert error.value.field == "units"
    assert error.value.code == "invalid_iscc"


def test_validate_units_accepts_valid_units():
    """Units generated by iscc-core pass the strict check and reconstruct the ISCC-CODE."""
    data = create_iscc_from_text("valid units")
    validators.validate_units_reconstruction(data["units"], data["datahash"], data["iscc"])


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", ["version 1", "no prefix", "lowercase body", "length code 0", "extra body bytes"])
def test_malformed_unit_writes_nothing(api_client, example_keypair, did_resolved, kind):
    """A correctly signed note with a malformed unit gets a field error under the default policies, never a 500."""
    note = build_note(f"malformed {kind}")
    note["units"][0] = MALFORMED_UNITS[kind](note["units"][0])
    response = post_note(api_client, icr.sign_json(note, example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "units"
    assert response.json()["error"]["code"] == "invalid_iscc"
    assert not LogRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", ["version 1", "truncated body", "length code 3"])
def test_malformed_unit_rejected_without_units_policy(api_client, example_keypair, did_resolved, settings, kind):
    """The strict unit check holds when the units-required policy is off."""
    settings.ISCC_HUB_REQUIRE_FULL_UNITS = False
    note = build_note(f"malformed {kind} policy off")
    note["units"][0] = MALFORMED_UNITS[kind](note["units"][0])
    response = post_note(api_client, icr.sign_json(note, example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "units"
    assert not LogRecord.objects.exists()


def build_short_unit_note(bits):
    # type: (int) -> dict
    """Build an unsigned note whose valid units carry bodies of the given length."""
    content = f"short units {bits}".encode()
    units = [
        ic.gen_meta_code(content.decode(), bits=bits)["iscc"],
        ic.gen_data_code(BytesIO(content), bits=bits)["iscc"],
    ]
    instance = ic.gen_instance_code(BytesIO(content), bits=256)
    note = build_note(content.decode())
    note["units"] = units
    note["iscc_code"] = ic.gen_iscc_code(units + [instance["iscc"]])["iscc"]
    note["datahash"] = instance["datahash"]
    return note


@pytest.mark.parametrize("bits", [64, 128, 192])
def test_validate_units_rejects_short_units(bits):
    """Units shorter than 256 bits are rejected even though they reconstruct the ISCC-CODE."""
    note = build_short_unit_note(bits)
    with pytest.raises(FieldValidationError, match=f"META unit must be 256-bit, got {bits}-bit") as error:
        validators.validate_units_reconstruction(note["units"], note["datahash"], note["iscc_code"])
    assert error.value.code == "invalid_length"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("bits", [64, 128, 192])
def test_short_units_rejected_without_units_policy(api_client, example_keypair, did_resolved, settings, bits):
    """Units shorter than 256 bits are rejected when the units-required policy is off."""
    settings.ISCC_HUB_REQUIRE_FULL_UNITS = False
    response = post_note(api_client, icr.sign_json(build_short_unit_note(bits), example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "units"
    assert response.json()["error"]["code"] == "invalid_length"
    assert not LogRecord.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_units_optional_without_units_policy(api_client, example_keypair, did_resolved, settings):
    """A note without units is accepted when the units-required policy is off."""
    settings.ISCC_HUB_REQUIRE_FULL_UNITS = False
    note = build_note("no units")
    del note["units"]
    response = post_note(api_client, icr.sign_json(note, example_keypair))
    assert response.status_code == 201, response.content
    entry = json.loads(bytes(LogRecord.objects.get().record))
    assert "units" not in entry["note"]


def respell_iscc_id(iscc_id, header):
    # type: (str, bytes) -> str
    """Encode the body of an ISCC-ID under a different 2-byte header."""
    return "ISCC:" + ic.encode_base32(header + bytes(IsccID(iscc_id)))


ISCC_ID_SPELLINGS = {
    "other realm": lambda i: respell_iscc_id(i, bytes([IsccID.HEADER[0] ^ 0x01, IsccID.HEADER[1]])),
    "undefined subtype": lambda i: respell_iscc_id(i, bytes([(IsccID.HEADER[0] & 0xF0) | 0x02, IsccID.HEADER[1]])),
    "length code 1": lambda i: respell_iscc_id(i, bytes([IsccID.HEADER[0], IsccID.HEADER[1] | 0x01])),
    "no prefix": lambda i: i.removeprefix("ISCC:"),
    "lowercase body": lambda i: "ISCC:" + i[5:].lower(),
    "lowercase scheme": lambda i: "iscc:" + i[5:],
    "dashes": lambda i: i[:9] + "-" + i[9:],
}


@pytest.mark.parametrize("kind", list(ISCC_ID_SPELLINGS))
def test_validate_iscc_id_rejects_other_spellings(kind):
    """Only the canonical string for this Hub's realm is valid, and the error names it."""
    iscc_id = str(IsccID.from_timestamp(1746171541264773, 1))
    spelled = ISCC_ID_SPELLINGS[kind](iscc_id)
    assert bytes(IsccID(spelled)) == bytes(IsccID(iscc_id))
    with pytest.raises(IsccIdError, match=f"not in canonical form for this Hub's realm; expected {iscc_id}"):
        validators.validate_iscc_id(spelled, hub_id=1)


def test_validate_iscc_id_accepts_canonical_form():
    """The ISCC-ID as the Hub issues it is valid."""
    validators.validate_iscc_id(str(IsccID.from_timestamp(1746171541264773, 1)), hub_id=1)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", list(ISCC_ID_SPELLINGS))
def test_deletion_with_other_spelling_writes_nothing(api_client, example_keypair, did_resolved, kind):
    """A signed deletion that spells the ISCC-ID differently is rejected, and the declaration stays."""
    iscc_id = declare(api_client, example_keypair, f"spelling {kind}")
    spelled = ISCC_ID_SPELLINGS[kind](iscc_id)
    response = delete_note(api_client, spelled, icr.sign_json(build_deletion(spelled), example_keypair))
    assert response.status_code == 422
    assert field_of(response) == "iscc_id"
    assert response.json()["error"]["code"] == "invalid_iscc"
    assert not LogRecord.objects.filter(type="deletion").exists()
    assert api_client.get(f"/{iscc_id}").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_deletion_with_issued_iscc_id_succeeds(api_client, example_keypair, did_resolved):
    """A deletion that names the ISCC-ID exactly as issued is accepted, and both log IDs agree."""
    iscc_id = declare(api_client, example_keypair, "issued spelling")
    response = delete_note(api_client, iscc_id, icr.sign_json(build_deletion(iscc_id), example_keypair))
    assert response.status_code == 204
    entry = json.loads(bytes(LogRecord.objects.get(type="deletion").record))
    assert entry["iscc_id"] == entry["note"]["iscc_id"] == iscc_id
