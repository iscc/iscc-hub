---
icon: lucide/code
description: Declare content, get receipts, resolve and delete ISCC-IDs with the HTTP API of a hub
---

# Use the API

Each hub has the same HTTP API. You declare content with a signed JSON message and get back an ISCC-ID.
{ .iscc-lead }

Each hub also shows its interactive API documentation at `/docs` and its OpenAPI file at `/static/openapi.yaml`.
[IEP-0013](https://ieps.iscc.codes/iep-0013/) defines the messages.

## Endpoints

| Method and path                      | Use                                                             |
| ------------------------------------ | --------------------------------------------------------------- |
| `POST /declaration`                  | Declare content with a signed `IsccNote`. Returns the ISCC-ID   |
| `GET /declaration/{iscc_id}/receipt` | Get the signed `IsccReceipt` of a declaration                   |
| `DELETE /declaration/{iscc_id}`      | Delete a declaration with a signed `IsccNoteDelete`             |
| `GET /{iscc_id}`                     | Resolve an ISCC-ID. Send `Accept: application/json` to get JSON |
| `GET /lookup?datahash=…`             | Find declarations by data hash                                  |
| `GET /lookup?iscc_code=…`            | Find declarations by ISCC-CODE                                  |
| `GET /search`, `POST /search`        | Similarity search. Returns 404 if the hub has no search server  |
| `GET /health`                        | Status and version of the hub                                   |
| `GET /.well-known/did.json`          | DID document with the public key of the hub                     |
| `GET /log/checkpoint`                | Signed checkpoint of the transparency log                       |
| `GET /log/tile/...`                  | Tiles of the transparency log, in the C2SP tlog-tiles format    |

## Before you declare

You need an Ed25519 key. With the default policies of a hub, your key must also be in a `did:web` DID document at your
domain:

```bash
uvx iscc-crypto keygen example.com
```

The command prints your secret key and a DID document. Publish the DID document at
`https://example.com/.well-known/did.json`. Keep the secret key private.

Select a hub and get its hub ID from the [hub list](join-the-network.md#the-hub-lists). Each message has a nonce. The
first 12 bits of the nonce must be the hub ID of the target hub. `iscc_crypto.create_nonce(hub_id)` makes such a nonce.
A hub rejects a message for a different hub, and it rejects a nonce that it saw before.

## Example

This script declares a text, gets the receipt, resolves the ISCC-ID and deletes the declaration. Run it with
`uv run declare.py`.

```python title="declare.py"
# /// script
# dependencies = ["iscc-core", "iscc-crypto", "httpx"]
# ///
import io
import os

import httpx
import iscc_core as ic
import iscc_crypto as icr

HUB = "https://staging.iscc.id"  # the target hub
HUB_ID = 1  # its hub ID, from the hub list
SECRET = os.environ["ISCC_SECRET_KEY"]  # your secret key from iscc-crypto keygen
KEY = icr.key_from_secret(SECRET, controller="did:web:example.com")

# 1. Generate the ISCC-CODE and the data hash of the content
text = "Hello World! This is my content."
data = text.encode()
meta = ic.gen_meta_code("Hello World", bits=256)["iscc"]
content = ic.gen_text_code(text, bits=256)["iscc"]
data_code = ic.gen_data_code(io.BytesIO(data), bits=256)["iscc"]
instance = ic.gen_instance_code(io.BytesIO(data), bits=256)
units = [meta, content, data_code]
iscc_code = ic.gen_iscc_code(units + [instance["iscc"]])["iscc"]

# 2. Make the note, sign it and send it
note = {
    "$schema": "http://purl.org/iscc/schema/iscc-note-0.8.0.json",
    "iscc_code": iscc_code,
    "datahash": instance["datahash"],
    "nonce": icr.create_nonce(HUB_ID),
    "units": units,
}
response = httpx.post(f"{HUB}/declaration", json=icr.sign_json(note, KEY))
print(response.status_code, response.json())  # 201 {'iscc_id': 'ISCC:MAIG...', 'seq': 0}
iscc_id = response.json()["iscc_id"]

# 3. Get the signed receipt
receipt = httpx.get(f"{HUB}/declaration/{iscc_id}/receipt").json()

# 4. Resolve the ISCC-ID
record = httpx.get(f"{HUB}/{iscc_id}", headers={"Accept": "application/json"}).json()

# 5. Delete the declaration
delete = {
    "$schema": "http://purl.org/iscc/schema/iscc-note-delete-0.8.0.json",
    "iscc_id": iscc_id,
    "nonce": icr.create_nonce(HUB_ID),
}
response = httpx.request("DELETE", f"{HUB}/declaration/{iscc_id}", json=icr.sign_json(delete, KEY))
print(response.status_code)  # 204
```

For real content, generate the codes from the file with [iscc-sdk](https://github.com/iscc/iscc-sdk) or
[iscc-web](https://web.iscc.codes/).

## Rules for declarations

| Field       | Rule                                                                                |
| ----------- | ----------------------------------------------------------------------------------- |
| `$schema`   | Required. `http://purl.org/iscc/schema/iscc-note-0.8.0.json`                        |
| `iscc_code` | Required. A valid ISCC-CODE                                                         |
| `datahash`  | Required. The BLAKE3 multihash of the content. It must match the Instance-Code      |
| `nonce`     | Required. 32 hex characters. The first 12 bits are the hub ID                       |
| `signature` | Required. Made by `iscc_crypto.sign_json`. Policy A requires a `did:web` controller |
| `units`     | Required by policy C. Each unit must be a valid 256-bit ISCC-UNIT                   |
| `timestamp` | Optional. Exactly `YYYY-MM-DDTHH:MM:SS.sssZ`, near the hub clock                    |
| `gateway`   | Optional. URL or URI template of your gateway for this ISCC-ID                      |
| `metahash`  | Optional. BLAKE3 multihash of your metadata                                         |

A request can have at most 8192 bytes. A hub rejects a second declaration of the same data hash. To declare the same
data again, send the header `X-Force-Declaration: true`.

## Errors

Errors return JSON with a message and a code:

```json
{
  "error": {
    "message": "Declaration already deleted: ISCC:MAIG...",
    "code": "not_found"
  }
}
```

| Status | Meaning                                                                                               |
| ------ | ----------------------------------------------------------------------------------------------------- |
| 400    | The hub saw this nonce before                                                                         |
| 401    | The signature is not valid, or the key is not allowed on this hub                                     |
| 404    | The ISCC-ID does not exist on this hub, or it was deleted                                             |
| 409    | The hub has a declaration of this data hash                                                           |
| 422    | The body is not valid JSON, is too large, or has a field that is not valid. The error names the field |
| 503    | The hub cannot check the DID document now, or no search server answers. Try again later               |
