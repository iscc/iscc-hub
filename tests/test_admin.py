"""Tests for Django admin configuration."""

import json
from datetime import datetime
from unittest.mock import Mock

import pytest
from django.contrib import admin
from django.contrib.admin.sites import site
from django.http import HttpRequest
from django.test import RequestFactory

from iscc_hub.admin import EventAdmin, IsccDeclarationAdmin
from iscc_hub.models import Event, IsccDeclaration


@pytest.fixture
def rf():
    # type: () -> RequestFactory
    """Request factory fixture."""
    return RequestFactory()


@pytest.fixture
def admin_request(rf):
    # type: (RequestFactory) -> HttpRequest
    """Admin request fixture."""
    request = rf.get("/admin/")
    request.user = Mock()
    return request


@pytest.fixture
def iscc_declaration():
    # type: () -> IsccDeclaration
    """Sample IsccDeclaration fixture."""
    return IsccDeclaration(
        iscc_id="ISCC:KAA777777UJZXHQ2",
        iscc_code="ISCC:KAA777777UJZXHQ2I5EBNSAAAA",
        datahash="bdyqnosmb56tqudeimdvmbvkn4dtsn5xpeub26pesrtl2lgoqy",
        nonce="123456789abcdef0123456789abcdef0",
        actor="ed25519_public_key_test",
        gateway="https://example.com",
        metahash="test_metahash",
        event_seq=1,
        redacted=False,
    )


@pytest.fixture
def event():
    # type: () -> Event
    """Sample Event fixture."""
    import json

    return Event(
        seq=1,
        event_type=1,  # CREATED
        iscc_id="ISCC:KAA777777UJZXHQ2",
        event_data=json.dumps({"test": "data"}).encode("utf-8"),
        event_hash="123456789abcdef0" * 4,  # 64 hex chars for BLAKE3 hash
    )


