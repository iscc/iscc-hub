# ISCC Hub

A Django-based timestamping service implementing the
[ISCC Discovery Protocol](https://docs.google.com/document/d/1JdQrrBDfDPnQ08kM-onf4s0DwcntRLQVRBmbw1JImGo/) for signed
content declarations.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Django 5.2+](https://img.shields.io/badge/django-5.2+-green.svg)](https://www.djangoproject.com/)
[![Coverage 100%](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](#testing)
[![Tests](https://github.com/iscc/iscc-hub/actions/workflows/test.yaml/badge.svg?branch=main)](https://github.com/iscc/iscc-hub/actions/workflows/test.yaml)

## Overview

ISCC-HUBs accept cryptographically signed ISCC declarations, assign globally unique ISCC-IDs with precise timestamps,
and issue verifiable credentials of ISCC-ID ownership. They also resolve ISCC-IDs to owner-controlled metdata and
service endpoints and support interoperable cross-registry search and discovery by ISCC-CODEs.

**Key Features:**

- Atomic sequencing with gapless numbering and microsecond timestamps
- Ed25519 signature validation with replay attack prevention
- W3C Verifiable Credentials for tamper-proof receipts
- REST API with OpenAPI documentation
- 100% test coverage with property-based testing

## Quick Start (local development)

```bash
# Clone and setup
git clone https://github.com/iscc/iscc-hub
cd iscc-hub
uv sync

# Initialize development environment (migrations, demo user, fixtures)
uv run poe reset

# Start the development server on localhost:8000
uv run poe dev
```

Visit http://localhost:8000 for the web interface or http://localhost:8000/docs for the API documentation. This setup
uses insecure development defaults and is **not** suitable for production — see [Deployment](#deployment) for running a
real Hub.

## Deployment

ISCC-HUB ships as a single OCI container image. An operator runs **one Hub instance per Hub-ID**, backed by the embedded
SQLite database (the default) or an external PostgreSQL. The image bundles the WSGI server (Gunicorn) and static-file
serving, so the only external dependency is a TLS-terminating reverse proxy.

### Container image

Release images are published to the GitHub Container Registry on every version tag:

```text
ghcr.io/iscc/iscc-hub:latest    # most recent release
ghcr.io/iscc/iscc-hub:0.3       # latest 0.3.x
ghcr.io/iscc/iscc-hub:0.3.0     # exact version — pin this in production
```

Pin an explicit version so upgrades are deliberate. To build the image yourself instead:

```bash
docker build --target production -t iscc-hub .
```

### Generate credentials

A Hub needs two secrets. Generate them once and store them safely — both are **stable for the life of the Hub**:

```bash
# Ed25519 signing key (uses the iscc-crypto package)
uvx iscc-crypto keygen
# -> {"public_key": "z6Mk…", "secret_key": "z3u2…"}
#    ISCC_HUB_SECKEY = the secret_key (keep private)
#    the public_key is published at /.well-known/did.json and registered in the Hub-List

# Django secret key (any high-entropy string works)
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Required configuration

All six variables below are mandatory in the published image; the Hub fails fast at startup if any is missing.

| Variable            | Description                                                                                                          |
| ------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `DJANGO_DEBUG`      | Must be `false` in production.                                                                                       |
| `DJANGO_SECRET_KEY` | Random secret for Django session/CSRF signing.                                                                       |
| `ISCC_HUB_DOMAIN`   | Public hostname the Hub is served from (e.g. `hub.example.com`). Drives `ALLOWED_HOSTS`, CSRF, and the `did:web` id. |
| `ISCC_HUB_SECKEY`   | Ed25519 secret key (multibase `z3u2…`) from above. Signs receipts, the DID document, and log checkpoints.            |
| `ISCC_HUB_ID`       | Integer `0`–`4095`, unique per Hub on the network. Embedded in every ISCC-ID this Hub issues — immutable once live.  |
| `ISCC_HUB_REALM`    | `0` = testnet (sandbox network), `1` = mainnet (operational network).                                                |

See [Configuration reference](#configuration-reference) for the optional settings.

### Run with Docker

```bash
docker run -d --name iscc-hub \
    -e DJANGO_DEBUG=false \
    -e DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY" \
    -e ISCC_HUB_DOMAIN=hub.example.com \
    -e ISCC_HUB_SECKEY="$ISCC_HUB_SECKEY" \
    -e ISCC_HUB_ID=42 \
    -e ISCC_HUB_REALM=0 \
    -v iscc-hub-data:/app/data \
    -p 8000:8000 \
    ghcr.io/iscc/iscc-hub:0.3.0
```

The entrypoint applies database migrations, performs an initial Hub-List sync, then starts Gunicorn on port 8000.
`GET /health` reports readiness, and the image defines a Docker `HEALTHCHECK` against it.

### Run with Docker Compose

The bundled `compose.yaml` is for **local development only** (it builds the dev image with insecure defaults). For
production, use a compose file that pins a published image and supplies your own configuration:

```yaml
services:
  iscc-hub:
    image: ghcr.io/iscc/iscc-hub:0.3.0
    restart: unless-stopped
    ports:
      - 8000:8000
    volumes:
      - iscc-hub-data:/app/data
    environment:
      DJANGO_DEBUG: 'false'
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
      ISCC_HUB_DOMAIN: hub.example.com
      ISCC_HUB_SECKEY: ${ISCC_HUB_SECKEY}
      ISCC_HUB_ID: '42'
      ISCC_HUB_REALM: '0'
    healthcheck:
      test: [CMD, curl, -f, http://localhost:8000/health]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
volumes:
  iscc-hub-data:
```

Keep secrets in a `.env` file or your orchestrator's secret store, not committed in the compose file.

### Reverse proxy & TLS

The container serves plain HTTP on port 8000. Terminate TLS at a reverse proxy (nginx, Caddy, Traefik) in front of it
and forward the original `Host` header. When the public hostname differs from what Django sees, set:

- `DJANGO_ALLOWED_HOSTS` — comma-separated hostnames (defaults to `ISCC_HUB_DOMAIN`).
- `DJANGO_CSRF_TRUSTED_ORIGINS` — comma-separated origins including scheme (defaults to `https://${ISCC_HUB_DOMAIN}`).

The Hub serves its own static assets, so no separate static-file host is required.

### Persistence & backups

All durable state lives under `/app/data`: the SQLite database (`iscc-hub-<ID>.db` plus the `-wal` and `-shm` sidecar
files used in WAL mode) and any uploaded co-branding media. Mount it on a persistent volume and back it up regularly.
Because the Hub issues permanent, signed ISCC-IDs, losing this data means losing the log.

### Database backend

SQLite (the default) suits the Hub's single-writer workload and needs no extra services. To use PostgreSQL instead, set
`ISCC_HUB_DB_ENGINE=postgres` and the `ISCC_HUB_DB_*` connection variables (see
[Configuration reference](#configuration-reference)). SQLite and PostgreSQL are the only tested backends.

### Tuning the web server

The entrypoint runs Gunicorn with sync workers. Override via environment variables (defaults shown): `WORKERS=4`,
`THREADS=1`, `TIMEOUT=30`, `GRACEFUL_TIMEOUT=30`, `KEEP_ALIVE=5`, `MAX_REQUESTS=1000`, `MAX_REQUESTS_JITTER=50`,
`LOG_LEVEL=info`, `PORT=8000`. Writes are serialized by the sequencer (one logical writer per Hub), so additional
workers raise read concurrency rather than write throughput.

### Background jobs

The entrypoint runs two periodic loops in-process — no external scheduler is required: a Hub-List sync
(`ISCC_HUB_HUB_SYNC_INTERVAL`, default `3600` s) and a log-checkpoint refresh (`ISCC_HUB_CHECKPOINT_INTERVAL`, default
`86400` s). Set either to `0` to disable it; the checkpoint also rebuilds lazily on read, so disabling it is safe.

### Joining the Hub network

Each Hub announces itself through the **Hub-List**, a YAML file in this repository (`hubs/testnet.yaml` for realm 0,
`hubs/mainnet.yaml` for realm 1). Hubs fetch it from GitHub at startup and on the periodic sync, and use it to resolve
and forward ISCC-IDs that belong to other Hubs. To join, open a pull request adding your `hub_id`, public key (`z6Mk…`),
and `url`, choosing a `hub_id` not already taken in that file. Until your entry is merged, other Hubs cannot resolve the
IDs you issue.

### Operational constraints

- Run **one deployment per `ISCC_HUB_ID`**. Never point two Hubs at the same ID or run two databases under one ID — the
    ID is baked into every ISCC-ID issued.
- `ISCC_HUB_ID` and `ISCC_HUB_SECKEY` are **fixed for the life of the Hub**: IDs are issued forever, and the key
    verifies every receipt and checkpoint.
- Do **not** set `ENVIRONMENT=development` with the published image; that mode expects development tooling that
    production images omit.

## Configuration reference

The required variables are listed under [Deployment](#required-configuration). The most relevant optional variables are
below; `.env.example` documents the full set (including search-proxy tuning and HTML co-branding).

| Variable                               | Default            | Description                                                                   |
| -------------------------------------- | ------------------ | ----------------------------------------------------------------------------- |
| `DJANGO_ALLOWED_HOSTS`                 | `ISCC_HUB_DOMAIN`  | Comma-separated allowed hostnames.                                            |
| `DJANGO_CSRF_TRUSTED_ORIGINS`          | `https://$DOMAIN`  | Comma-separated CSRF-trusted origins (scheme + host).                         |
| `ISCC_HUB_DB_ENGINE`                   | `sqlite`           | Database backend: `sqlite` or `postgres`.                                     |
| `ISCC_HUB_DB_NAME`                     | `iscc-hub-<ID>.db` | SQLite database filename under `/app/data`.                                   |
| `ISCC_HUB_OPEN_ACCESS`                 | `true`             | `false` = permissioned mode: only registered public keys may declare.         |
| `ISCC_HUB_REQUIRE_CLIENT_TIMESTAMP`    | `false`            | `true` = reject declarations without a client-supplied timestamp.             |
| `ISCC_HUB_TIMESTAMP_TOLERANCE_SECONDS` | `600`              | Max deviation (s) for a provided timestamp; `<=0` disables the check.         |
| `ISCC_HUB_LIST_INITIAL_SYNC`           | `true`             | Sync the Hub-List from GitHub on startup.                                     |
| `ISCC_HUB_SEARCH_URLS`                 | _(unset)_          | Comma-separated iscc-search backends; unset disables `/search` (returns 404). |

The declaration-policy variables (`ISCC_HUB_OPEN_ACCESS`, `ISCC_HUB_REQUIRE_CLIENT_TIMESTAMP`,
`ISCC_HUB_TIMESTAMP_TOLERANCE_SECONDS`) are read on the declaration write path and are effectively set-once: changing
them requires a restart.

For PostgreSQL, set `ISCC_HUB_DB_HOST`, `ISCC_HUB_DB_PORT`, `ISCC_HUB_DB_USER`, `ISCC_HUB_DB_PASSWORD`, and
`ISCC_HUB_DB_NAME_PG` alongside `ISCC_HUB_DB_ENGINE=postgres`.

## Development

### Commands

```bash
# Code quality pipeline
uv run poe all              # Run complete pipeline
uv run poe check-python     # Lint with ruff
uv run poe format-python    # Format code
uv run poe check-types      # Type checking with pyright

# Testing
uv run pytest              # Run all tests
uv run pytest --no-cov     # Run without coverage
uv run pytest -k "test_sequencer"  # Run specific tests

# Database
uv run poe reset            # Reset dev database
uv run poe fixtures-load    # Load test data

# Schema generation
uv run poe build-schema     # Generate models from OpenAPI
```

### Testing

The project maintains 100% test coverage with comprehensive test suites:

- **Unit tests**: Isolated component testing
- **Integration tests**: Full API workflow testing
- **Property-based tests**: API contract validation with Schemathesis

### Testing against PostgreSQL

The sequencer is portable across the two tested backends and is verified on both SQLite (the default) and PostgreSQL.
MySQL and Oracle are not supported: the binary primary-key and unique columns would need per-field `db_type` overrides.
To run the suite against a local PostgreSQL:

```bash
# Start a throwaway PostgreSQL (host port 5433 avoids clashing with a local 5432 instance)
docker run -d --name iscc-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres \
    -e POSTGRES_DB=iscc_hub -p 5433:5432 postgres:16

# Run the suite against it (connection details come from ISCC_HUB_DB_* env vars)
ISCC_HUB_DB_HOST=127.0.0.1 ISCC_HUB_DB_PORT=5433 uv run poe test-postgres

# Tear it down
docker rm -f iscc-pg
```

`poe test-postgres` sets `ISCC_HUB_DB_ENGINE=postgres`; override `ISCC_HUB_DB_HOST`, `ISCC_HUB_DB_PORT`,
`ISCC_HUB_DB_USER`, `ISCC_HUB_DB_PASSWORD`, and `ISCC_HUB_DB_NAME_PG` as needed. Coverage is only gated on the SQLite
suite (`poe all`).

## Architecture

### Core Components

- **Sequencer** (`sequencer.py`): Atomic event logging with gapless sequence numbers
- **Validators** (`validators.py`): ISCC note and signature validation
- **Receipt Generator** (`receipt.py`): W3C Verifiable Credential creation
- **API** (`api.py`): Django Ninja REST endpoints with content negotiation

### Key Technical Details

- **SQLite WAL mode** with IMMEDIATE transactions for consistency
- **Custom fields**: `SequenceField` for gapless numbering, `IsccIDField` for binary storage
- **Timestamp precision**: Client milliseconds, hub microseconds for sequencing
- **Signature system**: Ed25519 with nonce-based replay prevention

## Protocol Overview

The ISCC Discovery Protocol implements a three-layer architecture:

1. **HUB**: Core timestamping and discovery network
2. **GATEWAY**: Routing and service discovery layer
3. **REGISTRY**: Metadata and service layer

See [ISCC Discovery Protocol](https://docs.google.com/document/d/1JdQrrBDfDPnQ08kM-onf4s0DwcntRLQVRBmbw1JImGo/) for
draft protocol concept.

## Related Projects

- [iscc-core](https://github.com/iscc/iscc-core): Reference ISCC implementation
- [iscc-crypto](https://github.com/iscc/iscc-crypto): Cryptographic primitives
- [iscc-sdk](https://github.com/iscc/iscc-sdk): High-level content processing

## Funding

This work was supported through the Open Science Clusters’ Action for Research and Society (OSCARS) European project
under grant agreement Nº101129751.

See:
[BIO-CODES](https://oscars-project.eu/projects/bio-codes-enhancing-ai-readiness-bioimaging-data-content-based-identifiers)
project (Enhancing AI-Readiness of Bioimaging Data with Content-Based Identifiers).

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run `uv run poe all` to ensure code quality
4. Submit a pull request with tests

All contributions must maintain 100% test coverage.
