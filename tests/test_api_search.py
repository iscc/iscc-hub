"""
Tests for /search endpoint.
"""

import pytest

from tests.conftest import create_test_declaration, generate_test_iscc_id


@pytest.mark.django_db
def test_search_by_datahash_single_result(api_client):
    """Test search by datahash returns single declaration."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    decl = create_test_declaration(seq=1, datahash=datahash)

    response = api_client.get(f"/search?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["iscc_id"] == str(decl.iscc_id)
    assert data[0]["datahash"] == datahash
    assert data[0]["iscc_code"] == decl.iscc_code
    assert data[0]["pubkey"] == decl.pubkey
    assert "timestamp" in data[0]


@pytest.mark.django_db
def test_search_by_datahash_multiple_results(api_client):
    """Test search by datahash returns multiple declarations with same datahash."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    decl1 = create_test_declaration(seq=1, datahash=datahash)
    decl2 = create_test_declaration(seq=2, datahash=datahash)

    response = api_client.get(f"/search?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    iscc_ids = {d["iscc_id"] for d in data}
    assert str(decl1.iscc_id) in iscc_ids
    assert str(decl2.iscc_id) in iscc_ids


@pytest.mark.django_db
def test_search_by_iscc_code(api_client):
    """Test search by ISCC-CODE."""
    iscc_code = "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY"
    decl = create_test_declaration(seq=1, iscc_code=iscc_code)

    response = api_client.get(f"/search?iscc_code={iscc_code}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["iscc_id"] == str(decl.iscc_id)
    assert data[0]["iscc_code"] == iscc_code


@pytest.mark.django_db
def test_search_no_results(api_client):
    """Test search returns empty array when no results found."""
    response = api_client.get("/search?datahash=1e20aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.django_db
def test_search_excludes_redacted_declarations(api_client):
    """Test search excludes redacted declarations."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    create_test_declaration(seq=1, datahash=datahash, redacted=True)

    response = api_client.get(f"/search?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


@pytest.mark.django_db
def test_search_error_no_parameters(api_client):
    """Test search returns 400 when no parameters provided."""
    response = api_client.get("/search")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Exactly one search parameter required" in data["error"]["message"]


@pytest.mark.django_db
def test_search_error_both_parameters(api_client):
    """Test search returns 400 when both parameters provided."""
    response = api_client.get(
        "/search?datahash=1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
        "&iscc_code=ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY"
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Only one search parameter allowed" in data["error"]["message"]


@pytest.mark.django_db
def test_search_error_invalid_datahash_format(api_client):
    """Test search returns 400 for invalid datahash format."""
    response = api_client.get("/search?datahash=invalid-hash")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid datahash format" in data["error"]["message"]


@pytest.mark.django_db
def test_search_error_invalid_iscc_code_format(api_client):
    """Test search returns 400 for invalid ISCC-CODE format."""
    response = api_client.get("/search?iscc_code=INVALID:CODE")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid iscc_code format" in data["error"]["message"]


@pytest.mark.django_db
def test_search_omits_empty_optional_fields(api_client):
    """Test search omits controller, gateway, metahash when empty/null."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    create_test_declaration(seq=1, datahash=datahash, controller="", gateway="", metahash=None)

    response = api_client.get(f"/search?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # Required fields should be present
    assert "iscc_id" in data[0]
    assert "iscc_code" in data[0]
    assert "datahash" in data[0]
    assert "timestamp" in data[0]
    assert "pubkey" in data[0]
    # Optional fields should be omitted when empty
    assert "controller" not in data[0]
    assert "gateway" not in data[0]
    assert "metahash" not in data[0]


@pytest.mark.django_db
def test_search_includes_non_empty_optional_fields(api_client):
    """Test search includes controller, gateway, metahash when present."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    create_test_declaration(
        seq=1,
        datahash=datahash,
        controller="did:web:example.com",
        gateway="https://example.com/metadata/{iscc_id}",
        metahash="1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598",
    )

    response = api_client.get(f"/search?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # Optional fields should be present when non-empty
    assert data[0]["controller"] == "did:web:example.com"
    assert "gateway" in data[0]
    assert data[0]["metahash"] == "1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598"


@pytest.mark.django_db
def test_search_expands_gateway_url_template(api_client):
    """Test search expands gateway URL template with lowercase ISCC-ID without prefix."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    iscc_id = generate_test_iscc_id(seq=1)
    create_test_declaration(
        seq=1,
        iscc_id=iscc_id,
        datahash=datahash,
        gateway="https://example.com/metadata/{iscc_id}",
    )

    response = api_client.get(f"/search?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # Gateway should be expanded with lowercase iscc_id without prefix
    gateway = data[0]["gateway"]
    assert "https://example.com/metadata/" in gateway
    assert "{iscc_id}" not in gateway  # Template should be expanded
    # Extract the iscc_id part from the gateway URL
    iscc_id_from_url = gateway.split("/metadata/")[1]
    assert iscc_id_from_url.islower()  # Should be lowercase
    assert not iscc_id_from_url.startswith("iscc:")  # Should not have prefix


@pytest.mark.django_db
def test_search_datahash_wrong_length(api_client):
    """Test search with datahash of wrong length returns 400."""
    # Too short
    response = api_client.get("/search?datahash=1e203b49776")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid datahash format" in data["error"]["message"]


@pytest.mark.django_db
def test_search_datahash_wrong_prefix(api_client):
    """Test search with datahash without correct prefix returns 400."""
    # Missing 1e20 prefix
    response = api_client.get("/search?datahash=ffff3b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid datahash format" in data["error"]["message"]


@pytest.mark.django_db
def test_search_iscc_code_missing_prefix(api_client):
    """Test search with ISCC-CODE missing prefix returns 400."""
    response = api_client.get("/search?iscc_code=KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid iscc_code format" in data["error"]["message"]


@pytest.mark.django_db
def test_search_error_empty_datahash(api_client):
    """Test search returns 400 when datahash parameter is empty."""
    response = api_client.get("/search?datahash=")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "datahash parameter cannot be empty" in data["error"]["message"]


@pytest.mark.django_db
def test_search_error_empty_iscc_code(api_client):
    """Test search returns 400 when iscc_code parameter is empty."""
    response = api_client.get("/search?iscc_code=")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "iscc_code parameter cannot be empty" in data["error"]["message"]
