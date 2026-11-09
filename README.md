# ISCC Hub

The reference implementation of the ISCC-HUB, a server that timestamps signed content declarations.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Django 6.1+](https://img.shields.io/badge/django-6.1+-green.svg)](https://www.djangoproject.com/)
[![Coverage 100%](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](#development)
[![Tests](https://github.com/iscc/iscc-hub/actions/workflows/test.yaml/badge.svg?branch=main)](https://github.com/iscc/iscc-hub/actions/workflows/test.yaml)

## Overview

An ISCC-HUB accepts signed ISCC declarations. It gives each declaration a unique ISCC-ID with a precise timestamp,
returns a signed receipt and writes the declaration to a public transparency log that anyone can verify. A hub resolves
its ISCC-IDs to the services of the declarer, and it can search for similar content by ISCC-CODE. Independent
organizations run hubs, and together they form the hub network.

The hub implements the [ISCC Discovery Protocol](https://ieps.iscc.codes/iep-0013/) (IEP-0013) and the
[ISCC Transparency Log](https://ieps.iscc.codes/iep-0014/) (IEP-0014).

## Documentation

The documentation is at **[hub.iscc.codes](https://hub.iscc.codes/)**:

- [How it works](https://hub.iscc.codes/how-it-works/): declarations, ISCC-IDs, the log and acceptance policies
- [Run a hub](https://hub.iscc.codes/run-a-hub/): deploy the container image with SQLite or PostgreSQL
- [Configuration](https://hub.iscc.codes/configuration/): all environment variables
- [Join the network](https://hub.iscc.codes/join-the-network/): add your hub to the hub list
- [Operations](https://hub.iscc.codes/operations/): backups, upgrades and monitoring
- [Use the API](https://hub.iscc.codes/use-the-api/): declare, resolve and search

Release images are at `ghcr.io/iscc/iscc-hub`. Pin an exact version, for example `ghcr.io/iscc/iscc-hub:0.1.2`.

## Development

```bash
git clone https://github.com/iscc/iscc-hub
cd iscc-hub
uv sync
uv run poe reset    # development database with migrations, demo user and fixtures
uv run poe dev      # development server on localhost:8000
```

Open http://localhost:8000 for the web interface and http://localhost:8000/docs for the API documentation. The admin
user is `demo` with the password `demo`. This setup uses insecure development defaults. Never use it in production.

```bash
uv run poe all            # format, lint, type check and test (100% coverage required)
uv run pytest -k "name"   # run selected tests
uv run poe build-schema   # regenerate iscc_hub/schema.py from iscc_hub/static/openapi.yaml
uv run poe docs-build     # build the documentation site into site/ (docs-serve serves it)
```

To run the test suite against PostgreSQL:

```bash
docker run -d --name iscc-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres \
    -e POSTGRES_DB=iscc_hub -p 5433:5432 postgres:16
ISCC_HUB_DB_HOST=127.0.0.1 ISCC_HUB_DB_PORT=5433 uv run poe test-postgres
docker rm -f iscc-pg
```

SQLite and PostgreSQL are the only supported databases. Coverage is gated on the SQLite suite.

Coding agents find the code map, invariants and task recipes in
[For coding agents](https://hub.iscc.codes/for-coding-agents/).

## Related projects

- [iscc-ieps](https://ieps.iscc.codes/): ISCC specifications, including the Discovery Protocol
- [iscc-core](https://github.com/iscc/iscc-core): reference ISCC implementation
- [iscc-crypto](https://github.com/iscc/iscc-crypto): Ed25519 keys and signatures
- [iscc-search](https://github.com/iscc/iscc-search): similarity search server
- [iscc-sdk](https://github.com/iscc/iscc-sdk): content processing and ISCC generation

## Funding

This work was supported through the Open Science Clusters’ Action for Research and Society (OSCARS) European project
under grant agreement Nº101129751.

See:
[BIO-CODES](https://oscars-project.eu/projects/bio-codes-enhancing-ai-readiness-bioimaging-data-content-based-identifiers)
project (Enhancing AI-Readiness of Bioimaging Data with Content-Based Identifiers).

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Run `uv run poe all`. All contributions must keep 100% test coverage.
4. Open a pull request with tests.
