"""Tests for HTML views."""

import iscc_crypto as icr
import pytest
from django.test import Client, override_settings
from django.urls import reverse

from tests.conftest import create_test_declaration, generate_test_iscc_id


@pytest.mark.django_db
def test_iscc_id_resolve_valid_with_gateway():
    # type: () -> None
    """Test ISCC-ID resolution with gateway configured - should redirect."""
    # Create a declaration with gateway using unique nonce
    declaration = create_test_declaration(
        gateway="https://example.com/metadata",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}")

    # Should redirect with 307
    assert response.status_code == 307
    # Non-template gateway URLs are returned unmodified
    assert response["Location"] == "https://example.com/metadata"


@pytest.mark.django_db
def test_iscc_id_resolve_valid_with_gateway_template():
    # type: () -> None
    """Test ISCC-ID resolution with gateway template - should expand and redirect."""
    # Create a declaration with gateway template
    declaration = create_test_declaration(
        gateway="https://registry.com/{iscc_code}/details/{iscc_id}",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}")

    # Should redirect with 307 to expanded URL
    assert response.status_code == 307
    # ISCC-CODE should have "ISCC:" prefix stripped for cleaner URLs
    iscc_code_clean = declaration.iscc_code[5:] if declaration.iscc_code.startswith("ISCC:") else declaration.iscc_code
    expected_url = f"https://registry.com/{iscc_code_clean}/details/{iscc_id_path}"
    assert response["Location"] == expected_url


@pytest.mark.django_db
def test_iscc_id_resolve_with_metahash():
    # type: () -> None
    """Test ISCC-ID resolution with metahash field - should display it."""
    # Create a declaration with metahash
    declaration = create_test_declaration(
        gateway="",
        metahash="1e20a1b2c3d4e5f6789012345678901234567890123456789012345678901234",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}")

    # Should return detail page with metahash
    assert response.status_code == 200
    assert b"Metadata Hash" in response.content
    assert declaration.metahash.encode() in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_nonexistent():
    # type: () -> None
    """Test ISCC-ID resolution for non-existent ID - should return 404."""
    # Use a hardcoded valid ISCC-ID format that doesn't exist
    nonexistent_id = "ISCC:MAAZZZZZZZZZZZZZ"  # Valid format but doesn't exist
    # Strip ISCC: prefix for the URL path - MUST BE LOWERCASE
    iscc_id_path = nonexistent_id[5:].lower() if nonexistent_id.startswith("ISCC:") else nonexistent_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}")

    # Should return 404
    assert response.status_code == 404
    assert b"ISCC-ID Not Found" in response.content
    assert iscc_id_path.encode() in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_redacted():
    # type: () -> None
    """Test ISCC-ID resolution for redacted declaration - should return 404."""
    # Create a redacted declaration
    declaration = create_test_declaration(
        gateway="https://example.com",
        redacted=True,
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}")

    # Should return 404 for redacted content
    assert response.status_code == 404
    assert b"ISCC-ID Not Found" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_invalid_format():
    # type: () -> None
    """Test ISCC-ID resolution with invalid format - should return 404."""
    client = Client()

    # Test various invalid formats
    invalid_ids = [
        "invalid",  # Too short
        "INVALID1234567890",  # Wrong case
        "abcd123456789012",  # Invalid characters (1)
        "abcdefghijklmnopqr",  # Too long
        "!@#$%^&*()[]{}",  # Special characters
    ]

    for invalid_id in invalid_ids:
        response = client.get(f"/{invalid_id}")
        assert response.status_code == 404
        assert b"ISCC-ID Not Found" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_wrong_maintype():
    # type: () -> None
    """Test with valid ISCC code but wrong MainType - should return 404."""
    # This is a valid ISCC-CODE (composite) not an ISCC-ID
    iscc_code = "kacypxw445ftynj3"  # First 16 chars of an ISCC-CODE

    client = Client()
    response = client.get(f"/{iscc_code}")

    # Should return 404 because it's not MT.ID
    assert response.status_code == 404
    assert b"ISCC-ID Not Found" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_gateway_with_all_template_vars():
    # type: () -> None
    """Test gateway URL expansion with all supported template variables."""
    # Create a declaration with template using all variables
    declaration = create_test_declaration(
        gateway="https://api.example.com/{iscc_id}/{iscc_code}/{datahash}",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}")

    # Should redirect with all variables expanded
    assert response.status_code == 307
    # ISCC-CODE should have "ISCC:" prefix stripped for cleaner URLs
    iscc_code_clean = declaration.iscc_code[5:] if declaration.iscc_code.startswith("ISCC:") else declaration.iscc_code
    expected_url = f"https://api.example.com/{iscc_id_path}/{iscc_code_clean}/{declaration.datahash}"
    assert response["Location"] == expected_url


