# Tests for health endpoint
import pytest
from django.test import AsyncClient


@pytest.mark.asyncio
async def test_health_check_success():
    # type: () -> None
    """Test that health check returns a successful response."""
    client = AsyncClient()
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "status" in data
    assert "version" in data
    assert "description" in data

    # Check response values
    assert data["status"] == "pass"
    assert data["version"] == "0.1.0"
    assert data["description"] == "ISCC-HUB service is healthy"


@pytest.mark.asyncio
async def test_health_check_response_schema():
    # type: () -> None
    """Test that health check response conforms to schema."""
    client = AsyncClient()
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()

    # Verify all fields are present and of correct type
    assert isinstance(data.get("status"), str)
    assert isinstance(data.get("version"), str)
    assert isinstance(data.get("description"), str)

    # Verify status is one of the allowed enum values
    assert data["status"] in ["pass", "fail", "warn"]


@pytest.mark.asyncio
async def test_health_check_content_negotiation_json():
    # type: () -> None
    """Test that health check returns JSON for API clients."""
    client = AsyncClient()

    # Test explicit JSON request
    response = await client.get("/health", headers={"Accept": "application/json"})

    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]

    data = response.json()
    assert data["status"] == "pass"
    assert data["version"] == "0.1.0"
    assert data["description"] == "ISCC Notary service is healthy"


@pytest.mark.asyncio
async def test_health_check_content_negotiation_html():
    # type: () -> None
    """Test that health check returns HTML for browsers."""
    client = AsyncClient()

    # Test browser request with HTML Accept header
    response = await client.get(
        "/health",
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]

    content = response.content.decode()
    assert content.startswith("<!DOCTYPE html>")
    assert "ISCC Notary - Health Status" in content
    assert "Status" in content
    assert "Version" in content
    assert "Description" in content
    assert "PASS" in content.upper()


@pytest.mark.asyncio
async def test_health_check_default_returns_json():
    # type: () -> None
    """Test that health check returns JSON by default (no Accept header)."""
    client = AsyncClient()

    # Test default request (no Accept header)
    response = await client.get("/health")

    assert response.status_code == 200
    # Default should return JSON
    data = response.json()
    assert data["status"] == "pass"
