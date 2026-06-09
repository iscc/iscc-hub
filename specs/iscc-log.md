# ISCC-Log Specification

**Version:** 0.1.0-draft **Status:** Working Draft **Latest editor's draft:** `specs/iscc-log.md` **Editors:** ISCC
Foundation

## Abstract

This specification defines **ISCC-Log**, the verifiable append-only transparency log maintained by an ISCC-HUB. ISCC-Log
records the declaration and deletion entries produced by the ISCC Discovery Protocol (IDP) Declaration Profile and
commits to them with a cryptographic structure that any party can verify independently of the Hub.

ISCC-Log is a **profile of the [tlog-tiles](#tlog-tiles) standard**: a single append-only [RFC 6962](#rfc6962) Merkle
tree per Hub, hashed with SHA-256, served as static tiles over HTTP, and committed by a signed
[checkpoint](#c2sp-checkpoint). Reusing tlog-tiles lets existing transparency-log clients (for example those built for
the Go checksum database, Sigsum, or Sigstore) verify an ISCC-Log with little or no modification.

## Status of This Document

This is a working draft of the ISCC-Log specification. It is published for review and is subject to change. It is
**not** a finalized specification.

This document supersedes an earlier ISCC-Log draft that committed to log entries with a BLAKE3 *bao* tree over a custom
byte stream organized into daily shards. That design was replaced by the tlog-tiles profile defined here to reduce
implementation surface and to reuse standard verifier tooling. The change does not affect the Declaration Profile: the
IsccNote and IsccReceipt are unchanged.

Implementations conforming to this draft SHOULD label themselves as *ISCC-Log v0.1-draft* and document conformance
exceptions explicitly.

## Table of Contents

1. [Introduction](#1-introduction)
2. [Conformance](#2-conformance)
3. [Terminology](#3-terminology)
4. [Architecture overview](#4-architecture-overview)
5. [Log records](#5-log-records)
6. [Merkle tree](#6-merkle-tree)
7. [Tiles](#7-tiles)
8. [Checkpoint](#8-checkpoint)
9. [HTTP interface](#9-http-interface)
10. [Verification](#10-verification)
11. [Hub operations](#11-hub-operations)
12. [Trust model and deferred features](#12-trust-model-and-deferred-features)
13. [Security considerations](#13-security-considerations)
14. [References](#14-references)

## 1. Introduction

### 1.1 Motivation

The IDP Declaration Profile lets a declarer submit a signed declaration of an ISCC-CODE to an ISCC-HUB, which assigns an
ISCC-ID and commits the declaration to a transparency log. The transparency log exists so that a declaration's existence
and ordering can be proven after the fact — for audits, disputes, or litigation — without trusting the Hub's continued
good behavior or even its continued existence.

The log is optimized for that purpose. A Hub is rarely asked for an inclusion proof during normal operation; the log is
an evidentiary backstop. The design therefore favors primitives a reviewer can fully model, standard formats a
third-party verifier already understands, and static read endpoints that a CDN or archival mirror can serve in the Hub's
place.

### 1.2 Scope

This document specifies:

- The record format committed to the log (the log-entry envelope).
- The Merkle tree construction (SHA-256, RFC 6962 hashing).
- The tile layout used to publish the tree and its records.
- The checkpoint format that commits to the tree.
- The HTTP read interface.
- The inclusion- and consistency-proof verification algorithms.

### 1.3 Out of scope

- The structure and semantics of IsccNote, IsccReceipt, and the declaration and deletion APIs — see the *IDP Declaration
    Profile*.
- ISCC-ID resolution and Gateway service discovery — see *IDP Lookup & Resolution*.
- Derived indexes (ISCC-ID lookup, similarity search, analytics). These are Aggregator projections built from the log
    and are never part of the verifiable structure.
- Bitcoin anchoring and witness cosigning. These are OPTIONAL features deferred beyond the pilot; see
    [§12](#12-trust-model-and-deferred-features).

### 1.4 Document conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**,
**RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [[RFC2119]](#rfc2119)
and [[RFC8174]](#rfc8174) when, and only when, they appear in all capitals, as shown here.

Examples are non-normative unless explicitly marked otherwise.

## 2. Conformance

This specification defines three conformance classes.

### 2.1 Hub conformance

A **conforming Hub** is server software that:

- Maintains a single append-only Merkle tree per the rules in [§6](#6-merkle-tree).
- Commits each accepted log record exactly once, in sequence-number order, with no gaps, per [§5](#5-log-records) and
    [§11.1](#111-append).
- Publishes hash tiles and entry bundles per [§7](#7-tiles).
- Publishes a signed checkpoint per [§8](#8-checkpoint).
- Serves the three read endpoints defined in [§9](#9-http-interface).

### 2.2 Verifier conformance

A **conforming Verifier** is software that, given a record's sequence number, a checkpoint, and the relevant tiles:

- Verifies the checkpoint signature against the Hub's public key from the Hub-List.
- Computes an inclusion proof per [§10.1](#101-inclusion-proof) and confirms the record is committed by the checkpoint's
    root.

### 2.3 Monitor conformance

A **conforming Monitor** is software that periodically:

- Fetches checkpoints from one or more Hubs and verifies their signatures.
- Verifies consistency between successive checkpoints per [§10.2](#102-consistency-proof).
- Publishes the checkpoints it observes so that split views can be detected by comparison.

An **Aggregator** is a Monitor that additionally retains full tile data to serve as an availability backstop. Aggregator
behavior beyond Monitor conformance is not constrained by this document.

## 3. Terminology

The following terms are used throughout this specification.

- **ISCC-HUB** (or **Hub**). A server that accepts signed declarations, issues ISCC-IDs, and maintains an ISCC-Log.
- **Log record.** The canonical byte sequence committed as one leaf of the Merkle tree (see [§5](#5-log-records)).
- **Sequence number** (`i`). The zero-based index of a record in the log. The first record committed has sequence number
    `0`.
- **Tree size** (`N`). The number of records committed to the tree. A tree of size `N` commits records `0` through
    `N − 1`.
- **Merkle tree hash** (`root`). The RFC 6962 tree head over the first `N` records.
- **Tile.** A fixed-size slice of the tree or of the record data, addressable as a static resource (see [§7](#7-tiles)).
- **Checkpoint.** A signed commitment to the tree at a specific size (see [§8](#8-checkpoint)).
- **Hub-List.** The authoritative mapping of `hub_id` to Hub public key and base URL, as defined by the *IDP Declaration
    Profile*. For pilot deployments the Hub-List is a static document.
- **Monitor**, **Aggregator**, **Verifier.** Roles defined in [§2](#2-conformance).
- **JCS.** JSON Canonicalization Scheme as defined in [[RFC8785]](#rfc8785).

## 4. Architecture overview

This section is **informative**.

ISCC-Log applies the [tlog-tiles](#tlog-tiles) model to ISCC declarations. The log is a single, ever-growing RFC 6962
Merkle tree. Each accepted declaration or deletion becomes one leaf. The tree is never split into shards and never
reset; a record's sequence number is its permanent index.

Writers and observers are separated, following the Certificate Transparency operational model:

- A **Hub** is the sole writer of its log. It assigns sequence numbers, appends records, recomputes the tree head, and
    publishes a signed checkpoint.
- **Monitors** pull checkpoints and gossip them, detecting any attempt by a Hub to present different histories to
    different audiences (a *split view*).
- **Aggregators** pull full tile data and serve it, so the log remains verifiable even if the originating Hub goes
    offline.
- **Verifiers** check inclusion and consistency proofs. They need no live Hub access: a stored checkpoint plus the
    covering tiles suffices.

Reads are static files. The only operation that requires a running Hub is the write path.

> **Note.** The log's Merkle tree is hashed with SHA-256, whereas ISCC *content* hashes (the `datahash` and `metahash`
> carried inside an IsccNote) are BLAKE3. These are deliberately different primitives serving different purposes: the
> content hash identifies bytes of content, while the tree hash commits log structure using the algorithm for which
> interoperable transparency-log tooling exists.

## 5. Log records

### 5.1 Record content

Each log record is the **canonical log-entry envelope** defined in §5.4 of the *IDP Declaration Profile*: a JSON object
with members `$schema`, `iscc_id`, and `note`. The record bytes committed to the tree **MUST** be the JCS
([[RFC8785]](#rfc8785)) canonicalization of that object, encoded as UTF-8, with no surrounding whitespace.

A Hub **MUST NOT** alter a record after it has been committed. Deletion is expressed as a new record whose `note` is an
IsccNoteDelete (`note.$schema` = `iscc-note-delete-0.8.0`); it marks the prior declaration as redacted in derived
indexes but **MUST NOT** remove or rewrite any committed record.

### 5.2 Sequence numbers

The Hub **MUST** assign sequence numbers densely and monotonically: the record committed when the tree has size `N`
receives sequence number `N`. There **MUST NOT** be gaps. The sequence number assigned to a record is returned to the
declarer as the `seq` field of the IsccReceipt and is the record's permanent index `i`.

## 6. Merkle tree

ISCC-Log uses the Merkle tree defined in [[RFC6962]](#rfc6962), §2, with SHA-256 as the hash function.

- The hash of a **leaf** holding record bytes `r` is `SHA-256(0x00 || r)`.
- The hash of an **interior node** with left child `l` and right child `r` is `SHA-256(0x01 || l || r)`.
- The **Merkle tree hash** of an empty tree is `SHA-256()` of the empty string, per RFC 6962.

The tree head over the first `N` records is computed exactly as specified in RFC 6962, §2.1. Implementations **MUST**
produce tree heads identical to a conforming RFC 6962 implementation for the same record sequence.

## 7. Tiles

The tree and its records are published as **tiles** per the [tlog-tiles](#tlog-tiles) specification. This profile fixes
the tile height at **8**, so a full tile holds **256** entries.

### 7.1 Hash tiles

A **hash tile** at level `L` and index `K` holds the SHA-256 node hashes (32 bytes each) at the corresponding positions
of the tree, as defined by tlog-tiles. A full hash tile is `256 × 32 = 8192` bytes. While the tree is growing, the
rightmost tile at each level is a **partial tile** of `W` hashes where `1 ≤ W ≤ 255`; it is addressed with the `.p/<W>`
suffix defined by tlog-tiles and is rewritten as it fills.

### 7.2 Entry bundles

An **entry bundle** at index `K` bundles the 256 records whose leaf hashes occupy the level-0 hash tile at index `K`. It
is served at the tlog-tiles `tile/entries/<N>` path (see [§9](#9-http-interface)). Each record is length-prefixed as
specified by tlog-tiles for entry bundles, so a Verifier can fetch a record and its inclusion path in two requests
rather than one per tree level. Partial entry bundles use the same `.p/<W>` suffix as hash tiles.

### 7.3 Immutability

A full hash tile or entry bundle is immutable once published: its content is fixed by the records it commits. A Hub
**MUST** serve full hash tiles and entry bundles as immutable resources and **MAY** serve partial ones with a short
freshness lifetime, since a partial tile or bundle is replaced as the tree grows.

## 8. Checkpoint

A **checkpoint** commits to the tree at a specific size. It **MUST** use the
[C2SP checkpoint / signed-note](#c2sp-checkpoint) format: a text body followed by one or more signature lines.

The checkpoint body **MUST** consist of exactly three lines:

1. The **origin** — the Hub's identity string. A Hub **MUST** use a stable origin derived from its domain (for example
    `sb0.iscc.id`).
2. The decimal **tree size** `N`.
3. The base64-encoded SHA-256 **Merkle tree hash** (`root`) over the first `N` records.

#### Example: checkpoint (non-normative)

```
sb0.iscc.id
142077
8YxhYK0nQK6mF3T1Y9z6Z3iYTzJDmZAfWj2y0LM3KvY=

— sb0.iscc.id+a1b2c3d4 1z9w8e...
```

The signature line is a signed-note signature over the body. In this profile a checkpoint **MUST** carry the Hub's own
Ed25519 signature, and **MAY** carry additional signatures from witnesses (see [§12.2](#122-witness-cosigners)). A
Verifier **MUST** reject a checkpoint whose required Hub signature does not verify against the Hub's public key from the
Hub-List.

A Hub **MUST** publish a checkpoint whose tree size is monotonically non-decreasing over time. A Hub **MUST NOT**
publish two checkpoints with the same size and different roots, and **MUST NOT** publish a checkpoint at size `M` that
is inconsistent with a previously published checkpoint at size `N ≤ M`.

A Hub **SHOULD** republish the checkpoint at a fixed cadence and **SHOULD** advertise that cadence in its origin
metadata. The RECOMMENDED default cadence is 10 seconds.

## 9. HTTP interface

A Hub **MUST** expose the following three read endpoints. All are HTTP `GET`, return static content, and are cacheable.
There are no proof-computing endpoints; a Verifier computes proofs locally from tiles.

| Endpoint                    | Returns                                                         |
| --------------------------- | --------------------------------------------------------------- |
| `GET /log/checkpoint`       | The latest signed checkpoint ([§8](#8-checkpoint)).             |
| `GET /log/tile/<L>/<K>`     | The hash tile at level `L`, index `K` ([§7.1](#71-hash-tiles)). |
| `GET /log/tile/entries/<K>` | The entry bundle at index `K` ([§7.2](#72-entry-bundles)).      |

The index path encoding (including the thousands-grouped form for large indices) and the partial-tile `.p/<W>` suffix
**MUST** follow [tlog-tiles](#tlog-tiles).

A Hub:

- **MUST** set `Cache-Control` on `GET /log/checkpoint` to a max age no greater than the checkpoint cadence (RECOMMENDED
    `max-age=10`).
- **MUST** serve full tiles as immutable (RECOMMENDED `Cache-Control: immutable` with a long max age).
- **MUST** return `404 Not Found` for a tile that is not yet published.
- **MAY** return `410 Gone` for tile data that has been pruned per [§11.3](#113-pruning).

## 10. Verification

### 10.1 Inclusion proof

To **verify inclusion of record `i`** against a trusted checkpoint with size `N` and root `R` (where `i < N`), a
Verifier performs the following steps.

1. Fetch the entry bundle `GET /log/tile/entries/⌊i / 256⌋`.
2. Extract the record at offset `i mod 256` within that bundle.
3. If a record value is being checked (for example against an IsccReceipt), confirm the extracted record bytes match the
    expected canonical bytes; if they do not, return **failure**.
4. Compute the leaf hash `SHA-256(0x00 || record_bytes)`.
5. Fetch the hash tiles covering the path from leaf `i` to the tree head at size `N`, approximately
    `⌈log2(N / 256)⌉ + 1` tiles.
6. Combine the leaf hash with the sibling hashes from those tiles per [[RFC6962]](#rfc6962), §2.1.1, to compute a
    candidate root.
7. If the candidate root equals `R`, return **success**; otherwise return **failure**.

### 10.2 Consistency proof

To **verify consistency** between a trusted checkpoint of size `M` and a later checkpoint of size `N` (where `M ≤ N`), a
Verifier computes the RFC 6962 consistency proof ([[RFC6962]](#rfc6962), §2.1.2) from the hash tiles covering sizes `M`
and `N`, and confirms it relates root `R_M` to root `R_N`. If the proof does not verify, the Verifier **MUST** treat the
two checkpoints as evidence of a split view.

Because the tree is never split into shards, there is no cross-shard chaining; consistency is a single RFC 6962
operation over one tree.

## 11. Hub operations

### 11.1 Append

When the Hub accepts a declaration or deletion, it **MUST**, within a single atomic transaction:

1. Assign the next sequence number `i` (equal to the current tree size).
2. Form the canonical record bytes per [§5.1](#51-record-content).
3. Persist the record durably as the source of truth and advance the tree size to `i + 1`.

The Merkle tree, tiles, and checkpoint are a deterministic function of the committed records
([§11.2](#112-tile-materialization)) and **MAY** be derived after the transaction commits; the append transaction itself
need not perform any tree or tile work. The record **MUST** become visible in the entry bundle and committed by a
published checkpoint of size `≥ i + 1` before the Hub asserts the declaration is logged.

### 11.2 Tile materialization

Hash tiles, entry bundles, and the checkpoint **MAY** be materialized lazily or eagerly. Because every tile is a
deterministic function of the committed records, a Hub **MAY** discard a materialized tile and recompute it on demand; a
crash before materialization loses nothing, since the tree is recomputed from the records on restart. The record store,
not the tile cache, is the source of truth.

### 11.3 Pruning

A Hub **MAY** prune record and tile data according to an operator-defined retention policy. A Hub that prunes:

- **MUST** continue to serve, or delegate serving of, the checkpoints required to preserve verifiability of retained
    records.
- **MUST** return `410 Gone` for pruned tile resources.
- Does not invalidate any inclusion proof held by a third party that retained the covering tiles.

### 11.4 Aggregator synchronization

This section is **informative**. An Aggregator or other indexer synchronizes a Hub's log without trusting the Hub by:

1. Fetching `GET /log/checkpoint` and verifying its signature against the Hub's public key from the Hub-List.
2. Verifying consistency with the previously observed checkpoint per [§10.2](#102-consistency-proof).
3. Fetching the entry bundles `GET /log/tile/entries/<K>` for the newly covered range, recomputing every leaf and hash
    tile, and confirming the reconstructed root matches the signed checkpoint.

For each record, the indexer derives whether it is a declaration or a deletion from `note.$schema` (`iscc-note-0.8.0`
versus `iscc-note-delete-0.8.0`). An indexer building a resolution view **MUST** apply deletions (removing the prior
declaration for that ISCC-ID from its view) and **MUST** skip records whose `note.$schema` it does not recognize rather
than guessing their semantics.

## 12. Trust model and deferred features

The pilot profile (v1) ships a single-signer trust model. The features in this section are OPTIONAL and **MAY** be added
later without a change to the wire format, because the checkpoint format already permits additional signature lines.

### 12.1 Bitcoin anchoring (OpenTimestamps)

A Hub or any third party **MAY** submit a checkpoint to an [OpenTimestamps](#ots) calendar to obtain a proof that the
checkpoint existed at or before a given Bitcoin block. Anchoring is treated as an operational concern; it is **NOT
REQUIRED** by this profile.

### 12.2 Witness cosigners

A checkpoint **MAY** carry one or more additional signatures from independent **witnesses** that have verified
consistency with the previously published tree. Witness cosigning strengthens split-view detection. Witness discovery
and policy (for example a k-of-n threshold) are out of scope for this draft.

## 13. Security considerations

- **Split view.** A malicious Hub could present different histories to different audiences. In v1, detection relies on
    Monitor gossip: independent observers comparing the checkpoints they receive. The checkpoint format reserves space
    for witness cosignatures ([§12.2](#122-witness-cosigners)) to make equivocation detectable at fetch time in a later
    revision.
- **Cold start.** A Hub with no Monitors carries weaker guarantees, because no party is positioned to detect a split
    view. Operators **SHOULD NOT** treat a Hub as part of the federation until at least one independent Monitor declares
    coverage. The ISCC Foundation **SHOULD** maintain a public monitor-coverage registry.
- **Key compromise.** All evidentiary value flows from the Hub's signing key. Compromise of that key allows forged
    checkpoints. Hub keys **SHOULD** be held in a hardware or otherwise isolated signer, and the Hub-List **MUST**
    support key rotation.
- **Hash agility.** This profile fixes SHA-256 for the tree. A future version **MAY** define a different tree hash;
    checkpoints are versioned by their origin and tooling, and a Verifier **MUST** reject a checkpoint it cannot parse
    under a known profile.
- **Local redaction.** A Hub operator **MAY** mark a declaration as redacted to suppress it from that Hub's own
    resolution and search responses (for example, to disable resolution of abusive content). Redaction is a local policy
    control only: it writes no log record, does not alter or remove any committed record, and therefore does **not**
    propagate to Monitors, Aggregators, or other indexers, which continue to see the original declaration in the log.
    Removing a declaration from the verifiable log is only possible via a signed deletion record
    ([§5.1](#51-record-content)).

## 14. References

### Normative references

<dl>
  <dt id="rfc2119">[RFC2119]</dt>
  <dd>Bradner, S. <em>Key words for use in RFCs to Indicate Requirement
  Levels</em>. RFC 2119. March 1997.</dd>

<dt id="rfc8174">[RFC8174]</dt>
  <dd>Leiba, B. <em>Ambiguity of Uppercase vs Lowercase in RFC 2119 Key
  Words</em>. RFC 8174. May 2017.</dd>

<dt id="rfc6962">[RFC6962]</dt>
  <dd>Laurie, B., Langley, A., Kasper, E. <em>Certificate Transparency</em>.
  RFC 6962. June 2013.</dd>

<dt id="rfc8785">[RFC8785]</dt>
  <dd>Rundgren, A., Jordan, B., Erdtman, S. <em>JSON Canonicalization Scheme
  (JCS)</em>. RFC 8785. June 2020.</dd>

<dt id="tlog-tiles">[tlog-tiles]</dt>
  <dd>C2SP. <em>tlog-tiles: Tiled Transparency Logs</em>.
  <a href="https://c2sp.org/tlog-tiles">https://c2sp.org/tlog-tiles</a>.</dd>

<dt id="c2sp-checkpoint">[C2SP-checkpoint]</dt>
  <dd>C2SP. <em>checkpoint</em> and <em>signed-note</em>.
  <a href="https://c2sp.org/tlog-checkpoint">https://c2sp.org/tlog-checkpoint</a>,
  <a href="https://c2sp.org/signed-note">https://c2sp.org/signed-note</a>.</dd>
</dl>

### Informative references

<dl>
  <dt id="iso-24138">[ISO-24138]</dt>
  <dd>ISO 24138:2024, <em>Information and documentation — International Standard
  Content Code (ISCC)</em>.</dd>

<dt id="ots">[OpenTimestamps]</dt>
  <dd><em>OpenTimestamps</em>.
  <a href="https://opentimestamps.org">https://opentimestamps.org</a>.</dd>

<dt id="sunlight">[Sunlight]</dt>
  <dd>Let's Encrypt. <em>Sunlight — a tile-based Certificate Transparency
  log</em>. <a href="https://sunlight.dev">https://sunlight.dev</a>.</dd>

<dt id="transparent-logs">[Transparent-Logs]</dt>
  <dd>Cox, R. <em>Transparent Logs for Skeptical Clients</em>.
  <a href="https://research.swtch.com/tlog">https://research.swtch.com/tlog</a>.</dd>
</dl>
