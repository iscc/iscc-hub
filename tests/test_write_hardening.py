"""Tests that malformed input never reaches the permanent log."""

import json
import time

import iscc_crypto as icr
import pytest
from django.conf import settings

from iscc_hub import validators
from iscc_hub.exceptions import TimestampError
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
    note = {
        "$schema": ISCC_NOTE_DELETE_SCHEMA,
        "iscc_id": iscc_id,
        "nonce": icr.create_nonce(settings.ISCC_HUB_ID),
        "timestamp": iso_week_now(),
    }
    body = json.dumps(icr.sign_json(note, example_keypair)).encode()
    response = api_client.delete(f"/declaration/{iscc_id}", data=body, headers=HEADERS)
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
