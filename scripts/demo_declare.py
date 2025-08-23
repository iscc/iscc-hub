"""
Demo script to create and declare a random ISCC note on the sandbox node.
"""

import json
import random
import string
from datetime import UTC, datetime
from io import BytesIO

import iscc_core as ic
import iscc_crypto as icr
import requests


def generate_random_iscc_note():
    # type: () -> dict
    """Generate a random but valid ISCC note with signature."""
    # Generate random content
    random_text = "".join(random.choices(string.ascii_letters + string.digits + " ", k=random.randint(50, 200)))
    random_title = "".join(random.choices(string.ascii_letters + " ", k=random.randint(10, 30)))
    random_description = "".join(random.choices(string.ascii_letters + " ", k=random.randint(20, 50)))

    # Generate ISCC components
    text_bytes = random_text.encode("utf-8")
    mcode = ic.gen_meta_code(random_title, random_description, bits=256)
    ccode = ic.gen_text_code(random_text, bits=256)
    dcode = ic.gen_data_code(BytesIO(text_bytes), bits=256)
    icode = ic.gen_instance_code(BytesIO(text_bytes), bits=256)

    # Generate composite ISCC code from all units including instance
    iscc_code = ic.gen_iscc_code([mcode["iscc"], ccode["iscc"], dcode["iscc"], icode["iscc"]])["iscc"]

    # Create nonce with hub_id 0
    nonce = icr.create_nonce(0)

    # Create timestamp
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # Create the IsccNote
    note = {
        "iscc_code": iscc_code,
        "datahash": icode["datahash"],
        "nonce": nonce,
        "timestamp": timestamp,
        "gateway": f"https://example.com/demo/{nonce[:8]}",
        "metahash": mcode["metahash"],
        "units": [mcode["iscc"], ccode["iscc"], dcode["iscc"]],  # META, CONTENT, DATA units (NOT instance)
    }

    # Generate keypair and sign the note
    controller = f"did:web:demo-{random.randint(1000, 9999)}.example.com"
    keypair = icr.key_generate(controller=controller)
    signed_note = icr.sign_json(note, keypair)

    return signed_note


def declare_on_sandbox(iscc_note):
    # type: (dict) -> dict | None
    """Declare an ISCC note on the sandbox node."""
    url = "https://sb0.iscc.id/declaration"

    try:
        response = requests.post(
            url, json=iscc_note, headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=10
        )

        if response.status_code == 201:
            return response.json()
        else:
            print(f"Declaration failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error declaring on sandbox: {e}")
        return None


def main():
    # type: () -> None
    """Main function to create and declare a random ISCC note."""
    print("Generating random ISCC note...")
    note = generate_random_iscc_note()

    print("\nGenerated ISCC Note:")
    print(json.dumps(note, indent=2))

    print("\nDeclaring on sandbox node (https://sb0.iscc.id)...")
    receipt = declare_on_sandbox(note)

    if receipt:
        print("\n✅ Declaration successful!")
        print("\nReceipt:")
        print(json.dumps(receipt, indent=2))

        # Extract ISCC-ID from the receipt structure
        if "credentialSubject" in receipt and "declaration" in receipt["credentialSubject"]:
            iscc_id = receipt["credentialSubject"]["declaration"].get("iscc_id")
            if iscc_id:
                print(f"\n🔗 View declaration: https://sb0.iscc.id/declaration/{iscc_id}")
    else:
        print("\n❌ Declaration failed")


if __name__ == "__main__":
    main()
