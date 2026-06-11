"""
Tests for the /lookup exact-match endpoint.
"""

import os

import iscc_crypto as icr
import pytest

from iscc_hub.sequencer import sequence_iscc_note
from tests.conftest import create_iscc_from_text, create_test_declaration, generate_test_iscc_id


@pytest.mark.django_db
def test_lookup_by_datahash_single_result(api_client):
    """Test lookup by datahash returns single declaration."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    decl = create_test_declaration(seq=1, datahash=datahash)

    response = api_client.get(f"/lookup?datahash={datahash}")

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
def test_lookup_by_datahash_multiple_results(api_client):
    """Test lookup by datahash returns multiple declarations with same datahash."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    decl1 = create_test_declaration(seq=1, datahash=datahash)
    decl2 = create_test_declaration(seq=2, datahash=datahash)

    response = api_client.get(f"/lookup?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    iscc_ids = {d["iscc_id"] for d in data}
    assert str(decl1.iscc_id) in iscc_ids
    assert str(decl2.iscc_id) in iscc_ids


@pytest.mark.django_db
def test_lookup_by_iscc_code(api_client):
    """Test lookup by ISCC-CODE."""
    iscc_code = "ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY"
    decl = create_test_declaration(seq=1, iscc_code=iscc_code)

    response = api_client.get(f"/lookup?iscc_code={iscc_code}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["iscc_id"] == str(decl.iscc_id)
    assert data[0]["iscc_code"] == iscc_code


@pytest.mark.django_db
def test_lookup_no_results(api_client):
    """Test lookup returns empty array when no results found."""
    response = api_client.get("/lookup?datahash=1e20aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.django_db
def test_lookup_excludes_redacted_declarations(api_client):
    """Test lookup excludes redacted declarations."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    create_test_declaration(seq=1, datahash=datahash, redacted=True)

    response = api_client.get(f"/lookup?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


@pytest.mark.django_db
def test_lookup_error_no_parameters(api_client):
    """Test lookup returns 400 when no parameters provided."""
    response = api_client.get("/lookup")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Exactly one search parameter required" in data["error"]["message"]


@pytest.mark.django_db
def test_lookup_error_both_parameters(api_client):
    """Test lookup returns 400 when both parameters provided."""
    response = api_client.get(
        "/lookup?datahash=1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
        "&iscc_code=ISCC:KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY"
    )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Only one search parameter allowed" in data["error"]["message"]


@pytest.mark.django_db
def test_lookup_error_invalid_datahash_format(api_client):
    """Test lookup returns 400 for invalid datahash format."""
    response = api_client.get("/lookup?datahash=invalid-hash")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid datahash format" in data["error"]["message"]


@pytest.mark.django_db
def test_lookup_error_invalid_iscc_code_format(api_client):
    """Test lookup returns 400 for invalid ISCC-CODE format."""
    response = api_client.get("/lookup?iscc_code=INVALID:CODE")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid iscc_code format" in data["error"]["message"]


@pytest.mark.django_db
def test_lookup_omits_empty_optional_fields(api_client):
    """Test lookup omits controller, gateway, metahash when empty/null."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    create_test_declaration(seq=1, datahash=datahash, controller="", gateway="", metahash=None)

    response = api_client.get(f"/lookup?datahash={datahash}")

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
def test_lookup_includes_non_empty_optional_fields(api_client):
    """Test lookup includes controller, gateway, metahash when present."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    create_test_declaration(
        seq=1,
        datahash=datahash,
        controller="did:web:example.com",
        gateway="https://example.com/metadata/{iscc_id}",
        metahash="1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598",
    )

    response = api_client.get(f"/lookup?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # Optional fields should be present when non-empty
    assert data[0]["controller"] == "did:web:example.com"
    assert "gateway" in data[0]
    assert data[0]["metahash"] == "1e202335f74fc18e2f4f99f0ea6291de5803e579a2219e1b4a18004fc9890b94e598"


@pytest.mark.django_db
def test_lookup_expands_gateway_url_template(api_client):
    """Test lookup expands gateway URL template with the lowercase URI-form ISCC-ID body, prefix stripped."""
    datahash = "1e203b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c"
    iscc_id = generate_test_iscc_id(seq=1)
    create_test_declaration(
        seq=1,
        iscc_id=iscc_id,
        datahash=datahash,
        gateway="https://example.com/metadata/{iscc_id}",
    )

    response = api_client.get(f"/lookup?datahash={datahash}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    # Gateway expands to the lowercase URI-form base32 body with the ISCC: prefix stripped
    gateway = data[0]["gateway"]
    assert gateway == f"https://example.com/metadata/{iscc_id.removeprefix('ISCC:').lower()}"


@pytest.mark.django_db
def test_lookup_datahash_wrong_length(api_client):
    """Test lookup with datahash of wrong length returns 400."""
    # Too short
    response = api_client.get("/lookup?datahash=1e203b49776")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid datahash format" in data["error"]["message"]


@pytest.mark.django_db
def test_lookup_datahash_wrong_prefix(api_client):
    """Test lookup with datahash without correct prefix returns 400."""
    # Missing 1e20 prefix
    response = api_client.get("/lookup?datahash=ffff3b49776cc59dc94dc1ce328e6c4a5777c7816ebf1e10e87ac3cb061ce1037c6c")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid datahash format" in data["error"]["message"]


@pytest.mark.django_db
def test_lookup_iscc_code_missing_prefix(api_client):
    """Test lookup with ISCC-CODE missing prefix returns 400."""
    response = api_client.get("/lookup?iscc_code=KACYPXW445FTYNJ3CYSXHAFJMA2HUWULUNRFE3BLHRSCXYH2M5AEGQY")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "Invalid iscc_code format" in data["error"]["message"]


@pytest.mark.django_db
def test_lookup_error_empty_datahash(api_client):
    """Test lookup returns 400 when datahash parameter is empty."""
    response = api_client.get("/lookup?datahash=")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "datahash parameter cannot be empty" in data["error"]["message"]


@pytest.mark.django_db
def test_lookup_error_empty_iscc_code(api_client):
    """Test lookup returns 400 when iscc_code parameter is empty."""
    response = api_client.get("/lookup?iscc_code=")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "iscc_code parameter cannot be empty" in data["error"]["message"]


@pytest.mark.django_db(transaction=True)
def test_lookup_by_datahash_after_sequencer(api_client):
    """Test that declarations created via the sequencer are findable by datahash lookup.

    The sequencer uses raw SQL to insert declarations. This test verifies that
    the datahash is stored as binary (BLOB) so that HexField filtering works.
    """
    iscc_data = create_iscc_from_text("Searchable content")
    nonce_bytes = os.urandom(16)
    nonce_bytes = bytes([0x00, 0x10]) + nonce_bytes[2:]
    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": nonce_bytes.hex(),
        "timestamp": "2025-01-15T12:00:00.000Z",
    }
    keypair = icr.key_generate(controller="did:web:example.com")
    signed_note = icr.sign_json(note, keypair)
    seq, iscc_id_bytes = sequence_iscc_note(signed_note)

    response = api_client.get(f"/lookup?datahash={iscc_data['datahash']}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["datahash"] == iscc_data["datahash"]


@pytest.mark.django_db(transaction=True)
def test_lookup_by_iscc_code_after_sequencer(api_client):
    """Test that declarations created via the sequencer are findable by iscc_code lookup."""
    iscc_data = create_iscc_from_text("Another searchable content")
    nonce_bytes = os.urandom(16)
    nonce_bytes = bytes([0x00, 0x10]) + nonce_bytes[2:]
    note = {
        "iscc_code": iscc_data["iscc"],
        "datahash": iscc_data["datahash"],
        "nonce": nonce_bytes.hex(),
        "timestamp": "2025-01-15T12:00:00.000Z",
    }
    keypair = icr.key_generate(controller="did:web:example.com")
    signed_note = icr.sign_json(note, keypair)
    seq, iscc_id_bytes = sequence_iscc_note(signed_note)

    response = api_client.get(f"/lookup?iscc_code={iscc_data['iscc']}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["iscc_code"] == iscc_data["iscc"]
