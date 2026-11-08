---
icon: lucide/sliders-horizontal
description: All environment variables of the hub, with their defaults
---

# Configuration

You configure the hub with environment variables. The hub reads them at start. To apply a change, restart the container.
{ .iscc-lead }

## Required

The hub does not start if one of these variables is missing.

| Variable            | Value                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------- |
| `DJANGO_DEBUG`      | `false`                                                                                                         |
| `DJANGO_SECRET_KEY` | A long random string. Django signs sessions and CSRF tokens with it                                             |
| `ISCC_HUB_DOMAIN`   | The public host name of the hub, for example `hub.example.com`. It sets the `did:web` identity                  |
| `ISCC_HUB_SECKEY`   | The Ed25519 secret key from `iscc-crypto keygen` (`z3u2…`). It signs receipts, the DID document and checkpoints |
| `ISCC_HUB_ID`       | The hub ID, `0` to `4095`. It must be unique in the realm                                                       |
| `ISCC_HUB_REALM`    | `0` for testnet, `1` for mainnet                                                                                |

!!! warning

    Never change `ISCC_HUB_ID`, `ISCC_HUB_REALM`, `ISCC_HUB_SECKEY` or `ISCC_HUB_DOMAIN` of a running hub. See
    [Run a hub](run-a-hub.md#before-you-start).

## Admin user

| Variable             | Default | Value                                                                                                                                                 |
| -------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ISCC_HUB_ADMIN_PWD` | unset   | If set, the hub makes the user `admin` with this password at start, if the user does not exist. Changing the value later does not change the password |

## Web and proxy

| Variable                      | Default                        | Value                                                 |
| ----------------------------- | ------------------------------ | ----------------------------------------------------- |
| `DJANGO_ALLOWED_HOSTS`        | the value of `ISCC_HUB_DOMAIN` | Comma-separated host names that the hub accepts       |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` + `ISCC_HUB_DOMAIN` | Comma-separated origins, with scheme, for admin forms |

If you set one of these variables, its value replaces the default. Include the domain of the hub.

## Database

SQLite is the default. It needs no other service. PostgreSQL is the only other supported database.

| Variable                    | Default            | Value                                                           |
| --------------------------- | ------------------ | --------------------------------------------------------------- |
| `ISCC_HUB_DB_ENGINE`        | `sqlite`           | `sqlite` or `postgres`                                          |
| `ISCC_HUB_DB_NAME`          | `iscc-hub-<ID>.db` | SQLite file name in `/app/data`, for example `iscc-hub-0042.db` |
| `ISCC_HUB_SQLITE_SYNC_MODE` | `NORMAL`           | `FULL` or `NORMAL`. Use `FULL`. See below                       |
| `ISCC_HUB_DB_HOST`          | `localhost`        | PostgreSQL host                                                 |
| `ISCC_HUB_DB_PORT`          | `5432`             | PostgreSQL port                                                 |
| `ISCC_HUB_DB_USER`          | `postgres`         | PostgreSQL user                                                 |
| `ISCC_HUB_DB_PASSWORD`      | `postgres`         | PostgreSQL password                                             |
| `ISCC_HUB_DB_NAME_PG`       | `iscc_hub`         | PostgreSQL database name                                        |

With `NORMAL`, a power failure or an operating system crash can roll back declarations that the hub already confirmed
to the declarer. The hub then gives their log positions to new declarations, and monitors see two different entries at
the same position. With `FULL`, SQLite writes each transaction to disk before the hub confirms it. `FULL` makes writes a
little slower.

!!! warning "Fixed after the first start"

    Do not change `ISCC_HUB_DB_ENGINE`, `ISCC_HUB_DB_NAME` or the volume on `/app/data` after the first start. The hub
    would then start an empty log under the same identity. Keep `/app/data` on a local disk, not on NFS, SMB or a cloud
    file share.

## Acceptance policies

These policies make the hub reject declarations that the protocol permits. Policies A, B and C are on by default.
Permissioned mode is off by default.

| Variable                      | Default | Value                                                                  |
| ----------------------------- | ------- | ---------------------------------------------------------------------- |
| `ISCC_HUB_REQUIRE_DID`        | `true`  | Policy A. The signature must name a `did:web` controller               |
| `ISCC_HUB_VERIFY_DID`         | `true`  | Policy B. The DID document of the controller must list the signing key |
| `ISCC_HUB_REQUIRE_FULL_UNITS` | `true`  | Policy C. The declaration must include its ISCC-UNITs                  |
| `ISCC_HUB_DID_CACHE_TTL`      | `3600`  | Seconds that the hub keeps a successful DID check                      |
| `ISCC_HUB_OPEN_ACCESS`        | `true`  | `false` turns on permissioned mode                                     |

With policy B, the hub fetches the DID document of each new controller over HTTPS. The hub fetches only from public IP
addresses. If the hub cannot get the document, it rejects the declaration with status 503 and a `Retry-After` header.
Turn policy B off only if your declarers cannot publish a DID document.

### Permissioned mode

In permissioned mode, the hub accepts declarations only from public keys that you allow. Use it if only your own
organization or your customers may declare on your hub.

1. Set `ISCC_HUB_OPEN_ACCESS=false` and restart the hub.
2. Open `https://<your domain>/admin/` and go to **Public Keys**.
3. Add each allowed key: the `pubkey` (`z6Mk…`) and a label. Keep **Is active** set.

The hub rejects a declaration from any other key with status 401. To stop a key, clear **Is active**. The hub does not
check the list for deletions: the key that signed a declaration can always delete it. Resolution, search and the log
stay public.

## Declaration rules

| Variable                               | Default | Value                                                                                     |
| -------------------------------------- | ------- | ----------------------------------------------------------------------------------------- |
| `ISCC_HUB_REQUIRE_CLIENT_TIMESTAMP`    | `false` | `true` rejects declarations without a `timestamp`                                         |
| `ISCC_HUB_TIMESTAMP_TOLERANCE_SECONDS` | `600`   | Maximum difference between a given `timestamp` and the hub clock. `0` turns the check off |

## Similarity search

The hub sends `/search` requests to an [iscc-search](https://search.iscc.codes/) server.

| Variable                        | Default                  | Value                                                                                    |
| ------------------------------- | ------------------------ | ---------------------------------------------------------------------------------------- |
| `ISCC_HUB_SEARCH_URLS`          | `https://search.iscc.io` | Comma-separated server URLs, tried in this order. Empty turns `/search` off (status 404) |
| `ISCC_HUB_SEARCH_INDEX`         | `idptest` or `idp`       | Index name. The default is `idptest` for realm 0 and `idp` for realm 1                   |
| `ISCC_HUB_SEARCH_API_KEY`       | empty                    | Sent as `X-API-Key` header                                                               |
| `ISCC_HUB_SEARCH_TIMEOUT`       | `1.5`                    | Seconds for each server                                                                  |
| `ISCC_HUB_SEARCH_MAX_INFLIGHT`  | `24`                     | Searches at the same time for each worker. More get status 503. Only matters with `THREADS` greater than 1 |
| `ISCC_HUB_SEARCH_CB_FAILS`      | `5`                      | Failures in sequence before the hub stops to use a server                                |
| `ISCC_HUB_SEARCH_CB_COOLDOWN`   | `15`                     | Seconds before the hub tries that server again                                           |
| `ISCC_HUB_SEARCH_RERANK`        | `true`                   | Sort results again so that matches with more evidence come first                         |
| `ISCC_HUB_SEARCH_RERANK_WINDOW` | `100`                    | Number of results that the hub gets from the server to sort again                        |
| `ISCC_HUB_SEARCH_MIN_SCORE`     | `0.70`                   | Start value of the score filter on the home page. The API returns all results            |

## Home page

| Variable                 | Default               | Value                                                                                                                         |
| ------------------------ | --------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `ISCC_HUB_GENERATOR_URL` | `https://web.iscc.io` | [iscc-web](https://web.iscc.codes/) server for files that visitors drop on the home page. Empty keeps the file in the browser |

!!! note "Privacy"

    With the default value, the home page sends each dropped file to web.iscc.io to generate a full ISCC-CODE. If you set
    the variable empty, the browser calculates only the Instance-Code and the file stays on the computer of the visitor.

Show your organization on the HTML pages:

| Variable                   | Value                                                                  |
| -------------------------- | ---------------------------------------------------------------------- |
| `ISCC_HUB_ORG_NAME`        | Organization name. Set it to show the organization card and footer     |
| `ISCC_HUB_ORG_LOGO` | URL of the logo. For your own file, see below |
| `ISCC_HUB_ORG_URL`         | Organization website                                                   |
| `ISCC_HUB_ORG_TAGLINE`     | One line of text below the name                                        |
| `ISCC_HUB_CTA_ENABLED`     | `true` shows a call-to-action section                                  |
| `ISCC_HUB_CTA_TITLE`       | Title of the section                                                   |
| `ISCC_HUB_CTA_DESCRIPTION` | Text of the section                                                    |
| `ISCC_HUB_CTA_BUTTON_TEXT` | Text of the button                                                     |
| `ISCC_HUB_CTA_BUTTON_URL`  | Link of the button                                                     |

To show your own logo file:

1. Mount the file read-only into the container at `/app/iscc_hub/static/media/logo.svg`, for example
   `./logo.svg:/app/iscc_hub/static/media/logo.svg:ro` in `compose.yaml`.
2. Set `ISCC_HUB_ORG_LOGO=/media/logo.svg`.

The file is outside `/app/data`, so your backups do not contain it. Keep a copy.

## Background jobs

The container runs two jobs at intervals. It needs no other scheduler.

| Variable                       | Default | Value                                                                                                                 |
| ------------------------------ | ------- | --------------------------------------------------------------------------------------------------------------------- |
| `ISCC_HUB_LIST_INITIAL_SYNC`   | `true`  | Download the hub list at start                                                                                        |
| `ISCC_HUB_HUB_SYNC_INTERVAL`   | `3600`  | Seconds between hub list downloads. `0` turns the job off                                                             |
| `ISCC_HUB_CHECKPOINT_INTERVAL` | `86400` | Seconds between checkpoint updates. `0` turns the job off. The hub also updates the checkpoint when a client reads it |

## Web server

The container runs Gunicorn with sync workers. The hub writes declarations one at a time, so more workers give more read
capacity, not more write capacity.

| Variable              | Default | Value                                               |
| --------------------- | ------- | --------------------------------------------------- |
| `PORT`                | `8000`  | Port in the container                               |
| `WORKERS`             | `4`     | Worker processes                                    |
| `THREADS`             | `1`     | Threads for each worker                             |
| `TIMEOUT`             | `30`    | Seconds before Gunicorn stops a request             |
| `GRACEFUL_TIMEOUT`    | `30`    | Seconds for workers to finish at shutdown. Give the container more time to stop, for example `stop_grace_period: 45s` |
| `KEEP_ALIVE`          | `5`     | Seconds to keep a connection open. Gunicorn uses it only with `THREADS` greater than 1 |
| `MAX_REQUESTS`        | `1000`  | Requests before a worker restarts. `0` turns it off |
| `MAX_REQUESTS_JITTER` | `50`    | Random addition to `MAX_REQUESTS`                   |
| `LOG_LEVEL`           | `info`  | Gunicorn log level                                  |

Do not set `ENVIRONMENT=development` on the published image. That mode needs development tools that the image does not
contain.
