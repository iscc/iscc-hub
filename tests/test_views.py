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


@pytest.mark.django_db
def test_iscc_id_resolve_forward_to_active_remote_hub():
    # type: () -> None
    """Test ISCC-ID resolution forwards to active remote hub."""
    from iscc_hub.models import Hub

    # Create a remote hub entry
    Hub.objects.create(
        hub_id=2,
        pubkey="z6MkqLoZvd5FQbmZMf8amGUBTdqL1c4pWK7NmhxTJBRFXQHc",
        url="https://hub2.example.com",
        active=True,
    )

    # Generate ISCC-ID with hub_id=2
    remote_iscc_id = generate_test_iscc_id(hub_id=2, seq=100)
    # Extract just the ID part without ISCC: prefix for URL
    iscc_id_path = remote_iscc_id[5:].lower() if remote_iscc_id.startswith("ISCC:") else remote_iscc_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}")

    # Should redirect to remote hub
    assert response.status_code == 307
    assert response["Location"] == f"https://hub2.example.com/{iscc_id_path}"


@pytest.mark.django_db
def test_iscc_id_resolve_forward_to_inactive_hub_returns_404():
    # type: () -> None
    """Test ISCC-ID resolution returns 404 for inactive remote hub."""
    from iscc_hub.models import Hub

    # Create an inactive hub entry
    Hub.objects.create(
        hub_id=3,
        pubkey="z6Mkr2dAqiRrYBYMzk2U1Fw5wjQoTxbnXsuT9JJT6ZFZyMFY",
        url="https://hub3.example.com",
        active=False,
    )

    # Generate ISCC-ID with hub_id=3
    remote_iscc_id = generate_test_iscc_id(hub_id=3, seq=200)
    # Extract just the ID part without ISCC: prefix for URL
    iscc_id_path = remote_iscc_id[5:].lower() if remote_iscc_id.startswith("ISCC:") else remote_iscc_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}")

    # Should return 404 because hub is not active
    assert response.status_code == 404
    assert b"ISCC-ID Not Found" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_forward_to_nonexistent_hub_returns_404():
    # type: () -> None
    """Test ISCC-ID resolution returns 404 for non-existent remote hub."""
    # Generate ISCC-ID with hub_id=999 (no Hub record exists)
    remote_iscc_id = generate_test_iscc_id(hub_id=999, seq=300)
    # Extract just the ID part without ISCC: prefix for URL
    iscc_id_path = remote_iscc_id[5:].lower() if remote_iscc_id.startswith("ISCC:") else remote_iscc_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}")

    # Should return 404 because hub doesn't exist
    assert response.status_code == 404
    assert b"ISCC-ID Not Found" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_local_hub_still_works():
    # type: () -> None
    """Test local ISCC-ID resolution still works (hub_id=1)."""
    # Create a local declaration (hub_id=1 matches ISCC_HUB_ID in test env)
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

    # Should redirect to gateway (local resolution works)
    assert response.status_code == 307
    assert response["Location"] == "https://example.com/metadata"


@pytest.mark.django_db
def test_iscc_id_resolve_local_hub_nonexistent():
    # type: () -> None
    """Test local ISCC-ID that doesn't exist returns 404."""
    # Generate a local ISCC-ID (hub_id=1) that doesn't exist in DB
    local_iscc_id = generate_test_iscc_id(hub_id=1, seq=999999)
    # Extract just the ID part without ISCC: prefix for URL
    iscc_id_path = local_iscc_id[5:].lower() if local_iscc_id.startswith("ISCC:") else local_iscc_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}")

    # Should return 404 because local ISCC-ID doesn't exist
    assert response.status_code == 404
    assert b"ISCC-ID Not Found" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_remote_hub_preserves_query_params():
    # type: () -> None
    """Test remote hub forwarding preserves query parameters."""
    from iscc_hub.models import Hub

    # Create a remote hub entry with valid pubkey from fixtures
    Hub.objects.filter(hub_id=500).delete()  # Clean up first
    Hub.objects.create(
        hub_id=500,
        pubkey="z6MkqCganwv6TXSy5r3XLJf5KsjadEWDgbTP5apycN4zbdhk",  # Valid pubkey from fixtures
        url="https://hub500.example.com",
        active=True,
    )

    # Generate ISCC-ID with hub_id=500
    remote_iscc_id = generate_test_iscc_id(hub_id=500, seq=5000)
    # Extract just the ID part without ISCC: prefix for URL
    iscc_id_path = remote_iscc_id[5:].lower() if remote_iscc_id.startswith("ISCC:") else remote_iscc_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}?serviceType=Foo&key=value")

    # Should redirect to remote hub with query params preserved
    assert response.status_code == 307
    location = response["Location"]
    assert location.startswith(f"https://hub500.example.com/{iscc_id_path}")
    assert "serviceType=Foo" in location
    assert "key=value" in location


@pytest.mark.django_db
def test_iscc_id_resolve_gateway_template_preserves_query_params():
    # type: () -> None
    """Test gateway template expansion preserves query parameters."""
    # Create a declaration with gateway template
    declaration = create_test_declaration(
        gateway="https://registry.com/{iscc_id}",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}?serviceType=CoreMetadata")

    # Should redirect with query params preserved
    assert response.status_code == 307
    location = response["Location"]
    assert location.startswith(f"https://registry.com/{iscc_id_path}")
    assert "serviceType=CoreMetadata" in location


