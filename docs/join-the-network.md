---
icon: lucide/network
description: Get a hub ID and add your hub to the hub list of testnet or mainnet
---

# Join the network

The hub list connects the hubs of a network. It maps each hub ID to the URL and the public key of its hub. To join, add
your hub to the list with a pull request.
{ .iscc-lead }

## The hub lists

There is one list for each realm:

| Network | Realm | File                           |
| ------- | ----- | ------------------------------ |
| testnet | 0     | [`hubs/testnet.yaml`][testnet] |
| mainnet | 1     | [`hubs/mainnet.yaml`][mainnet] |

Each hub downloads the list of its realm from the `main` branch of this repository. It does this at start and then every
hour. The hub uses the list to send visitors to the hub that issued an ISCC-ID. Clients use the list to find hubs.

An entry has four fields:

```yaml
- hub_id: 42
  pubkey: z6Mk...
  url: https://hub.example.com
  active: true
```

| Field    | Value                                                        |
| -------- | ------------------------------------------------------------ |
| `hub_id` | The value of `ISCC_HUB_ID` of your hub                       |
| `pubkey` | The `public_key` from `iscc-crypto keygen`                   |
| `url`    | The public HTTPS URL of your hub, without a slash at the end |
| `active` | `true`                                                       |

## Steps

1. Open the list of your network and select the next free hub ID: the highest hub ID in the list plus 1. This keeps the
    hub IDs without gaps. If an open pull request already uses this hub ID, select the next one. Hub IDs go up to 4095.
2. Deploy your hub with this hub ID and the matching realm. See [Run a hub](run-a-hub.md).
3. Check that `https://<your domain>/.well-known/did.json` shows your public key.
4. Fork [iscc/iscc-hub](https://github.com/iscc/iscc-hub) and add your entry to the list.
5. Open a pull request to the `main` branch. In the description, give your organization and a contact address.
6. The ISCC Foundation reviews and merges the pull request.

The same process applies to testnet and mainnet. Start on testnet. Move to mainnet when your hub runs reliably.

!!! note "Before the merge"

    Your hub accepts declarations before your entry is in the list. But other hubs cannot send visitors to your ISCC-IDs,
    and clients do not find your hub in the list.

## Rules for listed hubs

- Run one hub for each hub ID. Never run two databases with the same hub ID.
- Keep the hub reachable at its URL. Monitors and clients download its log.
- Keep the signing key safe. If you lose it, the hub cannot sign checkpoints and receipts.

[mainnet]: https://github.com/iscc/iscc-hub/blob/main/hubs/mainnet.yaml
[testnet]: https://github.com/iscc/iscc-hub/blob/main/hubs/testnet.yaml
