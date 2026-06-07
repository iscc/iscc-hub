# ISCC Discovery Protocol — Declaration Profile

**Version:** 0.1.0-draft **Status:** Working Draft **Latest editor's draft:** `specs/idp-declaration.md` **Editors:**
ISCC Foundation

## Abstract

This specification defines the **Declaration Profile** of the ISCC Discovery Protocol (IDP). It describes how a declarer
submits a cryptographically signed declaration of an ISCC-CODE to an ISCC-HUB, how the Hub assigns and returns a
globally unique ISCC-ID, and how the declaration is committed to a verifiable transparency log.

The Declaration Profile covers the following concerns:

- The structure and semantics of the **IsccNote**, the signed object produced by a declarer.
- The structure and semantics of the **IsccReceipt**, the signed object returned by a Hub as proof of declaration.
- The format of declaration and deletion entries written to the transparency log.
- The HTTP submission and deletion APIs.
- Signature, canonicalization, and replay-protection rules.

Companion specifications cover the transparency log byte format (*ISCC-Log*) and ISCC-ID resolution (*IDP Lookup &
Resolution*).

## Status of This Document

This is a working draft of the IDP Declaration Profile. It is published for review and is subject to change. It is
**not** a finalized specification.

Implementations conforming to this draft SHOULD label themselves as *IDP-Declaration v0.1-draft* and document
conformance exceptions explicitly.

## Table of Contents