@pytest.mark.django_db
def test_iscc_id_resolve_redirect_false_with_gateway():
    # type: () -> None
    """Test redirect=false disables gateway redirect and shows declaration detail page."""
    # Create a declaration with gateway
    declaration = create_test_declaration(
        gateway="https://example.com/metadata",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}?redirect=false")

    # Should show detail page instead of redirecting
    assert response.status_code == 200
    assert b"ISCC-CODE" in response.content
    assert declaration.iscc_code.encode() in response.content
    assert declaration.datahash.encode() in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_redirect_false_with_gateway_template():
    # type: () -> None
    """Test redirect=false with gateway template shows detail page."""
    # Create a declaration with gateway template
    declaration = create_test_declaration(
        gateway="https://registry.com/{iscc_id}",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}?redirect=false")

    # Should show detail page instead of redirecting
    assert response.status_code == 200
    assert b"ISCC-CODE" in response.content
    assert declaration.iscc_code.encode() in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_redirect_false_remote_hub_active():
    # type: () -> None
    """Test redirect=false with remote hub shows remote info page."""
    from iscc_hub.models import Hub

    # Create a remote hub entry
    Hub.objects.create(
        hub_id=50,
        pubkey="z6MkqLoZvd5FQbmZMf8amGUBTdqL1c4pWK7NmhxTJBRFXQHc",
        url="https://hub50.example.com",
        active=True,
    )

    # Generate ISCC-ID with hub_id=50
    remote_iscc_id = generate_test_iscc_id(hub_id=50, seq=100)
    # Extract just the ID part without ISCC: prefix for URL
    iscc_id_path = remote_iscc_id[5:].lower() if remote_iscc_id.startswith("ISCC:") else remote_iscc_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}?redirect=false")

    # Should show remote info page
    assert response.status_code == 200
    assert b"Remote ISCC-ID" in response.content
    assert b"issued by a different ISCC-HUB" in response.content
    assert b"Hub ID:" in response.content
    assert b"50" in response.content
    assert b"https://hub50.example.com" in response.content
    assert b"View on Issuing Hub" in response.content
    # Check the link includes redirect=false
    assert b"?redirect=false" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_redirect_false_remote_hub_inactive():
    # type: () -> None
    """Test redirect=false with inactive remote hub shows info page."""
    from iscc_hub.models import Hub

    # Create an inactive hub entry
    Hub.objects.create(
        hub_id=51,
        pubkey="z6Mkr2dAqiRrYBYMzk2U1Fw5wjQoTxbnXsuT9JJT6ZFZyMFY",
        url="https://hub51.example.com",
        active=False,
    )

    # Generate ISCC-ID with hub_id=51
    remote_iscc_id = generate_test_iscc_id(hub_id=51, seq=200)
    # Extract just the ID part without ISCC: prefix for URL
    iscc_id_path = remote_iscc_id[5:].lower() if remote_iscc_id.startswith("ISCC:") else remote_iscc_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}?redirect=false")

    # Should show remote info page without hub details
    assert response.status_code == 200
    assert b"Remote ISCC-ID" in response.content
    assert b"Hub ID:" in response.content
    assert b"51" in response.content
    assert b"Hub information is not available" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_redirect_false_remote_hub_nonexistent():
    # type: () -> None
    """Test redirect=false with non-existent remote hub shows info page."""
    # Generate ISCC-ID with hub_id=888 (no Hub record exists)
    remote_iscc_id = generate_test_iscc_id(hub_id=888, seq=300)
    # Extract just the ID part without ISCC: prefix for URL
    iscc_id_path = remote_iscc_id[5:].lower() if remote_iscc_id.startswith("ISCC:") else remote_iscc_id.lower()

    client = Client()
    response = client.get(f"/{iscc_id_path}?redirect=false")

    # Should show remote info page without hub details
    assert response.status_code == 200
    assert b"Remote ISCC-ID" in response.content
    assert b"Hub ID:" in response.content
    assert b"888" in response.content
    assert b"Hub information is not available" in response.content


@pytest.mark.django_db
def test_iscc_id_resolve_redirect_true_still_redirects():
    # type: () -> None
    """Test redirect=true (explicit) still redirects as expected."""
    # Create a declaration with gateway
    declaration = create_test_declaration(
        gateway="https://example.com/metadata",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )
    response = client.get(f"/{iscc_id_path}?redirect=true")

    # Should still redirect (query params are preserved)
    assert response.status_code == 307
    assert "https://example.com/metadata" in response["Location"]
    assert "redirect=true" in response["Location"]


@pytest.mark.django_db
def test_iscc_id_resolve_default_behavior_unchanged():
    # type: () -> None
    """Test default behavior (no redirect param) still redirects."""
    # Create a declaration with gateway
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

    # Should redirect (default behavior unchanged)
    assert response.status_code == 307
    assert response["Location"] == "https://example.com/metadata"


@pytest.mark.django_db
def test_iscc_id_resolve_redirect_false_case_insensitive():
    # type: () -> None
    """Test redirect parameter is case-insensitive."""
    # Create a declaration with gateway
    declaration = create_test_declaration(
        gateway="https://example.com/metadata",
        nonce=icr.create_nonce(node_id=1),
    )

    client = Client()
    # Strip ISCC: prefix from the ID for the URL path - MUST BE LOWERCASE
    iscc_id_path = (
        declaration.iscc_id[5:].lower() if declaration.iscc_id.startswith("ISCC:") else declaration.iscc_id.lower()
    )

    # Test various case combinations
    for redirect_value in ["false", "False", "FALSE", "FaLsE"]:
        response = client.get(f"/{iscc_id_path}?redirect={redirect_value}")
        # Should show detail page for all case variants
        assert response.status_code == 200
        assert b"ISCC-CODE" in response.content
