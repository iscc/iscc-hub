"""Tests for GET /{iscc_id} resolve endpoint."""

import pytest

from iscc_hub.models import Hub
from tests.conftest import create_test_declaration, generate_test_iscc_id


@pytest.mark.django_db
def test_resolve_valid_iscc_id(api_client):
    """Test resolving a valid local ISCC-ID returns declaration JSON."""
    iscc_id = generate_test_iscc_id(hub_id=1, seq=1)
    decl = create_test_declaration(seq=1, iscc_id=iscc_id)

    response = api_client.get(f"/{iscc_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["iscc_id"] == str(decl.iscc_id)
    assert data["iscc_code"] == decl.iscc_code
    assert data["datahash"] == decl.datahash
    assert data["pubkey"] == decl.pubkey
    assert "timestamp" in data


@pytest.mark.django_db
def test_resolve_invalid_format(api_client):
    """Test resolving an invalid ISCC-ID returns 404."""
    response = api_client.get("/INVALID-ID")

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "Invalid ISCC-ID" in data["error"]["message"]


@pytest.mark.django_db
def test_resolve_not_found(api_client):
    """Test resolving a non-existent ISCC-ID returns 404."""
    iscc_id = generate_test_iscc_id(hub_id=1, seq=999)

    response = api_client.get(f"/{iscc_id}")

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "Declaration not found" in data["error"]["message"]


@pytest.mark.django_db
def test_resolve_redacted_declaration(api_client):
    """Test resolving a redacted declaration returns 404."""
    iscc_id = generate_test_iscc_id(hub_id=1, seq=1)
    create_test_declaration(seq=1, iscc_id=iscc_id, redacted=True)

    response = api_client.get(f"/{iscc_id}")

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "Declaration not found" in data["error"]["message"]


@pytest.mark.django_db
def test_resolve_remote_hub_known(api_client):
    """Test resolving an ISCC-ID from a known remote hub returns 404 with hub URL."""
    remote_iscc_id = generate_test_iscc_id(hub_id=42, seq=1)
    Hub.objects.create(
        hub_id=42,
        pubkey="z6MknNWEmX1zYYZbCCjWGYja9gZA64AKrKNLtsdP2g5EkFrB",
        url="https://remote-hub.example.com",
        active=True,
    )

    response = api_client.get(f"/{remote_iscc_id}")

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "remote hub" in data["error"]["message"]
    assert "https://remote-hub.example.com" in data["error"]["message"]


@pytest.mark.django_db
def test_resolve_remote_hub_unknown(api_client):
    """Test resolving an ISCC-ID from an unknown remote hub returns 404."""
    remote_iscc_id = generate_test_iscc_id(hub_id=99, seq=1)

    response = api_client.get(f"/{remote_iscc_id}")

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "unknown remote hub" in data["error"]["message"]


@pytest.mark.django_db
def test_resolve_omits_empty_optional_fields(api_client):
    """Test resolve omits controller, gateway, metahash when empty/null."""
    iscc_id = generate_test_iscc_id(hub_id=1, seq=1)
    create_test_declaration(seq=1, iscc_id=iscc_id, controller="", gateway="", metahash=None)

    response = api_client.get(f"/{iscc_id}")

    assert response.status_code == 200
    data = response.json()
    assert "iscc_id" in data
    assert "iscc_code" in data
    assert "datahash" in data
    assert "timestamp" in data
    assert "pubkey" in data
    assert "controller" not in data
    assert "gateway" not in data
    assert "metahash" not in data


@pytest.mark.django_db
def test_resolve_includes_optional_fields(api_client):
    """Test resolve includes controller, gateway, metahash when present."""
    iscc_id = generate_test_iscc_id(hub_id=1, seq=1)
    create_test_declaration(
        seq=1,
        iscc_id=iscc_id,
        controller="did:web:example.com",
        gateway="https://example.com/metadata/{iscc_id}",
        metahash="1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598",
    )

    response = api_client.get(f"/{iscc_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["controller"] == "did:web:example.com"
    assert "gateway" in data
    assert "{iscc_id}" not in data["gateway"]  # Template should be expanded
    assert data["metahash"] == "1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598"


@pytest.mark.django_db
def test_resolve_valid_iscc_but_not_id(api_client):
    """Test resolving a valid ISCC-CODE (not ISCC-ID) returns 404."""
    iscc_code = "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY"

    response = api_client.get(f"/{iscc_code}")

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "Invalid ISCC-ID" in data["error"]["message"]


@pytest.mark.django_db
def test_resolve_returns_single_dict_not_list(api_client):
    """Test resolve returns a single dict, not a list."""
    iscc_id = generate_test_iscc_id(hub_id=1, seq=1)
    create_test_declaration(seq=1, iscc_id=iscc_id)

    response = api_client.get(f"/{iscc_id}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "iscc_id" in data
