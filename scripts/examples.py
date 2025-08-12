#!/usr/bin/env python
"""Generate valid example data for OpenAPI specification."""

import json
import os
import sys
from datetime import UTC, datetime, timezone
from io import BytesIO

import django
import iscc_core as ic
import iscc_crypto as icr

# Set up Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iscc_hub.settings")
django.setup()

EXAMPLE_PRIVATE_KEY = "z3u2RDonZ81AFKiw8QCPKcsyg8Yy2MmYQNxfBn51SS2QmMiw"


def create_iscc():
    """Create a valid ISCC-CODE and metadata for IsccNote creation"""
    text = "Hello World!"
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


def create_note_min(nonce=None, timestamp=None, keypair=None):
    """Create a minimal IsccNote"""
    nonce = nonce or icr.create_nonce(0)
    # Client-side timestamp with millisecond precision (3 decimal places) for cross-platform compatibility
    # The hub will generate its own microsecond-precision timestamp in the ISCC-ID
    timestamp = timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    keypair = keypair or icr.key_generate()
    data = create_iscc()
    minimal_iscc_note = {
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": nonce,
        "timestamp": timestamp,
    }

    signed_minimal_iscc_note = icr.sign_json(minimal_iscc_note, keypair)
    return signed_minimal_iscc_note


def create_note_full(nonce=None, timestamp=None, keypair=None, controller=None):
    """Create a full IsccNote"""
    nonce = nonce or icr.create_nonce(0)
    # Client-side timestamp with millisecond precision (3 decimal places) for cross-platform compatibility
    # The hub will generate its own microsecond-precision timestamp in the ISCC-ID
    timestamp = timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    controller = controller or "did:web:example.com"
    keypair = keypair or icr.key_generate(controller=controller)
    data = create_iscc()
    full_iscc_note = {
        "iscc_code": data["iscc"],
        "datahash": data["datahash"],
        "nonce": nonce,
        "timestamp": timestamp,
        "gateway": "https://example.com/iscc_id/{iscc_id}/metadata",
        "units": data["units"],
        "metahash": data["metahash"],
    }

    signed_full_iscc_note = icr.sign_json(full_iscc_note, keypair)
    return signed_full_iscc_note


if __name__ == "__main__":
    print(json.dumps(create_note_min(), indent=2))
    print(json.dumps(create_note_full(), indent=2))
