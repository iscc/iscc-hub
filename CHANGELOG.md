# Changelog

All notable changes to iscc-hub. Release images are at `ghcr.io/iscc/iscc-hub:<version>`. The
[documentation](https://hub.iscc.codes/) describes how to run and upgrade a hub.

## 0.1.2

### Fixed

- The API docs page at `/docs` stayed blank since Redoc 3 was released. It now loads a pinned Redoc 2 version.

## 0.1.1

First versioned release. Hubs that run the `dev` image (version 0.1.0) should move to this release. Existing databases
and logs work unchanged: all entries in the logs of the public hubs pass the stricter checks of this release.

### Upgrade notes

- The hub does not start if `ISCC_HUB_SECKEY` is not a valid Ed25519 secret key. Before, it started and reported
  healthy, but failed on every receipt, checkpoint and DID document.
- The image health check sends the hub domain as `Host` header. If you added `localhost` or `127.0.0.1` to
  `DJANGO_ALLOWED_HOSTS` only for the health check, you can remove them.
- ISCC-UNITs shorter than 256 bits are always rejected. `ISCC_HUB_REQUIRE_FULL_UNITS` now only controls whether a
  declaration must include `units`.
- The first start applies migration `0002`. It changes only a help text and runs no SQL.
- The image runs Python 3.14. Installations outside the image need Python 3.12 or later and Django 6.1 or later.
- For a mainnet hub on SQLite, set `ISCC_HUB_SQLITE_SYNC_MODE=FULL`. See
  [Configuration](https://hub.iscc.codes/configuration/).

### Changed

- Declarations and deletions get stricter validation of timestamps, signature fields, ISCC-UNITs and ISCC-IDs.
  Requests that the public hubs received from real clients pass these checks.
- A malformed `proof` or `pubkey` in a signature gets a specific error message. Status and error code are unchanged.
- The admin interface shows hubs as view-only pages. The hub list download sets all their fields.

### Fixed

- Admin: saving a declaration changes only its redaction flag. A save from a page that was open during a signed deletion
  could bring the deleted declaration back into the hub's view. The log was never affected.
- Admin: searching declarations by ISCC-ID gave HTTP 500 on SQLite and PostgreSQL.
- Docker: the image health check failed with the default `DJANGO_ALLOWED_HOSTS`.
- The first start no longer prints the admin password to the container log.

### Added

- Documentation site at [hub.iscc.codes](https://hub.iscc.codes/), with guides to run a hub on SQLite or PostgreSQL,
  join the network, operate a hub and use the API.
- `.env.example` lists all settings with their defaults.
- Release pipeline: a version tag runs the full test suite, and the image is published only after its smoke test
  passes. Release candidates get only their exact image tag.

### Dependencies

- All dependencies updated, including Django 6.1.
- Base image Python 3.14 and uv, both pinned by digest.

### Known issues

- Two deletions of the same declaration at the same time can both be written to the log. Only the key that made the
  declaration can send deletions.
- Resolve and receipt requests accept some non-canonical ISCC-ID spellings, including ISCC-IDs of another realm.
- Some malformed requests get HTTP 500 instead of a 4xx response. They do not change the log.
- The admin search by public key, data hash or nonce finds nothing.
