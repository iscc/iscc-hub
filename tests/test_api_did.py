"""Tests for DID Web Method endpoint."""

import json

import pytest
from django.test import Client


@pytest.mark.django_db
def test_did_document_returns_json_structure():
    # type: () -> None
    """Test that DID document returns valid JSON with expected structure."""
    client = Client()
    response = client.get("/.well-known/did.json")

    assert response.status_code == 200

    # Parse JSON response
    did_doc = json.loads(response.content)

    # Verify required DID document fields
    assert "id" in did_doc
    assert did_doc["id"].startswith("did:web:")
    assert "verificationMethod" in did_doc
    assert isinstance(did_doc["verificationMethod"], list)
    assert len(did_doc["verificationMethod"]) > 0

    # Verify verification method structure
    vm = did_doc["verificationMethod"][0]
    assert "id" in vm
    assert "type" in vm
    assert "controller" in vm
    assert "publicKeyMultibase" in vm

    # Verify authentication methods are present
    assert "authentication" in did_doc
    assert "assertionMethod" in did_doc


@pytest.mark.django_db
def test_did_document_cors_header():
    # type: () -> None
    """Test that DID endpoint includes CORS header per W3C spec."""
    client = Client()
    response = client.get("/.well-known/did.json")

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" in response
    assert response["Access-Control-Allow-Origin"] == "*"


@pytest.mark.django_db
def test_did_document_content_type():
    # type: () -> None
    """Test that DID endpoint returns application/json content type."""
    client = Client()
    response = client.get("/.well-known/did.json")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"


@pytest.mark.django_db
def test_did_document_ignores_html_accept_header():
    # type: () -> None
    """Test that DID endpoint always returns JSON even with HTML accept header."""
    client = Client()
    response = client.get("/.well-known/did.json", HTTP_ACCEPT="text/html")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"

    # Verify it's valid JSON
    did_doc = json.loads(response.content)
    assert "id" in did_doc
    assert did_doc["id"].startswith("did:web:")


@pytest.mark.django_db
def test_did_document_ignores_format_parameter():
    # type: () -> None
    """Test that DID endpoint ignores format=html query parameter."""
    client = Client()
    response = client.get("/.well-known/did.json?format=html")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"

    # Verify it's valid JSON
    did_doc = json.loads(response.content)
    assert "id" in did_doc
    assert did_doc["id"].startswith("did:web:")


@pytest.mark.django_db
def test_did_document_with_mixed_negotiation():
    # type: () -> None
    """Test DID endpoint with both HTML accept header and format parameter."""
    client = Client()
    response = client.get("/.well-known/did.json?format=html", HTTP_ACCEPT="text/html,application/xhtml+xml")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert "Access-Control-Allow-Origin" in response

    # Verify response is valid JSON
    did_doc = json.loads(response.content)
    assert "verificationMethod" in did_doc
