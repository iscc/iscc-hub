---
icon: lucide/house
description: What an ISCC-HUB does, who runs one and where to start
---

# ISCC Hub

An ISCC-HUB is a server that timestamps signed content declarations. It gives each declaration a unique ISCC-ID and
writes it to a public transparency log that anyone can verify.
{ .iscc-lead }

This repository contains the reference implementation of the hub. It implements the
[ISCC Discovery Protocol](https://ieps.iscc.codes/iep-0013/). Independent organizations run hubs, and together they form
the hub network.

<div class="iscc-cards" markdown>

<div class="iscc-card" markdown>

### Operators

Run your own hub on testnet or mainnet with one container image.

[Run a hub →](run-a-hub.md)

</div>

<div class="iscc-card" markdown>

### Developers

Declare content, get receipts and resolve ISCC-IDs over HTTP.

[Use the API →](use-the-api.md)

</div>

<div class="iscc-card" markdown>

### Verifiers

Learn what a hub guarantees and how to check its log.

[How it works →](how-it-works.md)

</div>

</div>

## What a hub does

- It accepts declarations that the declarer signs with an Ed25519 key.
- It gives each declaration an ISCC-ID. The ISCC-ID contains a microsecond timestamp and the hub ID.
- It writes each declaration to an append-only transparency log.
- It issues a signed receipt for each declaration.
- It resolves an ISCC-ID to its declaration and to the gateway of the declarer.
- It finds declarations of identical and similar content across the hub network.

A hub does not store content or descriptive metadata. A declaration contains only codes, hashes and links.

## Find content by its ISCC-CODE

An ISCC-CODE comes from the content itself. Similar content gets a similar code. Thus a hub can find declarations
from what a file contains, not from its name or its metadata.

| Search                        | Finds                                                                    |
| ----------------------------- | ------------------------------------------------------------------------ |
| Exact lookup (`/lookup`)      | Declarations on this hub with the same ISCC-CODE or the same data hash   |
| Similarity search (`/search`) | Declarations on all hubs of the network with similar content, for example a resized image, a re-encoded video or an edited text |

For similarity search, the hub sends the query to an [iscc-search](https://search.iscc.codes/) server. That server
follows the logs of the hubs and keeps one index for the network. The hub then sorts the results so that matches with
more evidence come first. Each operator can select the search server or turn the search off. See
[Configuration](configuration.md#similarity-search).

The home page of each hub has a search field. Drop a file on it to find related declarations.

## Public hubs

| Network | Hub                                          | Hub ID |
| ------- | -------------------------------------------- | ------ |
| mainnet | [iscc.id](https://iscc.id)                   | 1      |
| mainnet | [amlet.id](https://amlet.id)                 | 2      |
| mainnet | [splia.id](https://splia.id)                 | 3      |
| testnet | [staging.iscc.id](https://staging.iscc.id)   | 1      |
| testnet | [staging.amlet.id](https://staging.amlet.id) | 2      |
| testnet | [staging.splia.id](https://staging.splia.id) | 3      |

The hub lists in the repository are the authoritative source: [`hubs/mainnet.yaml`][mainnet] and
[`hubs/testnet.yaml`][testnet].

## Specifications

The ISCC Enhancement Proposals (IEPs) define the protocol. This site describes the implementation.

| IEP                                           | Topic                                                     |
| --------------------------------------------- | --------------------------------------------------------- |
| [IEP-0011](https://ieps.iscc.codes/iep-0011/) | ISCC-ID: structure, realms and hub IDs                    |
| [IEP-0013](https://ieps.iscc.codes/iep-0013/) | ISCC Discovery Protocol: declarations, receipts, deletion |
| [IEP-0014](https://ieps.iscc.codes/iep-0014/) | ISCC Transparency Log                                     |
| [IEP-0019](https://ieps.iscc.codes/iep-0019/) | ISCC Signature                                            |

[mainnet]: https://github.com/iscc/iscc-hub/blob/main/hubs/mainnet.yaml
[testnet]: https://github.com/iscc/iscc-hub/blob/main/hubs/testnet.yaml
