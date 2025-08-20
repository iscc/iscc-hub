# ISCC Hub

A Django-based timestamping service implementing the
[ISCC Discovery Protocol](docs/specification.md) for signed content declarations.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Django 5.2+](https://img.shields.io/badge/django-5.2+-green.svg)](https://www.djangoproject.com/)
[![Coverage 100%](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](#testing)
[![Tests](https://github.com/iscc/iscc-hub/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/iscc/iscc-hub/actions/workflows/test.yml)

## Overview

ISCC-HUBs accept cryptographically signed ISCC declarations, assign globally unique ISCC-IDs with
precise timestamps, and issue verifiable credentials of ISCC-ID ownership. They also resolve
ISCC-IDs to owner-controlled metdata and service endpoints and support interoperable cross-registry
search and discovery by ISCC-CODEs.

**Key Features:**

- Atomic sequencing with gapless numbering and microsecond timestamps
- Ed25519 signature validation with replay attack prevention
- W3C Verifiable Credentials for tamper-proof receipts
- REST API with OpenAPI documentation
- 100% test coverage with property-based testing

## Quick Start

```bash
# Clone and setup
git clone https://github.com/iscc/iscc-hub
cd iscc-hub
uv sync

# Initialize development environment
uv run poe reset

# Start development server
uv run poe serve
```

Visit http://localhost:8000 for the web interface or http://localhost:8000/docs for API
documentation.

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

See [specification.md](docs/specification.md) for draft protocol details.

## Related Projects

- [iscc-core](https://github.com/iscc/iscc-core): Reference ISCC implementation
- [iscc-crypto](https://github.com/iscc/iscc-crypto): Cryptographic primitives
- [iscc-sdk](https://github.com/iscc/iscc-sdk): High-level content processing

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run `uv run poe all` to ensure code quality
4. Submit a pull request with tests

All contributions must maintain 100% test coverage.
