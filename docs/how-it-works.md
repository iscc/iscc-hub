---
icon: lucide/workflow
description: How a hub accepts a declaration, issues an ISCC-ID and records it in its transparency log
---

# How it works

A declarer signs a short JSON message about a piece of content and sends it to a hub. The hub checks the message, gives
it an ISCC-ID and records it in a public log.
{ .iscc-lead }

## Terms

| Term        | Meaning                                                                                    |
| ----------- | ------------------------------------------------------------------------------------------ |
| Declarer    | The person or organization that signs a declaration                                        |
| Declaration | A signed `IsccNote` message: ISCC-CODE, data hash, nonce and optional fields               |
| Hub         | A server that accepts declarations. The IEPs call it ISCC-HUB                              |
| Hub ID      | A number from 0 to 4095 that identifies one hub in a realm. The IEPs call it HUB-ID        |
| Realm       | The network of a hub: realm 0 is testnet (sandbox), realm 1 is mainnet (operational)       |
| Hub list    | The file that maps each hub ID of a realm to the URL of its hub. The IEPs call it HUB-LIST |
| Gateway     | A service of the declarer that serves metadata and services for its ISCC-IDs               |

## The declaration flow

1. The declarer generates an ISCC-CODE and a BLAKE3 data hash for the content.
2. The declarer makes an `IsccNote`. The first 12 bits of its nonce are the hub ID of the target hub.
3. The declarer signs the note with its Ed25519 key and sends it to the hub.
4. The hub validates the note. Then, in one database transaction, it gives the note a timestamp, makes the ISCC-ID and
    appends the note to its log.
5. The hub returns the ISCC-ID and the sequence number of the log entry.
6. The declarer gets the signed receipt. The receipt proves the declaration without help from the hub.

## The ISCC-ID

An ISCC-ID has a 64-bit body: a 52-bit timestamp in microseconds and the 12-bit hub ID. The header of the ISCC-ID
contains the realm. [IEP-0011](https://ieps.iscc.codes/iep-0011/) defines the format.

Each hub gives its declarations strictly increasing timestamps. Each hub ID is unique in its realm. Thus each ISCC-ID is
unique in its realm. ISCC-IDs of realm 0 are for tests and are not globally unique.

## The transparency log

Each hub keeps an append-only log of all declarations and deletions. The log follows the C2SP tlog-tiles format and has
a signed checkpoint. [IEP-0014](https://ieps.iscc.codes/iep-0014/) defines it.

- Entries have gapless sequence numbers that start at 0.
- The hub never changes or removes an entry.
- Anyone can download the log from `/log/` and verify it.
- [ISCC Monitor](https://monitor.iscc.codes/) follows the logs of all hubs, verifies them and keeps copies.

## Receipts

A receipt is a W3C Verifiable Credential that the hub signs. It contains the ISCC-ID, the sequence number and the
original signed note. To verify a receipt, you need only the receipt and the public key of the hub. The hub publishes
its key in its DID document at `/.well-known/did.json`.

## Deletion

Only the key that signed a declaration can delete it. A deletion is a signed `IsccNoteDelete` message. The hub appends a
deletion entry to its log. The original entry stays in the log, but the ISCC-ID no longer resolves on the hub.

## Redaction

The operator of a hub can redact a declaration in the admin interface, for example if it is malicious. A redacted
declaration does not resolve and does not show in lookups on that hub. Redaction does not change the log.

## Acceptance policies

The protocol lets each hub add stricter rules. The rules can only reject more, never accept more. The reference hub has
these policies:

| Policy             | Default | Rule                                                                                       |
| ------------------ | ------- | ------------------------------------------------------------------------------------------ |
| A                  | on      | The signature must name a `did:web` controller                                             |
| B                  | on      | The DID document of the controller must list the signing key. The hub fetches the document |
| C                  | on      | The declaration must include its ISCC-UNITs                                                |
| Permissioned mode  | off     | Only keys that the operator added in the admin interface can declare                       |

A hub in permissioned mode is still public: everyone can resolve its ISCC-IDs, search it and read its log. Only the
declarations are limited.

Some rules always apply. For example, each ISCC-UNIT must be a valid 256-bit unit, and timestamps must use the exact
form `YYYY-MM-DDTHH:MM:SS.sssZ`. [Configuration](configuration.md#acceptance-policies) tells you how to change the
policies.