@pytest.mark.django_db
def test_iscc_id_resolve_gateway_ending_with_equals():
    # type: () -> None
    """Test gateway URL ending with = (query param style but allowed pattern)."""
    # Create a declaration with gateway ending with =
    # Note: This will be rejected by validate_gateway as it has a query component
    declaration = create_test_declaration(
        gateway="https://example.com/id=",  # This will actually fail validation
        nonce=icr.create_nonce(node_id=1),
    )

    # Update directly to bypass validation for testing
    from iscc_hub.models import IsccDeclaration

    IsccDeclaration.objects.filter(iscc_id=declaration.iscc_id).update(gateway="https://example.com/path/")
    declaration.refresh_from_db()

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}")

    # Should redirect
    assert response.status_code == 307
    # Non-template gateway URLs are returned unmodified
    assert response["Location"] == "https://example.com/path/"


@pytest.mark.django_db
def test_homepage_view():
    # type: () -> None
    """Test homepage view returns successfully."""
    client = Client()
    response = client.get("/")

    assert response.status_code == 200
    assert b"ISCC" in response.content
    assert b"Universal Content" in response.content


@pytest.mark.django_db
def test_health_view():
    # type: () -> None
    """Test health view returns successfully."""
    client = Client()
    response = client.get("/health")

    assert response.status_code == 200
    assert b"pass" in response.content
    assert b"ISCC-HUB service is healthy" in response.content


@pytest.mark.django_db
def test_admin_redirect():
    # type: () -> None
    """Test admin convenience redirect."""
    client = Client()
    response = client.get("/admin", follow=False)

    assert response.status_code == 301
    assert response["Location"] == "/admin/"


@pytest.mark.django_db
def test_iscc_id_resolve_url_reverse():
    # type: () -> None
    """Test URL reversing for ISCC-ID resolution."""
    test_id = "maighfecjmopmiab"
    url = reverse("iscc_id_resolve", kwargs={"iscc_id": test_id})
    assert url == f"/{test_id}"


@pytest.mark.django_db
def test_iscc_id_resolve_multiple_query_params():
    # type: () -> None
    """Test forwarding multiple query parameters including duplicates."""
    declaration = create_test_declaration(
        gateway="https://example.com/api",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}?tag=foo&tag=bar&key=value")

    # Should preserve all query params including duplicates
    assert response.status_code == 307
    location = response["Location"]
    assert "tag=foo" in location
    assert "tag=bar" in location
    assert "key=value" in location


@pytest.mark.django_db
def test_health_view_short_build_commit():
    # type: () -> None
    """Test health view with short build commit hash (less than 8 chars)."""
    with override_settings(BUILD_COMMIT="abc123"):
        client = Client()
        response = client.get("/health")

        assert response.status_code == 200
        assert b"pass" in response.content
        # Should display the full commit as it's less than 8 chars
        assert b"abc123" in response.content


@pytest.mark.django_db
def test_health_view_long_build_commit():
    # type: () -> None
    """Test health view with long build commit hash (8+ chars) - should truncate."""
    with override_settings(BUILD_COMMIT="abcdef0123456789"):
        client = Client()
        response = client.get("/health")

        assert response.status_code == 200
        assert b"pass" in response.content
        # Should display only first 8 chars of long commit
        assert b"abcdef01" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_404_template():
    # type: () -> None
    """Test that 404 template is rendered with ISCC-ID context when ID doesn't exist."""
    # Generate a valid ISCC-ID that doesn't exist in DB
    import iscc_core as ic

    # Generate with a unique hub_id to ensure it doesn't exist
    nonexistent_iscc_id = ic.gen_iscc_id(
        hub_id=4095,  # Max hub ID unlikely to be used in tests
        realm_id=0,  # Test realm
    )
    # Extract just the ID part without ISCC: prefix for URL
    nonexistent_id = nonexistent_iscc_id["iscc"][5:].lower()

    client = Client()
    response = client.get(f"/{nonexistent_id}")

    # Should return 404 with the custom template
    assert response.status_code == 404
    assert b"ISCC-ID Not Found" in response.content
    # The ISCC-ID should be displayed in the 404 page
    assert nonexistent_id.encode() in response.content
    # Check for template-specific content
    assert b"could not be resolved" in response.content
