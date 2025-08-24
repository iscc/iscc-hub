"""
Business logic for building ISCC receipts (W3C Verifiable Credentials).
"""

import iscc_crypto as icr
from django.conf import settings


def build_iscc_receipt(declaration_data, hub_keypair=None):
    # type: (dict, icr.KeyPair|None) -> dict
    """
    Build a signed IsccReceipt (W3C Verifiable Credential) from declaration data.

    Creates a W3C Verifiable Credential containing the declaration details
    and signs it with the HUB's keypair using the eddsa-jcs-2022 cryptosuite.
    Both the issuer DID and keypair controller use did:web format based on the
    hub domain.

    :param declaration_data: Dict containing iscc_note, seq, and iscc_id_str
    :param hub_keypair: Optional HUB's KeyPair for signing (defaults to configured key)
    :return: Signed W3C Verifiable Credential as a dict
    """
    # Use provided or default HUB keypair
    if hub_keypair is None:
        # Create keypair with did:web controller
        controller = f"did:web:{settings.ISCC_HUB_DOMAIN}"
        hub_keypair = icr.key_from_secret(settings.ISCC_HUB_SECKEY, controller=controller)

    # Hub DID is always derived from domain for issuer identity
    hub_did = f"did:web:{settings.ISCC_HUB_DOMAIN}"

    # Extract data from declaration_data dict
    iscc_note = declaration_data["iscc_note"]
    seq = declaration_data["seq"]
    iscc_id_str = declaration_data["iscc_id_str"]

    # Derive subject DID from signature
    subject_did = derive_subject_did(iscc_note["signature"])

    # Create W3C Verifiable Credential structure
    vc = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "type": ["VerifiableCredential", "IsccReceipt"],
        "issuer": hub_did,
        "credentialSubject": {
            "id": subject_did,
            "declaration": {
                "seq": seq,
                "iscc_id": iscc_id_str,
                "iscc_note": iscc_note,
            },
        },
    }

    # Sign the VC using iscc-crypto
    signed_vc = icr.sign_vc(vc, hub_keypair)

    return signed_vc


def derive_subject_did(signature):
    # type: (dict) -> str
    """
    Derive the subject's DID from IsccNote signature data.

    Uses signature.controller if present, otherwise derives did:key from pubkey.

    :param signature: Dict with controller and/or pubkey
    :return: DID string for the subject
    """
    # Use controller if specified
    if signature.get("controller"):
        return signature["controller"]

    # Otherwise derive did:key from pubkey
    pubkey = signature.get("pubkey")
    if not pubkey:
        raise ValueError("Signature missing both controller and pubkey")

    # Construct did:key from the public key
    return f"did:key:{pubkey}"
