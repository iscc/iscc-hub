---
icon: lucide/bot
description: Dense reference for coding agents that change iscc-hub or integrate with a hub
---

# For Coding Agents

Reference for AI agents that work on iscc-hub or call a hub. Tables and rules first. The code is the source of truth;
the [IEPs](https://ieps.iscc.codes/) define the protocol.

## Architecture map

Django 6.1 + django-ninja, Python 3.12+. One process type: Gunicorn sync workers. SQLite (WAL) by default, PostgreSQL
optional.

| File                          | Contents                                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `iscc_hub/api.py`             | Ninja endpoints: `/declaration`, receipt, delete, `/lookup`, `/search`, `/health`, DID document, JSON resolve |
| `iscc_hub/validators.py`      | All write-path validation of `IsccNote` and `IsccNoteDelete`. Pure, no I/O                                    |
| `iscc_hub/identity.py`        | DID verification: fetches and checks the `did:web` document of the controller (SSRF-guarded, cached per worker)       |
| `iscc_hub/sequencer.py`       | Single-writer transaction: ISCC-ID, log record and view row in one commit                                     |
| `iscc_hub/iscc_id.py`         | `IsccID`: 52-bit µs timestamp + 12-bit hub ID; header from `ISCC_HUB_REALM`                                   |
| `iscc_hub/receipt.py`         | Builds the `IsccReceipt` (W3C VC) signed with `ISCC_HUB_SECKEY`                                               |
| `iscc_hub/merkle.py`          | RFC 6962 / tlog-tiles primitives. Pure                                                                        |
| `iscc_hub/checkpoint_note.py` | C2SP signed-note checkpoint codec. Pure, byte-exact with the Go reference                                     |
| `iscc_hub/log_tree.py`        | Live tree over `LogRecord`, checkpoint cache                                                                  |
| `iscc_hub/log_api.py`         | `/log/checkpoint`, `/log/tile/...` plain Django views                                                         |
| `iscc_hub/search_proxy.py`    | `/search` proxy to iscc-search servers: failover, circuit breaker                                             |
| `iscc_hub/rerank.py`          | Tiered Semantic Ranking of search results                                                                     |
| `iscc_hub/middleware.py`      | Routes a request to the API, log or HTML URL configuration                                                    |
| `iscc_hub/views.py`           | HTML pages: home page, resolve, health                                                                        |
| `iscc_hub/admin.py`           | Admin: redaction flag, public keys. No add, change or delete of declarations                                  |
| `iscc_hub/tasks.py`           | Hub list download from GitHub (`hubs/testnet.yaml`, `hubs/mainnet.yaml` on `main`)                            |
| `iscc_hub/models.py`          | `User`, `Hub`, `PubKey`, `IsccDeclaration` (view), `LogState`, `LogRecord` (log)                              |
| `iscc_hub/fields.py`          | `IsccIDField` (8-byte binary), `HexField`, `PubkeyField`                                                      |
| `iscc_hub/schema.py`          | Generated from `iscc_hub/static/openapi.yaml`. Never edit by hand                                             |
| `iscc_hub/settings.py`        | All environment variables (see [Configuration](configuration.md))                                             |
| `scripts/entrypoint.sh`       | Container start: migrate, admin user, hub list sync, background loops, Gunicorn                               |
| `hubs/*.yaml`                 | Hub lists. Hubs download them from the `main` branch                                                          |
| `specs/`                      | Older protocol drafts. The IEPs are authoritative                                                             |

Request flow for `POST /declaration`: `middleware` → `api.declaration` → `validators.validate_iscc_note` → permission
check (`PubKey`) → `identity` (DID verification) → `sequencer.sequence_iscc_note` → 201 `{iscc_id, seq}`.

## Decision dispatch

| Task                                | Where                                                                                        |
| ----------------------------------- | -------------------------------------------------------------------------------------------- |
| Add or change a validation rule     | `validators.py`, plus tests in `tests/test_validators.py` or `tests/test_write_hardening.py` |
| Change an API request or response   | `iscc_hub/static/openapi.yaml` and `static/schemas/*.yaml`, then `uv run poe build-schema`   |
| Add a setting                       | `settings.py` with a default, `.env.example`, `docs/configuration.md`                        |
| Change an HTML page                 | `iscc_hub/templates/`, `views.py`                                                            |
| Change the log or checkpoint format | Stop. Load-bearing. Discuss first                                                            |
| Change the hub list                 | `hubs/*.yaml` on `main`                                                                      |

## Constraints and invariants

| Invariant            | Rule                                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------------------- |
| Atomic issuance      | ISCC-ID, `LogRecord` and `IsccDeclaration` row are written in one transaction. Never split it           |
| Gapless sequence     | `LogRecord.index` starts at 0 and has no gaps                                                           |
| Monotonic timestamps | Each ISCC-ID of a hub has a strictly greater timestamp                                                  |
| Single writer        | SQLite `BEGIN IMMEDIATE` (`transaction_mode=IMMEDIATE`); PostgreSQL row lock on `LogState`              |
| Append-only log      | Nothing updates or deletes a `LogRecord`. Deletion appends a deletion record                            |
| Log entry envelope   | `{"$schema", "iscc_id", "note"}`, JCS-canonical, framed `[u16 BE length][record]` in tlog-tiles bundles |
| Signature scope      | JCS (RFC 8785) of the note without `signature.proof`. Byte-exact                                        |
| `IsccDeclaration`    | A view of current state, rebuilt from the log. Admin saves change only `redacted`                       |
| Nonce                | 32 hex chars; first 12 bits = `ISCC_HUB_ID`; unique per hub                                             |
| Request size         | Body at most 8192 bytes                                                                                 |
| ISCC-UNITs           | Each passes `iscc_core.iscc_validate(strict=True)` and has a 256-bit body                               |
| ISCC-ID on deletion  | Must be the canonical string for the realm of the hub                                                   |
| Fixed per hub        | `ISCC_HUB_ID`, `ISCC_HUB_REALM`, `ISCC_HUB_SECKEY`, `ISCC_HUB_DOMAIN`                                   |

Load-bearing (never change without discussion): entry bundle framing, log entry envelope, checkpoint format, RFC 6962
hashing and height-8 tiles, `/log/` paths, ISCC-ID encoding, signature scope and JCS.

## Side effects

| Call                            | Writes                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------- |
| `POST /declaration`             | One `LogRecord` (declaration), one `IsccDeclaration`, `LogState` update         |
| `DELETE /declaration/{iscc_id}` | One `LogRecord` (deletion), removes the `IsccDeclaration` row                   |
| Admin redact or unredact        | `IsccDeclaration.redacted` only                                                 |
| `GET /log/checkpoint`           | May rebuild the cached checkpoint                                               |
| DID verification                | Outbound HTTPS GET of `https://<domain>/.well-known/did.json`; per-worker cache |
| `sync_hubs` command             | Creates or updates `Hub` rows from the hub list; never deletes rows             |

## Task recipes

```bash
uv sync                                   # install
uv run poe all                            # format, lint, types, tests (100% coverage required)
uv run pytest tests/test_x.py --no-cov    # one test file
uv run pytest -m slow                     # slow tests (Go conformance, fuzzing)
uv run poe build-schema                   # regenerate schema.py from openapi.yaml
uv run poe docs-build && uv run poe docs-check   # build and check this site
```

Tests that touch the sequencer or the API use `@pytest.mark.django_db(transaction=True)`. Without `transaction=True`,
pytest-django wraps the test in a transaction and `BEGIN IMMEDIATE` fails.

Sign a note in a client:

```python
import iscc_crypto as icr

key = icr.key_from_secret(secret, controller="did:web:example.com")
note = {
    "$schema": "http://purl.org/iscc/schema/iscc-note-0.8.0.json",
    "iscc_code": code,
    "datahash": datahash,
    "nonce": icr.create_nonce(hub_id),
    "units": units,
}
signed = icr.sign_json(note, key)  # POST as JSON to /declaration
```

A full, tested client example is on [Use the API](use-the-api.md#example).

## Change playbook

| If you change                       | Also update                                                                                            |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `openapi.yaml` or `static/schemas/` | `uv run poe build-schema`; `docs/use-the-api.md`                                                       |
| A setting or its default            | `.env.example`, `docs/configuration.md`, this page                                                     |
| A validation rule                   | Tests; `docs/use-the-api.md` rules table; replay the public logs to check that real clients still pass |
| `scripts/entrypoint.sh`             | `docs/run-a-hub.md` start steps, `docs/configuration.md` background jobs                               |
| A dependency floor                  | `pyproject.toml`, then `uv lock`; CI uses `uv sync --locked`                                           |
| The version                         | `pyproject.toml` and `iscc_hub/__init__.py`; image tags in `docs/run-a-hub.md`                         |

## Common mistakes

**NEVER** edit `iscc_hub/schema.py`. **ALWAYS** change `openapi.yaml` and run `uv run poe build-schema`.

---

**NEVER** call `obj.save()` on an `IsccDeclaration` from code that can run during a deletion. A stale save inserts the
row again. **ALWAYS** use `filter(pk=...).update(...)`.

---

**NEVER** use `@pytest.mark.django_db` without `transaction=True` for sequencer or API tests.

---

**NEVER** write tests with mocks for crypto. **ALWAYS** use real Ed25519 keys and the fixtures in `tests/conftest.py`.

---

**NEVER** treat `specs/` as authoritative. **ALWAYS** check the [IEPs](https://ieps.iscc.codes/) and the code.

---

**NEVER** send a resolve request without `Accept: application/json` if you want JSON. Without it, `GET /{iscc_id}`
returns HTML or a redirect.