class TestIsccDeclarationAdmin:
    def test_registration(self):
        # type: () -> None
        """Test that IsccDeclarationAdmin is registered."""
        assert IsccDeclaration in site._registry
        assert isinstance(site._registry[IsccDeclaration], IsccDeclarationAdmin)

    def test_list_display(self):
        # type: () -> None
        """Test list_display configuration."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        expected = [
            "iscc_id_display",
            "iscc_code_short",
            "actor_short",
            "gateway_domain",
            "creation_time",
            "redacted",
        ]
        assert admin_obj.list_display == expected

    def test_iscc_id_display(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test ISCC-ID display."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        result = admin_obj.iscc_id_display(iscc_declaration)
        assert result == "ISCC:KAA777777UJZXHQ2"

    def test_iscc_code_short_truncated(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test ISCC-CODE truncation for long codes."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.iscc_code = "ISCC:" + "A" * 50
        result = admin_obj.iscc_code_short(iscc_declaration)
        assert '<span title="ISCC:' in result
        assert "..." in result

    def test_iscc_code_short_not_truncated(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test ISCC-CODE display for short codes."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.iscc_code = "ISCC:SHORT"
        result = admin_obj.iscc_code_short(iscc_declaration)
        assert result == "ISCC:SHORT"

    def test_actor_short_truncated(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test actor truncation for long keys."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.actor = "a" * 50
        result = admin_obj.actor_short(iscc_declaration)
        assert '<span title="' in result
        assert "..." in result

    def test_actor_short_not_truncated(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test actor display for short keys."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.actor = "short_key"
        result = admin_obj.actor_short(iscc_declaration)
        assert result == "short_key"

    def test_gateway_domain_with_url(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test gateway domain extraction from full URL."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.gateway = "https://example.com/path/to/gateway"
        result = admin_obj.gateway_domain(iscc_declaration)
        assert "example.com" in result
        assert "https://example.com/path/to/gateway" in result
        assert 'title="https://example.com/path/to/gateway"' in result

    def test_gateway_domain_with_domain_only(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test gateway domain with domain-only input."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.gateway = "example.com"
        result = admin_obj.gateway_domain(iscc_declaration)
        assert "example.com" in result

    def test_gateway_domain_empty(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test gateway domain with empty gateway."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.gateway = ""
        result = admin_obj.gateway_domain(iscc_declaration)
        assert result == "—"

    def test_gateway_domain_none(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test gateway domain with None gateway."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.gateway = None
        result = admin_obj.gateway_domain(iscc_declaration)
        assert result == "—"

    def test_gateway_domain_format_error(self, iscc_declaration, monkeypatch):
        # type: (IsccDeclaration, Any) -> None
        """Test gateway domain fallback when format_html fails."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.gateway = "https://example.com"

        # Mock format_html to raise an exception
        def mock_format_html(*args, **kwargs):
            # type: (*Any, **Any) -> None
            raise ValueError("Format error")

        monkeypatch.setattr("iscc_hub.admin.format_html", mock_format_html)
        result = admin_obj.gateway_domain(iscc_declaration)
        # Should fallback to the original gateway value
        assert result == "https://example.com"

    def test_creation_time(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test creation time extraction from ISCC-ID."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        # Test with valid ISCC-ID
        iscc_declaration.iscc_id = "ISCC:MEAJU3PC4ICWCTYI"
        result = admin_obj.creation_time(iscc_declaration)
        assert result == "2056-02-02T20:12:57.217556Z"

        # Test with None ISCC-ID
        iscc_declaration.iscc_id = None
        result = admin_obj.creation_time(iscc_declaration)
        assert result == "—"

    def test_get_actions(self, admin_request):
        # type: (HttpRequest) -> None
        """Test custom actions configuration."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        actions = admin_obj.get_actions(admin_request)
        assert "delete_selected" not in actions
        assert "redact" in actions
        assert "unredact" in actions

    @pytest.mark.django_db
    def test_redact_action(self, admin_request):
        # type: (HttpRequest) -> None
        """Test redact action."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        queryset = Mock()
        queryset.update = Mock(return_value=4)
        admin_obj.message_user = Mock()

        admin_obj.redact(admin_request, queryset)

        queryset.update.assert_called_once_with(redacted=True)
        admin_obj.message_user.assert_called_once_with(admin_request, "4 declaration(s) redacted.")

    @pytest.mark.django_db
    def test_unredact_action(self, admin_request):
        # type: (HttpRequest) -> None
        """Test unredact action."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        queryset = Mock()
        queryset.update = Mock(return_value=1)
        admin_obj.message_user = Mock()

        admin_obj.unredact(admin_request, queryset)

        queryset.update.assert_called_once_with(redacted=False)
        admin_obj.message_user.assert_called_once_with(admin_request, "1 declaration(s) unredacted.")

    def test_list_editable(self):
        # type: () -> None
        """Test list_editable configuration."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        assert admin_obj.list_editable == ["redacted"]

    def test_has_add_permission(self, admin_request):
        # type: (HttpRequest) -> None
        """Test that adding declarations is prevented."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        assert admin_obj.has_add_permission(admin_request) is False


class TestEventAdmin:
    def test_registration(self):
        # type: () -> None
        """Test that EventAdmin is registered."""
        assert Event in site._registry
        assert isinstance(site._registry[Event], EventAdmin)

    def test_has_add_permission(self, admin_request):
        # type: (HttpRequest) -> None
        """Test that adding events is prevented."""
        admin_obj = EventAdmin(Event, site)
        assert admin_obj.has_add_permission(admin_request) is False

    def test_has_change_permission_get(self, admin_request):
        # type: (HttpRequest) -> None
        """Test that viewing events is allowed."""
        admin_obj = EventAdmin(Event, site)
        admin_request.method = "GET"
        assert admin_obj.has_change_permission(admin_request) is True

    def test_has_change_permission_post(self, admin_request):
        # type: (HttpRequest) -> None
        """Test that editing events is prevented."""
        admin_obj = EventAdmin(Event, site)
        admin_request.method = "POST"
        assert admin_obj.has_change_permission(admin_request) is False

    def test_has_delete_permission(self, admin_request):
        # type: (HttpRequest) -> None
        """Test that deleting events is prevented."""
        admin_obj = EventAdmin(Event, site)
        assert admin_obj.has_delete_permission(admin_request) is False

    def test_event_type_display_created(self, event):
        # type: (Event) -> None
        """Test event type display for CREATED."""
        admin_obj = EventAdmin(Event, site)
        event.event_type = 1
        result = admin_obj.event_type_display(event)
        assert "CREATED" in result
        assert "color: green" in result

    def test_event_type_display_updated(self, event):
        # type: (Event) -> None
        """Test event type display for UPDATED."""
        admin_obj = EventAdmin(Event, site)
        event.event_type = 2
        result = admin_obj.event_type_display(event)
        assert "UPDATED" in result
        assert "color: blue" in result

    def test_event_type_display_deleted(self, event):
        # type: (Event) -> None
        """Test event type display for DELETED."""
        admin_obj = EventAdmin(Event, site)
        event.event_type = 3
        result = admin_obj.event_type_display(event)
        assert "DELETED" in result
        assert "color: red" in result

    def test_event_type_display_unknown(self, event):
        # type: (Event) -> None
        """Test event type display for unknown type."""
        admin_obj = EventAdmin(Event, site)
        event.event_type = 999
        result = admin_obj.event_type_display(event)
        assert "UNKNOWN" in result
        assert "color: black" in result

    def test_iscc_id_display(self, event):
        # type: (Event) -> None
        """Test ISCC-ID display."""
        admin_obj = EventAdmin(Event, site)
        result = admin_obj.iscc_id_display(event)
        assert result == "ISCC:KAA777777UJZXHQ2"

    def test_iscc_id_timestamp(self, event):
        # type: (Event) -> None
        """Test ISCC-ID timestamp extraction."""
        admin_obj = EventAdmin(Event, site)
        # Test with valid ISCC-ID
        event.iscc_id = "ISCC:MEAJU3PC4ICWCTYI"
        result = admin_obj.iscc_id_timestamp(event)
        assert result == "2056-02-02T20:12:57.217556Z"

        # Test with None ISCC-ID
        event.iscc_id = None
        result = admin_obj.iscc_id_timestamp(event)
        assert result == "—"

    def test_event_data_formatted_valid_json(self, event):
        # type: (Event) -> None
        """Test JSON formatting for valid data."""
        admin_obj = EventAdmin(Event, site)
        test_data = {"key": "value", "nested": {"data": 123}}
        event.event_data = json.dumps(test_data).encode("utf-8")
        result = admin_obj.event_data_formatted(event)
        assert "<pre" in result
        assert "background: #f5f5f5" in result
        # HTML-escaped quotes in the output
        assert "&quot;key&quot;: &quot;value&quot;" in result

    def test_event_data_formatted_invalid_json(self, event):
        # type: (Event) -> None
        """Test JSON formatting fallback for invalid data."""
        admin_obj = EventAdmin(Event, site)
        # Set invalid binary data that cannot be decoded as UTF-8 JSON
        event.event_data = b"\xff\xfe\xfd"  # Invalid UTF-8 bytes

        result = admin_obj.event_data_formatted(event)

        # Should fallback to string representation of binary data
        assert "b'\\xff\\xfe\\xfd'" in result

    def test_event_hash_short_truncated(self, event):
        # type: (Event) -> None
        """Test event hash truncation for long hashes."""
        admin_obj = EventAdmin(Event, site)
        # event_hash is already set to 64 hex chars in fixture
        result = admin_obj.event_hash_short(event)
        # Hash should be truncated and have tooltip
        assert '<span title="' in result
        assert "...</span>" in result
        # Should show first 16 chars of hex
        assert event.event_hash[:16] in result

    def test_event_hash_short_not_truncated(self, event):
        # type: (Event) -> None
        """Test event hash display for short hashes."""
        admin_obj = EventAdmin(Event, site)
        # Set a short hash (16 hex chars)
        event.event_hash = "123456789abcdef0"
        result = admin_obj.event_hash_short(event)
        # Should not be truncated
        assert result == "123456789abcdef0"

    def test_event_hash_short_none(self, event):
        # type: (Event) -> None
        """Test event hash display when hash is None."""
        admin_obj = EventAdmin(Event, site)
        event.event_hash = None
        result = admin_obj.event_hash_short(event)
        assert result == "—"