1. [Introduction](#1-introduction)
2. [Conformance](#2-conformance)
3. [Terminology](#3-terminology)
4. [Architecture overview](#4-architecture-overview)
5. [Abstract data model](#5-abstract-data-model)
6. [JSON representation](#6-json-representation)
7. [ISCC-ID](#7-iscc-id)
8. [Signatures](#8-signatures)
9. [Declaration submission](#9-declaration-submission)
10. [Declaration deletion](#10-declaration-deletion)
11. [Nonce handling](#11-nonce-handling)
12. [Permission modes](#12-permission-modes)
13. [Metadata forwarding](#13-metadata-forwarding)
14. [Security considerations](#14-security-considerations)
15. [IANA considerations](#15-iana-considerations)
16. [References](#16-references)
17. [Appendix A: Examples](#appendix-a-examples)
18. [Appendix B: Schema reference](#appendix-b-schema-reference)

## 1. Introduction

The ISCC Discovery Protocol (IDP) enables registrants to associate descriptive metadata, rights signals, and service
endpoints with content identified by an **International Standard Content Code (ISCC)** defined in
[[ISO-24138]](#iso-24138). The Declaration Profile defines the first half of this association: how a registrant tells an
ISCC-HUB that a specific ISCC-CODE has been declared, by whom, and where to find related metadata.

### 1.1 Motivation

ISCC-CODEs are deterministic content fingerprints. Two parties that process the same content independently derive the
same ISCC-CODE. Identity, rights, and provenance information cannot be inferred from the code itself — they must be
**declared**. The Declaration Profile provides the protocol surface for that declaration to occur in a way that is:

- **Cryptographically attributable** to the declarer (Ed25519 signature).
- **Verifiable independent of the Hub** (signed receipt + transparency log inclusion proof).
- **Replay-protected** (per-Hub nonces, ISCC-ID timestamp commitment).
- **Privacy-preserving for the Hub** (declarative metadata never enters the Hub log; only a hash commitment).

### 1.2 Scope

This document specifies:

- The IsccNote object that a declarer signs and submits.
- The IsccReceipt object that a Hub signs and returns.
- The IsccSignature format used by both declarer and Hub.
- The transparency-log entry shape that a Hub appends.
- The submission and deletion HTTP endpoints exposed by a Hub.
- Validation rules, error model, and signature semantics.

### 1.3 Out of scope

The following are addressed by companion specifications and are intentionally out of scope for this document:

- The **Merkle tree, tile layout, and checkpoint** of the transparency log (a tlog-tiles profile) — see *ISCC-Log
    Specification*.
- **Lookup and resolution** of ISCC-IDs to W3C CID documents and service descriptors — see *IDP Lookup & Resolution*.
- **Metadata schemas** carried as forwarded attachments — managed by the ISCC Schema Registry.
- **Hub-List governance**: how Hub identity is established and revoked at the protocol layer.

### 1.4 Document conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**,
**RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [[RFC2119]](#rfc2119)
and [[RFC8174]](#rfc8174) when, and only when, they appear in all capitals, as shown here.

Examples are non-normative unless explicitly marked otherwise.

## 2. Conformance

This specification defines two conformance classes.

### 2.1 Declarer conformance

A **conforming declarer** is software that:

- Produces an IsccNote whose structure satisfies [§5.1](#51-isccnote).
- Computes an IsccSignature whose structure satisfies [§5.2](#52-iscc-signature) over the canonicalized IsccNote per
    [§8.2](#82-signing-scope).
- Submits the IsccNote to a Hub per [§9](#9-declaration-submission).
- Validates the IsccReceipt returned by the Hub per [§5.3](#53-isccreceipt).

### 2.2 Hub conformance

A **conforming Hub** is server software that:

- Accepts IsccNote submissions at the endpoint defined in [§9.1](#91-submission-endpoint).
- Validates incoming IsccNotes per the algorithm in [§9.3](#93-validation-procedure).
- Issues ISCC-IDs whose structure satisfies [§7](#7-iscc-id).
- Appends a log entry per [§5.4](#54-log-entry) for every accepted declaration.
- Returns an IsccReceipt per [§5.3](#53-isccreceipt) for every accepted declaration.
- Accepts deletion requests per [§10](#10-declaration-deletion) and appends the corresponding log entry.

A Hub MAY additionally implement metadata forwarding per [§13](#13-metadata-forwarding). A Hub that implements metadata
forwarding MUST follow the rules in that section.

## 3. Terminology

The following terms are used throughout this specification.

- **ISCC-CODE.** A composite identifier derived deterministically from a digital asset, as defined in
    [[ISO-24138]](#iso-24138).
- **ISCC-ID.** A 64-bit globally unique identifier issued by a Hub when a declaration is accepted (see
    [§7](#7-iscc-id)).
- **ISCC-HUB** (or **Hub**). A server that accepts signed declarations, issues ISCC-IDs, and maintains a verifiable
    transparency log.
- **Declarer.** The entity that creates and signs an IsccNote.
- **IsccNote.** A JSON object containing a declaration claim, signed by the declarer.
- **IsccReceipt.** A W3C Verifiable Credential issued by the Hub as proof that a declaration has been accepted and
    committed to the log.
- **IsccSignature.** The Ed25519 digital signature object used by both declarers and Hubs, as defined in
    [[ISCC-SIG]](#iscc-sig).
- **Hub-List.** The authoritative mapping of `hub_id` (12-bit integer) to Hub public key and base URL. For pilot
    deployments, the Hub-List is a static document.
- **Gateway.** An external service that resolves ISCC-IDs to metadata and service descriptors. Gateways are out of scope
    for this document, except as the destination of optional metadata forwarding (see [§13](#13-metadata-forwarding)).
- **Transparency log.** The append-only, cryptographically verifiable record of all declaration and deletion entries
    produced by a Hub. Byte format is defined by the *ISCC-Log Specification*.
- **JCS.** JSON Canonicalization Scheme as defined in [[RFC8785]](#rfc8785).
- **Multihash.** Self-describing hash format. In this specification, multihash always denotes BLAKE3 with prefix `1e20`
    followed by 32 bytes of digest in lowercase hexadecimal (68 characters total).
- **Multibase.** Self-describing base-encoding format. In this specification, multibase strings use the `z` prefix
    indicating base58-btc encoding.

## 4. Architecture overview

This section is **informative**.

The Declaration Profile sits at the **Hub layer** of the three-layer IDP architecture (Hub, Gateway, Registry). A
declarer interacts with a Hub by submitting an IsccNote and receiving an IsccReceipt. The Hub records the declaration in
its transparency log and assigns an ISCC-ID. Hubs do not store user-supplied descriptive metadata; that responsibility
belongs to the Gateway and Registry layers.

A typical declaration sequence proceeds as follows.

1. The declarer computes an ISCC-CODE and a BLAKE3 `datahash` for the asset.
2. The declarer selects a target Hub from the Hub-List and constructs an IsccNote, including a 128-bit nonce whose top
    12 bits equal the target Hub's `hub_id`.
3. The declarer canonicalizes the IsccNote per [§8.2](#82-signing-scope), signs it with their Ed25519 private key, and
    submits the result to the Hub.
4. The Hub validates the IsccNote, atomically assigns an ISCC-ID, appends a log entry, and returns an IsccReceipt.
5. The declarer stores the IsccReceipt as durable proof of the declaration.

## 5. Abstract data model

This section defines the data structures used by the Declaration Profile in terms of named fields with semantic types.
The normative JSON binding is specified in [§6](#6-json-representation).

A conforming declaration **MUST** validate against the published `iscc-note-0.8.0` schema. The Hub additionally enforces
a **stricter admission profile**: it forbids `@context`/`@type`, requires an embedded `pubkey` (PROOF_ONLY signatures
are rejected), and requires strict 3-digit-millisecond timestamps when a timestamp is present. Every Hub deviation only
narrows what the published schema permits, so any declaration the Hub accepts remains valid under `iscc-note-0.8.0`. The
wire `$schema` value references the published schema; the Hub publishes no separate schema, and its admission rules are
documented here as Hub policy.

### 5.1 IsccNote

An **IsccNote** is a structured claim by a declarer that a specified ISCC-CODE applies to content they wish to declare.

| Field       | Required | Type                | Description                                                                              |
| ----------- | -------- | ------------------- | ---------------------------------------------------------------------------------------- |
| `$schema`   | **MUST** | URI                 | Published schema URI; **MUST** equal `http://purl.org/iscc/schema/iscc-note-0.8.0.json`. |
| `iscc_code` | **MUST** | ISCC-CODE           | The composite ISCC-CODE being declared.                                                  |
| `datahash`  | **MUST** | BLAKE3 multihash    | Hash of the content bytes, prefixed `1e20`.                                              |
| `nonce`     | **MUST** | 128-bit hex         | Random value; first 12 bits equal target `hub_id`.                                       |
| `signature` | **MUST** | IsccSignature       | Declarer's Ed25519 signature over the canonical IsccNote.                                |
| `timestamp` | **MAY**  | RFC 3339 timestamp  | Declarer-supplied UTC timestamp with strict millisecond precision.                       |
| `gateway`   | **MAY**  | URI or URI template | Service endpoint for metadata or W3C CID document.                                       |
| `metahash`  | **MAY**  | BLAKE3 multihash    | Commitment to metadata bytes (see [§13](#13-metadata-forwarding)).                       |
| `units`     | **MAY**  | array of ISCC-UNIT  | Extended similarity-preserving ISCC-UNITs (excluding Instance-Code).                     |

Field semantics:

- `$schema` **MUST** be present and **MUST** equal `http://purl.org/iscc/schema/iscc-note-0.8.0.json` — the URI of the
    published IsccNote schema. It is part of the signature scope ([§8.2](#82-signing-scope)). Declarations carrying
    `@context` or `@type` are rejected by the Hub admission profile (see below); the wire value references the published
    schema, and the Hub publishes no separate schema.
- `iscc_code` **MUST** be a composite ISCC-CODE, not an individual ISCC-UNIT. Implementations SHOULD use 256-bit
    components for pilot-scale deployments to avoid birthday collisions.
- `datahash` **MUST** be a BLAKE3 multihash: literal `1e20` followed by 64 lowercase hexadecimal characters representing
    32 digest bytes.
- `nonce` **MUST** be a 128-bit value encoded as 32 lowercase hexadecimal characters. The 12 most-significant bits
    **MUST** equal the `hub_id` of the target Hub. See [§11](#11-nonce-handling).
- `signature` **MUST** be a valid IsccSignature ([§5.2](#52-iscc-signature)) whose `proof` is computed over the
    canonicalized IsccNote per [§8.2](#82-signing-scope).
- `timestamp` is governed by configurable Hub policy. Under default policy a Hub **MUST NOT** reject a declaration
    solely because `timestamp` is absent; a Hub **MAY** require a declarer timestamp (`REQUIRE_CLIENT_TIMESTAMP`). When
    `timestamp` is present it **MUST** be an RFC 3339 timestamp in UTC with a trailing `Z` and exactly 3-digit
    milliseconds (`YYYY-MM-DDTHH:MM:SS.sssZ`). A Hub **MAY** range-check a provided value against a configurable
    tolerance (`TIMESTAMP_TOLERANCE_SECONDS`, default ±600 s; `0` disables). The Hub always assigns its own
    authoritative microsecond timestamp at sequencing time regardless of any declarer value (see [§7](#7-iscc-id)).
- If `gateway` is present, it **MUST** be either an absolute HTTPS URL or an RFC 6570 URI template using only
    `{iscc_id}`, `{iscc_code}`, or `{datahash}` as variables. The URI **MUST NOT** contain userinfo, query, or fragment
    components. Allowed operators are level-1 (simple), `{/var}`, and `{.var}`; explode and prefix modifiers are not
    permitted.
- If `metahash` is present, it **MUST** be a BLAKE3 multihash with the same format as `datahash`. The `metahash` commits
    to metadata bytes that the declarer may attach at submission time (see [§13](#13-metadata-forwarding)).
- If `units` is present, it **MUST** contain between 1 and 4 ISCC-UNITs. The array **MUST NOT** include the
    Instance-Code, which is derivable from `datahash`.

### 5.2 IsccSignature

An **IsccSignature** is an Ed25519 digital signature object conforming to the ISCC Signature Specification
[[ISCC-SIG]](#iscc-sig).

| Field        | Required | Type             | Description                                                                       |
| ------------ | -------- | ---------------- | --------------------------------------------------------------------------------- |
| `version`    | **MUST** | constant string  | Exactly `"ISCC-SIG v1.0"`.                                                        |
| `pubkey`     | **MUST** | multibase string | Ed25519 public key (multibase `z` + base58-btc, with multicodec prefix `0xed01`). |
| `proof`      | **MUST** | multibase string | Ed25519 signature value over the canonical signed object.                         |
| `controller` | **MAY**  | URI              | DID or HTTPS URL identifying the key controller.                                  |
| `keyid`      | **MAY**  | string           | Key identifier within the controller document.                                    |

Field semantics:

- `pubkey` **MUST** decode to a 32-byte Ed25519 public key after multibase and multicodec prefix removal.
- `proof` **MUST** decode to a 64-byte Ed25519 signature value.
- `controller`, if present, **MUST** be a DID URI (e.g., `did:key:`, `did:web:`) or an absolute HTTPS URL that resolves
    to a W3C Controlled Identifier Document [[CID]](#cid).
- `keyid`, if present, identifies a specific verification method within the controller document.

### 5.3 IsccReceipt

An **IsccReceipt** is a W3C Verifiable Credential [[VC-DATA-MODEL]](#vc-data-model) issued by a Hub as proof that a
declaration has been accepted and committed to the transparency log.

The receipt is a self-contained credential: any verifier holding the receipt, the Hub's public key, and (for inclusion
verification) a log checkpoint can confirm the declaration's authenticity and the time at which it was logged, without
re-contacting the issuing Hub.

| Field               | Required | Type            | Description                                                                 |
| ------------------- | -------- | --------------- | --------------------------------------------------------------------------- |
| `@context`          | **MUST** | array of URI    | JSON-LD context. **MUST** include `"https://www.w3.org/ns/credentials/v2"`. |
| `type`              | **MUST** | array of string | **MUST** include `"VerifiableCredential"` and `"IsccReceipt"`.              |
| `issuer`            | **MUST** | URI             | DID of the issuing Hub.                                                     |
| `credentialSubject` | **MUST** | object          | Declaration claims (see below).                                             |
| `proof`             | **MUST** | object          | W3C Data Integrity proof (see below).                                       |

The `credentialSubject` object **MUST** contain:

| Field         | Required | Type   | Description                                                     |
| ------------- | -------- | ------ | --------------------------------------------------------------- |
| `id`          | **MUST** | URI    | DID or controller URI of the declarer (signer of the IsccNote). |
| `declaration` | **MUST** | object | Declaration record (see below).                                 |

The `declaration` object **MUST** contain:

| Field       | Required | Type        | Description                                                    |
| ----------- | -------- | ----------- | -------------------------------------------------------------- |
| `seq`       | **MUST** | integer ≥ 0 | Gapless sequence number of the log entry within the Hub's log. |
| `iscc_id`   | **MUST** | ISCC-ID     | The ISCC-ID assigned by the Hub.                               |
| `iscc_note` | **MUST** | IsccNote    | The original IsccNote, byte-for-byte canonical.                |

The `proof` object **MUST** contain:

| Field                | Required | Value                  | Description                                            |
| -------------------- | -------- | ---------------------- | ------------------------------------------------------ |
| `@context`           | **MUST** | array of URI           | Copy of the credential's `@context`.                   |
| `type`               | **MUST** | `"DataIntegrityProof"` | Per [[VC-DATA-INTEGRITY]](#vc-data-integrity).         |
| `cryptosuite`        | **MUST** | `"eddsa-jcs-2022"`     | Per [[VC-DI-EDDSA]](#vc-di-eddsa).                     |
| `verificationMethod` | **MUST** | URI                    | DID URL of the Hub's signing key.                      |
| `proofPurpose`       | **MUST** | `"assertionMethod"`    | Per [[VC-DATA-INTEGRITY]](#vc-data-integrity).         |
| `proofValue`         | **MUST** | multibase string       | Hub's Ed25519 signature over the canonical credential. |

The `proofValue` is computed using `eddsa-jcs-2022`: the credential (excluding `proof.proofValue` itself) is
canonicalized with JCS, SHA-256-hashed, and signed with the Hub's Ed25519 private key. The signature value is then
multibase-encoded with prefix `z` (base58-btc).

The receipt's timestamp is implicit: the 52 most-significant bits of the ISCC-ID encode the microsecond Unix timestamp
at which the Hub committed the declaration to the log (see [§7](#7-iscc-id)).

### 5.4 Log entry

A **log entry** is the canonical JSON object that a Hub appends to its transparency log for every accepted declaration
or deletion. Log entries are the unit over which the transparency log's Merkle tree is constructed.

| Field     | Required | Type                       | Description                               |
| --------- | -------- | -------------------------- | ----------------------------------------- |
| `v`       | **MUST** | integer                    | Entry-format version. **MUST** equal `1`. |
| `type`    | **MUST** | string                     | `"declaration"` or `"deletion"`.          |
| `iscc_id` | **MUST** | ISCC-ID                    | The ISCC-ID this entry refers to.         |
| `note`    | **MUST** | IsccNote or IsccNoteDelete | The verbatim signed object.               |

For `type` = `"declaration"`, the `note` field **MUST** contain the original IsccNote, byte-for-byte identical to the
bytes whose hash was signed by the declarer — including its `$schema` field. A verifier reading the log entry can
re-verify the declarer's signature without consulting the Hub.

For `type` = `"deletion"`, the `note` field **MUST** contain the IsccNoteDelete object signed by the declarer (see
[§5.5](#55-deletion-entry-isccnotedelete)).

Log entries are canonicalized with JCS prior to being appended to the log. The exact framing of entries within the log
byte stream is defined by the *ISCC-Log Specification* and is out of scope here.

### 5.5 Deletion entry (IsccNoteDelete)

An **IsccNoteDelete** is the object a declarer signs to request deletion of a previously committed declaration.

| Field       | Required | Type               | Description                                                                                     |
| ----------- | -------- | ------------------ | ----------------------------------------------------------------------------------------------- |
| `$schema`   | **MUST** | URI                | Published schema URI; **MUST** equal `http://purl.org/iscc/schema/iscc-note-delete-0.8.0.json`. |
| `iscc_id`   | **MUST** | ISCC-ID            | The ISCC-ID being deleted.                                                                      |
| `timestamp` | **MAY**  | RFC 3339 timestamp | Declarer-supplied UTC timestamp with strict millisecond precision.                              |
| `nonce`     | **MUST** | 128-bit hex        | Random value; first 12 bits equal target `hub_id`.                                              |
| `signature` | **MUST** | IsccSignature      | Declarer's signature over the canonical IsccNoteDelete.                                         |

The IsccNoteDelete object **MUST NOT** contain fields beyond those listed above. `$schema` is part of the signature
scope ([§8.2](#82-signing-scope)). As with IsccNote, `timestamp` is governed by configurable Hub policy: under default
policy a Hub **MUST NOT** reject a deletion solely because `timestamp` is absent; a Hub **MAY** require a declarer
timestamp (`REQUIRE_CLIENT_TIMESTAMP`). When `timestamp` is present it **MUST** use the strict RFC 3339 form and is
range-checked against the configurable tolerance (`TIMESTAMP_TOLERANCE_SECONDS`). The Hub assigns its own authoritative
microsecond timestamp to the deletion at sequencing time regardless of any declarer value.

Authorization rule: the `signature.pubkey` of an IsccNoteDelete **MUST** equal the `signature.pubkey` of the original
IsccNote that produced the `iscc_id` being deleted. A Hub **MUST** reject any deletion request whose signing key does
not match.

## 6. JSON representation

This section defines the **normative JSON binding** of the abstract data model. All Hubs and declarers **MUST** use this
binding for on-the-wire interchange. Alternative serializations are not defined by this specification; any such
alternative would require its own signature canonicalization rule and is out of scope.

### 6.1 General rules

- All JSON documents **MUST** be encoded in UTF-8 [[RFC3629]](#rfc3629).
- Field names **MUST** be lowercase ASCII as specified in [§5](#5-abstract-data-model).
- Object members **MAY** appear in any order on the wire; canonicalization (see [§6.2](#62-canonicalization-jcs))
    normalizes ordering for signature computation and log entry comparison.
- Unknown top-level fields encountered in an IsccNote, IsccNoteDelete, or IsccSignature **MUST** cause the Hub to reject
    the submission. This prevents downgrade attacks where an attacker adds fields that are ignored by some
    implementations but interpreted by others.

### 6.2 Canonicalization (JCS)

JSON Canonicalization Scheme [[RFC8785]](#rfc8785) is the canonicalization rule for this protocol. JCS specifies a
deterministic byte representation of any JSON document: object keys sorted lexicographically, numbers formatted per RFC
8785 §3.2.2.3, whitespace removed.

The following objects **MUST** be canonicalized with JCS before being:

- Signed (for IsccNote, IsccNoteDelete, IsccReceipt).
- Hashed (for log entries appended to the transparency log).
- Compared byte-for-byte (for verifying signature scope agreement).

Implementations **MUST** use a JCS implementation that conforms to RFC 8785. Implementations **MUST NOT** introduce
alternative canonicalization rules.

### 6.3 Field encodings

The following encodings apply to fields in their JSON representation.

- **ISCC-CODE / ISCC-ID / ISCC-UNIT.** Encoded as the standard ISCC string form `ISCC:` followed by uppercase Base32
    [[RFC4648]](#rfc4648). The pattern `^ISCC:[A-Z0-9]{n,m}$` applies, where `n` and `m` depend on the code type.
    ISCC-IDs are exactly 16 characters following the `ISCC:` prefix.
- **BLAKE3 multihash.** Encoded as 68 lowercase hexadecimal characters: the literal `1e20` (multihash code `0x1e` for
    BLAKE3, length `0x20` = 32 bytes) followed by 64 hex characters representing the digest. Matches the regular
    expression `^1e20[0-9a-f]{64}$`.
- **128-bit nonce.** Encoded as 32 lowercase hexadecimal characters. Matches `^[0-9a-f]{32}$`.
- **Ed25519 public key.** Encoded as multibase `z` + base58-btc, with multicodec prefix `0xed01`. Matches
    `^z[1-9A-HJ-NP-Za-km-z]{47,48}$` in practice.
- **Ed25519 signature value.** Encoded as multibase `z` + base58-btc. Matches `^z[1-9A-HJ-NP-Za-km-z]+$`.
- **Timestamp.** Encoded per RFC 3339 §5.6 with millisecond precision and uppercase `Z` suffix indicating UTC. Matches
    `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$`.
- **URI / URI template.** Encoded as a UTF-8 string per [[RFC3986]](#rfc3986) / [[RFC6570]](#rfc6570).

## 7. ISCC-ID

The ISCC-ID is a 64-bit globally unique identifier issued by a Hub. Its structure is **load-bearing**: ISCC-IDs are
intended to remain valid and verifiable indefinitely. The structure defined in this section **MUST NOT** change in
subsequent revisions of this specification.

### 7.1 Body structure

The 64-bit ISCC-ID body is composed of:

- **Bits 0–51 (52 bits):** Microsecond timestamp, unsigned integer, representing microseconds elapsed since
    `1970-01-01T00:00:00Z` (Unix epoch). Big-endian, most-significant bit first.
- **Bits 52–63 (12 bits):** Hub identifier (`hub_id`), unsigned integer in the range 0–4095. Big-endian.

The timestamp field provides microsecond resolution. The Hub's sequencer **MUST** ensure that successive ISCC-IDs issued
by the same Hub have strictly monotonically increasing timestamp fields (see [§9.3](#93-validation-procedure)).

The `hub_id` field identifies the issuing Hub. The mapping of `hub_id` to Hub public key and base URL is defined by the
Hub-List.

### 7.2 Encoded form

ISCC-IDs are exchanged in the standard ISCC string form:

- The 64-bit body is prefixed with the standard ISCC header (16 bits): `MAINTYPE = 0110` (ISCC-ID), `SUBTYPE = 0000`
    (REALM), `VERSION = 0001` (V1), `LENGTH = 0001` (64-bit body). The resulting 80-bit value is encoded as 16
    characters of uppercase Base32 with the leading literal `ISCC:`.
- Total string length: 21 characters (`ISCC:` + 16). Matches the regex `^ISCC:[A-Z2-7]{16}$`.

Implementations **MAY** store the 8-byte binary body internally and reconstruct the header on serialization.

## 8. Signatures

### 8.1 Algorithm

All signatures defined by this specification use **Ed25519** [[RFC8032]](#rfc8032) with the IsccSignature object format
from [[ISCC-SIG]](#iscc-sig).

### 8.2 Signing scope

To sign an IsccNote or IsccNoteDelete:

1. Let *object* be the object to be signed; it **MUST NOT** yet carry a `signature.proof` value.
2. Construct *object*`.signature` with `version`, the embedded `pubkey`, and any optional `controller`/`keyid` —
    **without** a `proof` key.
3. Canonicalize *object* with JCS per [§6.2](#62-canonicalization-jcs). The `proof` key is **absent** from the
    canonicalized bytes (it is not set to a placeholder).
4. Compute *signature* = Ed25519-Sign(secret_key, canonical_bytes).
5. Encode *signature* as multibase `z` + base58-btc.
6. Set *object*`.signature.proof` to the encoded signature value.

The resulting object is the **signed form** transmitted on the wire. `pubkey` is **REQUIRED** in every
IsccNote/IsccNoteDelete signature; PROOF_ONLY signatures (carrying only `version` and `proof`, with no embedded
`pubkey`) are **rejected** so that every log entry is offline-verifiable from its own bytes. The IsccReceipt uses the
W3C Data Integrity proof structure instead of the IsccSignature object; see
[§8.5](#85-issccreceipt-signature-procedure).

### 8.3 Verification procedure

To verify the signature on an IsccNote or IsccNoteDelete:

1. Let *object* be the received signed object.
2. Let *received_proof* be *object*`.signature.proof`.
3. Remove the `proof` key from *object*`.signature` (canonicalization omits it; it **MUST NOT** be replaced with a
    placeholder).
4. Canonicalize *object* with JCS per [§6.2](#62-canonicalization-jcs).
5. Decode *object*`.signature.pubkey` (strip `z` prefix, base58-btc decode, strip multicodec prefix `0xed01`) to obtain
    a 32-byte Ed25519 public key. A signature without an embedded `pubkey` is rejected.
6. Decode *received_proof* (strip `z` prefix, base58-btc decode) to obtain a 64-byte Ed25519 signature value.
7. Compute *valid* = Ed25519-Verify(public_key, canonical_bytes, signature).
8. If *valid* is false, the signature is invalid.

### 8.4 Controller resolution

If an IsccSignature includes a `controller` field, a verifier **MAY** resolve the controller URI to verify that `pubkey`
is currently authorized to sign on behalf of that controller. Resolution behavior depends on the URI scheme:

- `did:key:` controllers carry the public key directly in the DID. No external resolution is required. A verifier
    **MUST** confirm that the key encoded in the DID matches `signature.pubkey`.
- `did:web:` controllers **MAY** be resolved by fetching the DID document per [[DID-WEB]](#did-web). A verifier that
    performs resolution **MUST** confirm that `signature.pubkey` appears as a verification method authorized for
    `assertionMethod` (or, for the IsccReceipt proof, `assertionMethod` of the issuing Hub).
- HTTPS controller URLs **MAY** be resolved by fetching a W3C Controlled Identifier Document [[CID]](#cid) at the given
    URL. The same verification-method check applies.

A Hub **MAY** choose, as an operational policy, whether to perform controller resolution during declaration validation.
The choice does not affect interoperability of correctly signed IsccNotes.

### 8.5 IsccReceipt signature procedure

The IsccReceipt uses the W3C Data Integrity `eddsa-jcs-2022` cryptosuite [[VC-DI-EDDSA]](#vc-di-eddsa) rather than the
IsccSignature object. The procedure differs from [§8.2](#82-signing-scope) as follows:

1. Construct the receipt including all fields except `proof.proofValue`.
2. The `proof` object **MUST** be present with all required fields except `proofValue`.
3. Canonicalize the entire receipt with JCS per [§6.2](#62-canonicalization-jcs).
4. Compute *hash* = SHA-256(canonical_bytes).
5. Compute *signature* = Ed25519-Sign(hub_secret_key, hash).
6. Encode *signature* as multibase `z` + base58-btc.
7. Set `proof.proofValue` to the encoded signature value.

To verify an IsccReceipt:

1. Let *received_proof_value* be `proof.proofValue`.
2. Remove `proof.proofValue` from the receipt.
3. Canonicalize the receipt with JCS.
4. Hash with SHA-256 and verify the signature using the Hub's Ed25519 public key (resolved from
    `proof.verificationMethod` via the Hub-List or DID document).

## 9. Declaration submission

### 9.1 Submission endpoint

A conforming Hub **MUST** expose the following HTTP endpoint:

```
POST /declaration
Content-Type: application/json
Accept: application/json
```

The request body **MUST** be a JSON document conforming to one of the two shapes defined in [§9.2](#92-request-shapes).

### 9.2 Request shapes

A Hub **MUST** accept two request shapes.

**Bare shape** — the request body is an IsccNote:

```json
{
  "$schema": "http://purl.org/iscc/schema/iscc-note-0.8.0.json",
  "iscc_code": "...",
  "datahash": "...",
  "nonce": "...",
  "signature": {
    "...": "..."
  }
}
```

**Envelope shape** — the request body is an envelope containing an IsccNote and optional unsigned metadata attachment:

```json
{
  "iscc_note": {
    "$schema": "http://purl.org/iscc/schema/iscc-note-0.8.0.json",
    "iscc_code": "...",
    "datahash": "...",
    "nonce": "...",
    "metahash": "...",
    "signature": {
      "...": "..."
    }
  },
  "metadata": {
    "...": "..."
  }
}
```

A Hub determines which shape is in use by checking for the presence of the top-level `iscc_note` key. If `iscc_note` is
present, the envelope shape applies. Otherwise, the bare shape applies.

The envelope shape **MAY** include a `metadata` sibling. If present, the IsccNote inside the envelope **MUST** include a
`metahash` field whose value equals `BLAKE3(JCS(metadata))` encoded as a multihash. A Hub **MUST** reject a submission
containing `metadata` without a matching `metahash` on the inner IsccNote.

The bare shape is provided for backward compatibility with implementations that do not support metadata forwarding. The
envelope shape is the **RECOMMENDED** form for new declarers.

### 9.3 Validation procedure

Upon receiving a `POST /declaration` request, a conforming Hub **MUST** perform the following steps in order. The first
step that fails determines the error response per [§9.5](#95-error-responses).

1. **Parse JSON.** If the request body is not valid UTF-8 JSON, return HTTP 400 with error code `INVALID_JSON`.
2. **Detect shape.** Determine whether the request is bare or envelope per [§9.2](#92-request-shapes).
3. **Validate IsccNote structure.** Confirm that all required fields (including `$schema`) are present, that `$schema`
    is in the Hub's supported allowlist, that all field encodings conform to [§6.3](#63-field-encodings), and that no
    unknown top-level fields are present (`@context`/`@type` are rejected here). If validation fails, return HTTP 422
    with error code `INVALID_NOTE` and a `field` identifier.
4. **Validate `nonce` hub binding.** Confirm that the top 12 bits of the `nonce` (the first 3 hex characters) equal the
    receiving Hub's `hub_id`. If not, return HTTP 422 with error code `NONCE_HUB_MISMATCH`.
5. **Validate timestamp policy.** If `timestamp` is absent, reject with HTTP 422 (error code `INVALID_NOTE`, with a
    `field` identifier of `timestamp`) only when the Hub's `REQUIRE_CLIENT_TIMESTAMP` policy is enabled; otherwise
    accept and let the Hub assign its own timestamp at sequencing. If `timestamp` is present it **MUST** use the
    strict RFC 3339 form (`Z`, 3-digit ms); a Hub **MAY** range-check it against `TIMESTAMP_TOLERANCE_SECONDS`
    (default ±600 s; `0` disables) and return HTTP 422 with error code `TIMESTAMP_OUT_OF_RANGE` if the value is
    outside the tolerance.
6. **Verify declarer signature.** Run the verification procedure from [§8.3](#83-verification-procedure). If the
    signature does not verify, return HTTP 401 with error code `INVALID_SIGNATURE`.
7. **Verify controller (optional).** If `signature.controller` is present and the Hub performs controller resolution
    per [§8.4](#84-controller-resolution), return HTTP 401 with error code `CONTROLLER_KEY_NOT_AUTHORIZED` on
    mismatch.
8. **Verify metadata binding.** If the request uses the envelope shape and includes `metadata`, compute
    `BLAKE3(JCS(metadata))` and confirm it matches the IsccNote's `metahash`. On mismatch, return HTTP 422 with error
    code `METAHASH_MISMATCH`.
9. **Check nonce uniqueness.** If `nonce` has previously been used in a declaration accepted by this Hub, return HTTP
    409 with error code `NONCE_REUSED`.
10. **Check duplicate-declaration policy.** If the Hub enforces a soft duplicate check on `datahash` and a prior
    declaration exists, and the request does not include the header `X-Force-Declaration: true`, return HTTP 409 with
    error code `DUPLICATE_DATAHASH`. See [§9.6](#96-duplicate-declarations).
11. **Check permission mode.** If the Hub operates in permissioned mode (see [§12](#12-permission-modes)) and the
    declarer's `pubkey` is not in the Hub's authorized-key list, return HTTP 401 with error code `KEY_NOT_AUTHORIZED`.
12. **Atomically commit.** Within a single atomic transaction:
    - Assign a microsecond-precision Hub timestamp strictly greater than the most recent prior Hub timestamp.
    - Compose the ISCC-ID from the timestamp and the Hub's `hub_id`.
    - Compose the canonical log entry per [§5.4](#54-log-entry).
    - Append the log entry to the Hub's transparency log.
13. **Compose and return IsccReceipt.** Build the IsccReceipt per [§5.3](#53-isccreceipt), sign per
    [§8.5](#85-issccreceipt-signature-procedure), and return it with HTTP status `201 Created`.

If metadata forwarding applies (envelope shape with `metadata` present and `gateway` resolvable per
[§13](#13-metadata-forwarding)), the Hub **SHOULD** initiate the forward asynchronously after step 12. The forward
outcome **MUST NOT** affect the success status of the declaration.

### 9.4 Response

On success, the Hub returns:

- **Status:** `201 Created`.
- **Content-Type:** `application/json`.
- **Body:** The IsccReceipt as defined in [§5.3](#53-isccreceipt).

### 9.5 Error responses

Errors are returned as JSON documents with the following shape:

```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE",
  "field": "iscc_code"
}
```

The `code` and `field` properties are **OPTIONAL** but **RECOMMENDED** to aid programmatic handling.

The following HTTP status codes are used.

| Status                      | Meaning                                                                                      |
| --------------------------- | -------------------------------------------------------------------------------------------- |
| `400 Bad Request`           | Malformed request (invalid JSON, missing Accept header, etc.).                               |
| `401 Unauthorized`          | Signature invalid, controller unauthorized, or key not authorized.                           |
| `409 Conflict`              | Duplicate declaration (with `X-Force-Declaration` not set), or nonce reuse.                  |
| `422 Unprocessable Entity`  | Validation failure (field encoding, nonce hub mismatch, timestamp bounds, etc.).             |
| `500 Internal Server Error` | Sequencer or log failure. Implementations **SHOULD** retry idempotently using a fresh nonce. |

Error code values defined by this specification:

`INVALID_JSON`, `INVALID_NOTE`, `NONCE_HUB_MISMATCH`, `TIMESTAMP_OUT_OF_RANGE`, `INVALID_SIGNATURE`,
`CONTROLLER_KEY_NOT_AUTHORIZED`, `METAHASH_MISMATCH`, `NONCE_REUSED`, `DUPLICATE_DATAHASH`, `KEY_NOT_AUTHORIZED`,
`INTERNAL_ERROR`.

Implementations **MAY** define additional error codes provided they are distinct from the values above.

### 9.6 Duplicate declarations

Two distinct declarations of the same content (same `datahash`) by the same or different declarers are **valid** at the
protocol level. Multiple parties may legitimately declare the same content; each declaration produces a distinct ISCC-ID
with distinct provenance.

A Hub **MAY** apply a soft duplicate check that rejects a second declaration of a previously seen `datahash` with HTTP
409 unless the request includes the header `X-Force-Declaration: true`. This is an operator convenience to help
declarers catch unintended re-submissions. It is **NOT** a protocol-level uniqueness guarantee.

## 10. Declaration deletion

A declarer **MAY** request deletion of a previously committed declaration. Deletion does not remove the original
declaration entry from the transparency log — the log is append-only. Instead, the Hub appends a **deletion entry** that
signals to consumers of the log (Aggregators, Verifiers, downstream indexes) that the declaration has been redacted.

### 10.1 Deletion endpoint

A conforming Hub **MUST** expose the following HTTP endpoint:

```
DELETE /declaration/{iscc_id}
Content-Type: application/json
Accept: application/json
```

The `{iscc_id}` path parameter **MUST** be the ISCC-ID in its standard 21-character string form.

The request body **MUST** be an IsccNoteDelete object as defined in [§5.5](#55-deletion-entry-isccnotedelete).

### 10.2 Deletion validation procedure

A conforming Hub **MUST** perform the following steps in order.

1. **Parse JSON.** On failure return HTTP 400, `INVALID_JSON`.
2. **Validate IsccNoteDelete structure.** Confirm all required fields are present, no unknown fields are present, and
    the body's `iscc_id` equals the path parameter. On failure return HTTP 422, `INVALID_DELETION`.
3. **Validate `nonce` hub binding.** As in [§9.3](#93-validation-procedure) step 4.
4. **Validate timestamp policy.** As in [§9.3](#93-validation-procedure) step 5: reject an absent `timestamp` only when
    the Hub's `REQUIRE_CLIENT_TIMESTAMP` policy is enabled (HTTP 422, error code `INVALID_DELETION`, with a `field`
    identifier of `timestamp`); when `timestamp` is present it **MUST** use the strict RFC 3339 form and a Hub **MAY**
    range-check it against `TIMESTAMP_TOLERANCE_SECONDS`, returning HTTP 422 with error code `TIMESTAMP_OUT_OF_RANGE`
    if the value is outside the tolerance.
5. **Resolve original declaration.** Look up the existing declaration by `iscc_id`. If not found or already deleted,
    return HTTP 404, `DECLARATION_NOT_FOUND`.
6. **Verify declarer signature.** Run the verification procedure from [§8.3](#83-verification-procedure) over the
    IsccNoteDelete.
7. **Verify deletion authorization.** Confirm that the `signature.pubkey` of the IsccNoteDelete equals the
    `signature.pubkey` of the original IsccNote that produced the `iscc_id`. On mismatch, return HTTP 401,
    `NOT_AUTHORIZED_TO_DELETE`.
8. **Check nonce uniqueness.** As in [§9.3](#93-validation-procedure) step 9.
9. **Atomically commit.** Within a single atomic transaction:
    - Assign a microsecond-precision Hub timestamp strictly greater than the most recent prior Hub timestamp.
    - Compose the deletion log entry per [§5.4](#54-log-entry) with `type` = `"deletion"`.
    - Append the entry to the Hub's transparency log.
    - Remove or mark redacted the materialized declaration record so that subsequent lookups by `iscc_id` reflect the
        deletion.
10. **Return success.** HTTP 204 No Content, with no response body.

### 10.3 Log effects of deletion

After a deletion entry is committed:

- The original declaration entry **MUST** remain in the transparency log in its original byte form.
- The deletion entry **MUST** remain in the transparency log in its original byte form.
- The Hub's resolution endpoint (defined in *IDP Lookup & Resolution*) **MUST** treat the declaration as deleted:
    returning HTTP 410 Gone or an equivalent deleted-state response.
- Downstream consumers (Aggregators, Verifiers) that observe the deletion entry **SHOULD** propagate the deletion to
    their derived indexes.

## 11. Nonce handling

The `nonce` field on an IsccNote or IsccNoteDelete provides replay protection in two senses.

**Cross-Hub replay protection.** The top 12 bits of the nonce **MUST** equal the `hub_id` of the target Hub. A nonce
constructed for Hub A cannot be replayed against Hub B because Hub B's `hub_id` validation will fail. The receiving Hub
**MUST** verify the top 12 bits against its own `hub_id` per [§9.3](#93-validation-procedure) step 4.

**Per-Hub replay protection.** Within a single Hub, no two accepted declarations or deletions may share the same
`nonce`. The Hub **MUST** maintain a nonce index and reject submissions whose nonce has been previously accepted, with
HTTP 409 and error code `NONCE_REUSED`.

Nonce generation: declarers **MUST** use a cryptographically secure random source to generate the 116 random bits (bits
12–127). The 12 most significant bits **MUST** be set to the target Hub's `hub_id` and **MUST NOT** be derived from
randomness.

A Hub **MAY** garbage-collect nonces older than a configurable retention window if doing so does not weaken replay
protection in practice (e.g., because the Hub also enforces an earliest-accepted timestamp bound). Garbage collection is
an operational choice; this specification places no requirement on retention.

## 12. Permission modes

This section is **informative**.

A Hub **MAY** operate in any of the following modes.

- **Open.** Any declarer with a valid signature may declare. The Hub applies signature and replay validation but does
    not constrain the set of authorized keys.
- **Permissioned.** Only declarers whose `pubkey` appears in a Hub-maintained authorized-key list may declare. The Hub
    rejects submissions from unauthorized keys with HTTP 401, error code `KEY_NOT_AUTHORIZED`.
- **Hybrid.** Some operational mix, such as open declarations with rate-limiting per key, or permissioned declarations
    with public read-only access.

Permission mode is an operator policy choice. This specification does not prescribe a default mode. Declarers can detect
the mode in effect by attempting a declaration and observing the response.

## 13. Metadata forwarding

This section defines optional behavior. A Hub that supports the envelope shape per [§9.2](#92-request-shapes) **MAY**
forward `metadata` attachments to a Gateway identified by the IsccNote's `gateway` field.

The metadata forwarding mechanism is summarized here and specified in full by the *IDP Lookup & Resolution* companion
specification.

### 13.1 Forwarding precondition

Before forwarding metadata to a Gateway origin for the first time, a Hub **MUST** fetch:

```
GET <gateway-origin>/.well-known/iscc-gateway
```

The Hub **MUST NOT** forward to a Gateway origin unless this document exists and contains `"accept_forwards": true`. The
Hub **SHOULD** cache this response for a minimum of one hour, respecting any `Cache-Control` directive in the response.

### 13.2 Forwarding envelope

When forwarding, the Hub wraps the metadata in an envelope signed by the Hub:

```json
{
  "iscc_id": "ISCC:...",
  "iscc_note": {
    "...": "original IsccNote with declarer signature"
  },
  "metadata": {
    "...": "the attachment"
  },
  "forwarded_at": "2026-05-21T12:34:57.123Z",
  "hub_signature": {
    "...": "IsccSignature by Hub"
  }
}
```

The Hub-signature scope is the canonicalized envelope with the `hub_signature.proof` key **absent**, computed per
[§8.2](#82-signing-scope).

### 13.3 Delivery semantics

Metadata forwarding is **best-effort**:

- The declaration **MUST** succeed (HTTP 201) regardless of forwarding outcome.
- A Hub **SHOULD** retry transient forwarding failures (suggested: up to 3 attempts within 1 hour).
- A Hub **SHOULD** record forwarding outcomes in operational logs.

## 14. Security considerations

### 14.1 Signature validation

The integrity of the entire protocol rests on Ed25519 signature validation. Implementations **MUST** use a well-reviewed
Ed25519 library. Implementations **MUST NOT** accept signatures with malleable encodings (see RFC 8032 §5.1.7); the
cofactored verification check is the SHOULD default but the strict (non-malleable) check is **RECOMMENDED**.

### 14.2 Canonicalization correctness

JCS-canonicalized bytes are the integrity anchor of every signed object in this protocol. A non-conformant JCS
implementation can cause a Hub to accept a maliciously crafted IsccNote whose signature does not in fact cover the bytes
the Hub interprets. Implementations **SHOULD** include test vectors from RFC 8785 §3 in their unit-test suite and
**SHOULD** verify byte-equality against an independent JCS implementation.

### 14.3 Nonce predictability

A predictable nonce permits a network attacker to pre-compute and submit declarations on behalf of a victim if the
attacker possesses the victim's signing key. The nonce itself does not protect against key compromise. Implementations
**MUST** generate the 116 random bits of the nonce from a cryptographically secure random source.

### 14.4 Cross-Hub replay

The `nonce` top-12-bits binding (see [§11](#11-nonce-handling)) prevents an IsccNote signed for Hub A from being
accepted by Hub B without re-signing. This binding **MUST NOT** be weakened in future revisions of the protocol.

### 14.5 DoS via gateway forwarding

Without the well-known opt-in mechanism described in [§13.1](#131-forwarding-precondition), the Hub network could be
weaponized to issue forwarding traffic against arbitrary URLs declared in IsccNote `gateway` fields. A conforming Hub
**MUST NOT** forward to a Gateway origin without first confirming opt-in.

### 14.6 Hub key compromise

If a Hub's signing key is compromised, all IsccReceipts issued by that Hub are forensically suspect. Mitigations:

- The transparency log is OTS-anchored to Bitcoin per the *ISCC-Log Specification*. Independent observers can prove that
    specific entries were present in the log at specific times, limiting the attacker's ability to forge backdated
    entries.
- The Hub-List **MUST** support key rotation: a compromised key entry should be retired and a new key issued. Receipts
    issued under the old key remain verifiable against the historical Hub-List entry.

### 14.7 Declarer key compromise

If a declarer's signing key is compromised, an attacker can declare content on the declarer's behalf and can delete the
declarer's existing declarations. Mitigations are outside the protocol surface (e.g., key rotation in the declarer's DID
document, hardware-backed key storage). A declarer **SHOULD NOT** use the same key for declaration as for high-stakes
identity operations.

## 15. IANA considerations

This specification does not require any IANA registry actions in its present form.

A future revision may register:

- A `+iscc-note` JSON structured-suffix media type.
- An `iscc:` URI scheme (currently used informally via the `ISCC:` prefix in code strings).

## 16. References

### 16.1 Normative references

<a id="rfc2119"></a>**[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
2119, March 1997.

<a id="rfc3339"></a>**[RFC3339]** Klyne, G., Newman, C., "Date and Time on the Internet: Timestamps", RFC 3339, July
2002\.

<a id="rfc3629"></a>**[RFC3629]** Yergeau, F., "UTF-8, a transformation format of ISO 10646", STD 63, RFC 3629, November
2003\.

<a id="rfc3986"></a>**[RFC3986]** Berners-Lee, T., Fielding, R., Masinter, L., "Uniform Resource Identifier (URI):
Generic Syntax", STD 66, RFC 3986, January 2005.

<a id="rfc4648"></a>**[RFC4648]** Josefsson, S., "The Base16, Base32, and Base64 Data Encodings", RFC 4648, October
2006\.

<a id="rfc6570"></a>**[RFC6570]** Gregorio, J., Fielding, R., Hadley, M., Nottingham, M., Orchard, D., "URI Template",
RFC 6570, March 2012.

<a id="rfc8032"></a>**[RFC8032]** Josefsson, S., Liusvaara, I., "Edwards-Curve Digital Signature Algorithm (EdDSA)", RFC
8032, January 2017.

<a id="rfc8174"></a>**[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
8174, May 2017.

<a id="rfc8785"></a>**[RFC8785]** Rundgren, A., Jordan, B., Erdtman, S., "JSON Canonicalization Scheme (JCS)", RFC 8785,
June 2020.

<a id="iso-24138"></a>**[ISO-24138]** ISO 24138:2024, "Information and documentation — International Standard Content
Code (ISCC)".

<a id="iscc-sig"></a>**[ISCC-SIG]** "ISCC Signature Specification v1.0", ISCC Foundation,
<https://crypto.iscc.codes/iscc-sig-spec/>.

<a id="vc-data-model"></a>**[VC-DATA-MODEL]** W3C Recommendation, "Verifiable Credentials Data Model v2.0",
<https://www.w3.org/TR/vc-data-model-2.0/>.

<a id="vc-data-integrity"></a>**[VC-DATA-INTEGRITY]** W3C Recommendation, "Verifiable Credential Data Integrity 1.0",
<https://www.w3.org/TR/vc-data-integrity/>.

<a id="vc-di-eddsa"></a>**[VC-DI-EDDSA]** W3C Recommendation, "Data Integrity EdDSA Cryptosuites v1.0",
<https://www.w3.org/TR/vc-di-eddsa/>.

<a id="cid"></a>**[CID]** W3C Recommendation, "Controlled Identifiers v1.0", <https://www.w3.org/TR/cid-1.0/>.

### 16.2 Informative references

<a id="did-web"></a>**[DID-WEB]** W3C Community Group Report, "did:web Method Specification",
<https://w3c-ccg.github.io/did-method-web/>.

## Appendix A: Examples

This appendix is non-normative.

### A.1 Minimal IsccNote

```json
{
  "$schema": "http://purl.org/iscc/schema/iscc-note-0.8.0.json",
  "iscc_code": "ISCC:KACWN77F73NA44D6EUG3S3QNJIL2BPPQFMW6ZX6CZNOKPAK23S2IJ2I",
  "datahash": "1e205ca7815adcb484e9a136c11efe69c1d530176d549b5d18d038eb5280b4b3470c",
  "nonce": "00197932bfe2d31f11d8709be50f84bd",
  "signature": {
    "version": "ISCC-SIG v1.0",
    "pubkey": "z6MkmeDbeC5BecFmVnTHA5PWEBaVUrGLdB3weGE2KYnXfHso",
    "proof": "znTcLukuu7CL8FpoaSxr6UWQpxCogZUCZ9iqx9dnP3inkzGszbUN79qrxWvpxEHnuNtLQ5Jd1rBukY7g1JSiYHVZ"
  }
}
```

The first 12 bits of the nonce (`001`) bind this note to a Hub with `hub_id = 1`.

### A.2 IsccNote with optional fields

```json
{
  "$schema": "http://purl.org/iscc/schema/iscc-note-0.8.0.json",
  "iscc_code": "ISCC:KACWN77F73NA44D6EUG3S3QNJIL2BPPQFMW6ZX6CZNOKPAK23S2IJ2I",
  "datahash": "1e205ca7815adcb484e9a136c11efe69c1d530176d549b5d18d038eb5280b4b3470c",
  "metahash": "1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598",
  "nonce": "0013a3c214c05796673503e6e549446d",
  "timestamp": "2026-05-21T10:42:00.000Z",
  "gateway": "https://example.com/iscc_id/{iscc_id}",
  "units": [
    "ISCC:AADWN77F73NA44D6X3N4VEUAPOW5HJKGK5JKLNGLNFPOESXWYDVDVUQ",
    "ISCC:EADSKDNZNYGUUF5AMFEJLZ5P66CP5YKCOA3X7F36RWE4CIRCBTUWXYY"
  ],
  "signature": {
    "version": "ISCC-SIG v1.0",
    "controller": "did:web:example.com",
    "pubkey": "z6MkmeDbeC5BecFmVnTHA5PWEBaVUrGLdB3weGE2KYnXfHso",
    "proof": "z5j9nrpPw3oYSAN4XbCvk2sUtkwrueTD6V2Y35gS1KFTode2ED2YQWokPmoXw6QBYtYEFxtAQfzBhdNyr8PMwP79G"
  }
}
```

### A.3 Envelope shape with metadata attachment

```json
{
  "iscc_note": {
    "$schema": "http://purl.org/iscc/schema/iscc-note-0.8.0.json",
    "iscc_code": "ISCC:KACWN77F73NA44D6EUG3S3QNJIL2BPPQFMW6ZX6CZNOKPAK23S2IJ2I",
    "datahash": "1e205ca7815adcb484e9a136c11efe69c1d530176d549b5d18d038eb5280b4b3470c",
    "metahash": "1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598",
    "nonce": "0013a3c214c05796673503e6e549446d",
    "gateway": "https://registry.example.com/iscc_id/{iscc_id}",
    "signature": {
      "version": "ISCC-SIG v1.0",
      "pubkey": "z6MkmeDbeC5BecFmVnTHA5PWEBaVUrGLdB3weGE2KYnXfHso",
      "proof": "z5j9nrpPw3oYSAN4XbCvk2sUtkwrueTD6V2Y35gS1KFTode2ED2YQWokPmoXw6QBYtYEFxtAQfzBhdNyr8PMwP79G"
    }
  },
  "metadata": {
    "@context": "https://schema.iscc.codes/v1",
    "name": "Example article",
    "tdm_reservation": true
  }
}
```

### A.4 IsccReceipt

```json
{
  "@context": [
    "https://www.w3.org/ns/credentials/v2"
  ],
  "type": [
    "VerifiableCredential",
    "IsccReceipt"
  ],
  "issuer": "did:web:hub.example.com",
  "credentialSubject": {
    "id": "did:web:example.com",
    "declaration": {
      "seq": 1234567,
      "iscc_id": "ISCC:MAEK2NC3Y5VZ4XQM",
      "iscc_note": {
        "...": "canonical IsccNote, see A.2"
      }
    }
  },
  "proof": {
    "@context": [
      "https://www.w3.org/ns/credentials/v2"
    ],
    "type": "DataIntegrityProof",
    "cryptosuite": "eddsa-jcs-2022",
    "verificationMethod": "did:web:hub.example.com#z6MkkRXoNEjqGNKHrPh8a54g6B2kqLp5M6HyA7odbCh1mDwX",
    "proofPurpose": "assertionMethod",
    "proofValue": "z3yW8rT4qP9uX7vS6mN1oL2kJ5hG8fD3cB9zA4xE7yV1qM8nR6pW2tY5iU0oP3mL9kJ8hG5fD2cB1zA6xE9yV3qM"
  }
}
```

### A.5 IsccNoteDelete

```json
{
  "$schema": "http://purl.org/iscc/schema/iscc-note-delete-0.8.0.json",
  "iscc_id": "ISCC:MAEK2NC3Y5VZ4XQM",
  "timestamp": "2026-05-22T08:15:00.000Z",
  "nonce": "001d17437f53f6899ed01ecb8659118b",
  "signature": {
    "version": "ISCC-SIG v1.0",
    "controller": "did:web:example.com",
    "pubkey": "z6MkmeDbeC5BecFmVnTHA5PWEBaVUrGLdB3weGE2KYnXfHso",
    "proof": "z5j9nrpPw3oYSAN4XbCvk2sUtkwrueTD6V2Y35gS1KFTode2ED2YQWokPmoXw6QBYtYEFxtAQfzBhdNyr8PMwP79G"
  }
}
```

### A.6 Log entry (declaration)

```json
{
  "v": 1,
  "type": "declaration",
  "iscc_id": "ISCC:MAEK2NC3Y5VZ4XQM",
  "note": {
    "...": "canonical IsccNote, see A.2"
  }
}
```

### A.7 Log entry (deletion)

```json
{
  "v": 1,
  "type": "deletion",
  "iscc_id": "ISCC:MAEK2NC3Y5VZ4XQM",
  "note": {
    "...": "canonical IsccNoteDelete, see A.5"
  }
}
```

## Appendix B: Schema reference

This appendix is non-normative.

JSON Schema files corresponding to the data structures in [§5](#5-abstract-data-model) are provided in `specs/schemas/`
as YAML sources and `.json` build outputs. These schemas are intended for use with validation tooling and code
generators. Together with this prose they **document** the plan-driven implementation; where either disagrees with the
running implementation, the implementation governs and the documentation is corrected to match.

Schema files:

- `iscc-note.yaml` — IsccNote ([§5.1](#51-isccnote)).
- `iscc-signature.yaml` — IsccSignature ([§5.2](#52-iscc-signature)).
- `iscc-receipt.yaml` — IsccReceipt ([§5.3](#53-isccreceipt)).
- `iscc-note-delete.yaml` — IsccNoteDelete ([§5.5](#55-deletion-entry-isccnotedelete)).
- `log-entry.yaml` — Log entry envelope ([§5.4](#54-log-entry)).
