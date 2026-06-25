"""End-to-end tests for cross-origin reads of the public read surface.

These run through the full Django middleware stack via django.test.Client (the
Ninja TestClient bypasses middleware), so they verify CorsReadMiddleware stamps
``Access-Control-Allow-Origin: *`` on JSON/log read responses while leaving HTML
views and write endpoints untouched. This is the prerequisite for a Hub homepage
to resolve declarations issued by another Hub for the "Who signed it?" rail.
"""

import pytest
from django.test import Client

from tests.conftest import create_test_declaration, generate_test_iscc_id


@pytest.mark.django_db
def test_cors_header_on_resolve_json():
    # type: () -> None
    """Resolving a local ISCC-ID as JSON carries the wildcard CORS header."""
    iscc_id = generate_test_iscc_id(hub_id=1, seq=1)
    create_test_declaration(seq=1, iscc_id=iscc_id, controller="did:web:elsevier.com")

    response = Client().get(f"/{iscc_id}", HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "*"
    assert response.json()["controller"] == "did:web:elsevier.com"


@pytest.mark.django_db
def test_cors_header_on_resolve_json_error():
    # type: () -> None
    """A JSON read error (404) is still CORS-open, so cross-hub fetch reads it cleanly."""
    response = Client().get("/INVALID-ID", HTTP_ACCEPT="application/json")

    assert response.status_code == 404
    assert response["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_cors_header_on_lookup():
    # type: () -> None
    """The /lookup read endpoint is path-routed to the JSON API and is CORS-open."""
    response = Client().get("/lookup?datahash=1e20ab")

    assert "Access-Control-Allow-Origin" in response
    assert response["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_no_cors_header_on_html_view():
    # type: () -> None
    """The HTML homepage is not part of the read surface and gets no CORS header."""
    response = Client().get("/", HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response
