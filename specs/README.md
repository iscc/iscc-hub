# IDP Specifications

This directory holds the implementation-agnostic specifications of the ISCC Discovery Protocol (IDP) and their companion
schemas.

## Documents

| Document             | Status      | Description                                                                                                                                                                |
| -------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `idp-declaration.md` | Draft v0.1  | Declaration Profile — IsccNote submission, signature rules, IsccReceipt, deletion, submission API.                                                                         |
| `iscc-log.md`        | Draft v0.1  | Transparency Log — tlog-tiles profile (SHA-256 RFC 6962 tree, hash/data tiles), C2SP signed-note checkpoint, 3 static HTTP endpoints. OTS + witnesses deferred post-pilot. |
| `idp-lookup.md`      | *(planned)* | Lookup & Resolution — ISCC-ID resolution, W3C CID document format, service descriptors, exact-match lookup (`/lookup`), optional proxied similarity search (`/search`).    |

The three specs are written to be read together. Cross-references are section-anchored where possible.

## Schemas

JSON Schemas for the data structures defined in the specs live in [`schemas/`](schemas/) as YAML source files. YAML is
used as the source of truth because it is more readable and editable than equivalent JSON; because YAML is a strict
superset of JSON, the same files are valid JSON Schema documents and most tooling reads them directly.

| Schema                  | Defined in | Description                                                 |
| ----------------------- | ---------- | ----------------------------------------------------------- |
| `common.yaml`           | §6.3       | Shared field encodings (multihash, nonce, multibase, etc.). |
| `iscc-signature.yaml`   | §5.2       | IsccSignature object.                                       |
| `iscc-note.yaml`        | §5.1       | IsccNote (the signed declaration).                          |
| `iscc-note-delete.yaml` | §5.5       | IsccNoteDelete (the signed deletion request).               |
| `iscc-receipt.yaml`     | §5.3       | IsccReceipt (W3C VC issued by the Hub).                     |
| `log-entry.yaml`        | §5.4       | Transparency-log entry envelope.                            |

The schemas reference each other with relative `$ref` paths and resolve correctly with standard JSON Schema tooling that
supports `draft/2020-12`.

## Relationship to the implementation

The schemas in this directory document the **protocol-level** wire format described by the specs. The schemas under
[`iscc_hub/static/schemas/`](../iscc_hub/static/schemas/) are the **implementation contract** of the reference Hub —
they are the source from which `iscc_hub/schema.py` is generated and describe exactly what the current Hub code accepts
and emits.

These specs **document** the plan-driven implementation; they have **no authority of their own**. The flow is **plan →
implementation → `specs/`**: a decision is made in a plan, built into the code, and only then is the prose here updated
to describe what was built. Where this directory and the running implementation disagree, the implementation governs and
the spec is corrected to match — never the reverse.
