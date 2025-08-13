"""
Unit tests for the receipt module.
"""

import iscc_crypto as icr
import pytest
from django.conf import settings

from iscc_hub.iscc_id import IsccID
from iscc_hub.models import Event
from iscc_hub.receipt import abuild_iscc_receipt, build_iscc_receipt, derive_subject_did


@pytest.mark.django_db
def test_build_iscc_receipt_with_minimal_note(minimal_iscc_note):
    # type: (dict) -> None
    """Test building an IsccReceipt from a minimal IsccNote."""
    # Create an Event with the minimal note
    iscc_id_bytes = IsccID.from_timestamp(1700000000000000, 1).bytes_body
    event = Event(
        seq=42,
        event_type=Event.EventType.CREATED,
        iscc_id=iscc_id_bytes,
        iscc_note=minimal_iscc_note,
    )
    event.save()

    # Build the receipt
    receipt = build_iscc_receipt(event)

    # Verify structure
    assert "@context" in receipt
    assert receipt["@context"] == ["https://www.w3.org/ns/credentials/v2"]
    assert receipt["type"] == ["VerifiableCredential", "IsccReceipt"]
    assert receipt["issuer"] == f"did:web:{settings.ISCC_HUB_DOMAIN}"

    # Verify credentialSubject
    assert "credentialSubject" in receipt
    subject = receipt["credentialSubject"]
    assert "id" in subject
    assert subject["id"].startswith("did:")

    # Verify declaration
    assert "declaration" in subject
    declaration = subject["declaration"]
    assert declaration["seq"] == 42
    assert declaration["iscc_id"] == str(IsccID(iscc_id_bytes))
    assert declaration["iscc_note"] == minimal_iscc_note

    # Verify proof exists
    assert "proof" in receipt
    proof = receipt["proof"]
    assert proof["type"] == "DataIntegrityProof"
    assert proof["cryptosuite"] == "eddsa-jcs-2022"
    assert proof["proofPurpose"] == "assertionMethod"
    assert "proofValue" in proof
    assert proof["proofValue"].startswith("z")  # Multibase-encoded


@pytest.mark.django_db
def test_build_iscc_receipt_with_full_note(full_iscc_note):
    # type: (dict) -> None
    """Test building an IsccReceipt from a full IsccNote with all optional fields."""
    # Create an Event with the full note
    iscc_id_bytes = IsccID.from_timestamp(1700000000000000, 1).bytes_body
    event = Event(
        seq=100,
        event_type=Event.EventType.CREATED,
        iscc_id=iscc_id_bytes,
        iscc_note=full_iscc_note,
    )
    event.save()

    # Build the receipt
    receipt = build_iscc_receipt(event)

    # Verify the note contains all optional fields
    declaration_note = receipt["credentialSubject"]["declaration"]["iscc_note"]
    assert "gateway" in declaration_note
    assert "units" in declaration_note
    assert "metahash" in declaration_note
    assert declaration_note == full_iscc_note


@pytest.mark.django_db
def test_build_iscc_receipt_with_custom_keypair(minimal_iscc_note, example_keypair):
    # type: (dict, icr.KeyPair) -> None
    """Test building an IsccReceipt with custom HUB keypair."""
    # Create an Event
    iscc_id_bytes = IsccID.from_timestamp(1700000000000000, 1).bytes_body
    event = Event(
        seq=1,
        event_type=Event.EventType.CREATED,
        iscc_id=iscc_id_bytes,
        iscc_note=minimal_iscc_note,
    )
    event.save()

    # Build the receipt with custom keypair
    receipt = build_iscc_receipt(event, hub_keypair=example_keypair)

    # Verify issuer is derived from domain (not keypair)
    assert receipt["issuer"] == "did:web:testserver"

    # Verify proof uses the custom keypair's verification method
    assert "proof" in receipt
    assert receipt["proof"]["verificationMethod"].startswith(example_keypair.controller)
    # The proof should be valid with the custom keypair


def test_derive_subject_did_with_controller():
    # type: () -> None
    """Test deriving subject DID when controller is specified."""
    signature = {
        "controller": "did:web:publisher.example.com",
        "pubkey": "z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
    }

    did = derive_subject_did(signature)
    assert did == "did:web:publisher.example.com"


def test_derive_subject_did_without_controller():
    # type: () -> None
    """Test deriving subject DID from pubkey when controller is not specified."""
    signature = {
        "pubkey": "z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
    }

    did = derive_subject_did(signature)
    assert did == "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"


