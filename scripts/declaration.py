#!/usr/bin/env python3
"""
Create and submit a valid ISCC declaration to the hub.

This script creates a valid IsccNote, signs it, and submits it to the local hub
via POST request to localhost:8000/declaration.
"""

import json
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import iscc_core as ic
import iscc_crypto as icr
import requests

# Add project root to Python path for imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def create_iscc_from_text(text="Hello World!"):
    # type: (str) -> dict
    """Create deterministic ISCC components from text."""
    mcode = ic.gen_meta_code(text, "Test Description", bits=256)
    ccode = ic.gen_text_code(text, bits=256)
    dcode = ic.gen_data_code(BytesIO(text.encode("utf-8")), bits=256)
    icode = ic.gen_instance_code(BytesIO(text.encode("utf-8")), bits=256)
    iscc_code = ic.gen_iscc_code([mcode["iscc"], ccode["iscc"], dcode["iscc"], icode["iscc"]])["iscc"]

    result = {}
    result.update(mcode)
    result.update(ccode)
    result.update(dcode)
    result.update(icode)
    result["iscc"] = iscc_code
    result["units"] = [mcode["iscc"], ccode["iscc"], dcode["iscc"]]
    return result


def generate_nonce(hub_id=0):
    # type: (int) -> str
    """Generate a nonce with hub_id prefix."""
    import secrets

    # First 12 bits = hub_id (0 = 0x000)
    hub_prefix = f"{hub_id:03x}"
    # Remaining 29 hex chars (116 bits) random
    random_suffix = secrets.token_hex(14) + secrets.token_hex(1)[:1]
    return hub_prefix + random_suffix


def create_timestamp():
    # type: () -> str
    """Create current timestamp in ISO format with millisecond precision."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def create_minimal_iscc_note(text="Hello from declaration script!"):
    # type: (str) -> dict
    """Create a minimal signed IsccNote."""
    # Generate ISCC data from text
    iscc_data = create_iscc_from_text(text)

    # Generate keypair
    controller = "did:web:example.com"
    keypair = icr.key_generate(controller=controller)

    # Create minimal note
    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": generate_nonce(),
        "timestamp": create_timestamp(),
    }

    # Sign the note
    signed_note = icr.sign_json(note, keypair)
    return signed_note


def create_full_iscc_note(text="Hello from declaration script!"):
    # type: (str) -> dict
    """Create a full signed IsccNote with all optional fields."""
    # Generate ISCC data from text
    iscc_data = create_iscc_from_text(text)

    # Generate keypair
    controller = "did:web:example.com"
    keypair = icr.key_generate(controller=controller)

    # Create full note with optional fields
    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": generate_nonce(),
        "timestamp": create_timestamp(),
        "gateway": "https://example.com/iscc_id/{iscc_id}/metadata",
        "units": iscc_data["units"],
        "metahash": iscc_data["metahash"],
    }

    # Sign the note
    signed_note = icr.sign_json(note, keypair)
    return signed_note


def submit_declaration(note, base_url="http://localhost:8000"):
    # type: (dict, str) -> dict
    """Submit ISCC declaration to the hub."""
    url = f"{base_url}/declaration"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        response = requests.post(url, json=note, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error submitting declaration: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response text: {e.response.text}")
        raise


def main():
    """Create and submit ISCC declaration."""
    print("Creating ISCC declaration...")

    # Create a full ISCC note
    note = create_full_iscc_note("Hello from ISCC Hub declaration script!")

    print("\nCreated ISCC Note:")
    print(json.dumps(note, indent=2))

    print("\nSubmitting to localhost:8000/declaration...")

    try:
        result = submit_declaration(note)

        print("\n" + "=" * 60)
        print("DECLARATION SUCCESSFUL!")
        print("=" * 60)
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"\nFailed to submit declaration: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