def test_derive_subject_did_missing_both():
    # type: () -> None
    """Test error when signature has neither controller nor pubkey."""
    signature = {}

    with pytest.raises(ValueError) as exc_info:
        derive_subject_did(signature)

    assert "Signature missing both controller and pubkey" in str(exc_info.value)


def test_derive_subject_did_with_empty_controller():
    # type: () -> None
    """Test that empty controller is ignored and pubkey is used."""
    signature = {
        "controller": "",  # Empty string should be ignored
        "pubkey": "z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
    }

    did = derive_subject_did(signature)
    assert did == "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"


@pytest.mark.django_db
def test_build_iscc_receipt_with_updated_event(minimal_iscc_note):
    # type: (dict) -> None
    """Test building an IsccReceipt from an UPDATE event."""
    # Create an UPDATE event
    iscc_id_bytes = IsccID.from_timestamp(1700000000000000, 1).bytes_body
    event = Event(
        seq=200,
        event_type=Event.EventType.UPDATED,
        iscc_id=iscc_id_bytes,
        iscc_note=minimal_iscc_note,
    )
    event.save()

    # Build the receipt - should work the same way
    receipt = build_iscc_receipt(event)

    # Verify it's still a valid receipt
    assert receipt["type"] == ["VerifiableCredential", "IsccReceipt"]
    assert receipt["credentialSubject"]["declaration"]["seq"] == 200


@pytest.mark.django_db
def test_build_iscc_receipt_structure(minimal_iscc_note):
    # type: (dict) -> None
    """Test that the built IsccReceipt has correct structure and proof."""
    # Create an Event
    iscc_id_bytes = IsccID.from_timestamp(1700000000000000, 1).bytes_body
    event = Event(
        seq=1,
        event_type=Event.EventType.CREATED,
        iscc_id=iscc_id_bytes,
        iscc_note=minimal_iscc_note,
    )
    event.save()

    # Build the receipt
    receipt = build_iscc_receipt(event)

    # Check that the receipt is properly signed with did:web
    assert receipt["issuer"] == "did:web:testserver"
    assert "proof" in receipt
    assert receipt["proof"]["type"] == "DataIntegrityProof"
    assert receipt["proof"]["cryptosuite"] == "eddsa-jcs-2022"
    assert receipt["proof"]["verificationMethod"].startswith("did:web:testserver#")
    assert "proofValue" in receipt["proof"]


@pytest.mark.django_db
def test_build_iscc_receipt_iscc_id_formatting(minimal_iscc_note):
    # type: (dict) -> None
    """Test that ISCC-ID is properly formatted in the receipt."""
    # Create an Event with a specific ISCC-ID
    iscc_id = IsccID.from_timestamp(1736942400000000, 42)  # Specific timestamp and hub_id
    event = Event(
        seq=1,
        event_type=Event.EventType.CREATED,
        iscc_id=iscc_id.bytes_body,
        iscc_note=minimal_iscc_note,
    )
    event.save()

    # Build the receipt
    receipt = build_iscc_receipt(event)

    # Verify ISCC-ID format
    declaration = receipt["credentialSubject"]["declaration"]
    assert declaration["iscc_id"].startswith("ISCC:")
    assert len(declaration["iscc_id"]) == 21  # ISCC: + 16 characters
    assert declaration["iscc_id"] == str(iscc_id)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_abuild_iscc_receipt(minimal_iscc_note):
    # type: (dict) -> None
    """Test async wrapper for building an IsccReceipt."""
    from asgiref.sync import sync_to_async

    # Create an Event synchronously
    iscc_id_bytes = IsccID.from_timestamp(1700000000000000, 1).bytes_body
    event = Event(
        seq=42,
        event_type=Event.EventType.CREATED,
        iscc_id=iscc_id_bytes,
        iscc_note=minimal_iscc_note,
    )

    # Save the event using sync_to_async
    await sync_to_async(event.save)()

    # Build the receipt using async wrapper
    receipt = await abuild_iscc_receipt(event)

    # Build sync version for comparison
    sync_receipt = await sync_to_async(build_iscc_receipt)(event)

    # Verify it's the same as the sync version
    assert receipt == sync_receipt

    # Verify basic structure
    assert receipt["type"] == ["VerifiableCredential", "IsccReceipt"]
    assert receipt["issuer"] == f"did:web:{settings.ISCC_HUB_DOMAIN}"
    assert receipt["credentialSubject"]["declaration"]["seq"] == 42
