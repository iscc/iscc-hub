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
        deleted=False,
    )


@pytest.fixture
def event():
    # type: () -> Event
    """Sample Event fixture."""
    return Event(
        seq=1,
        event_type=1,  # CREATED
        iscc_id="ISCC:KAA777777UJZXHQ2",
        iscc_note={"test": "data"},
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
            "gateway",
            "creation_time",
            "updated_at",
            "is_deleted",
        ]
        assert admin_obj.list_display == expected

    def test_iscc_id_display(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test ISCC-ID display formatting."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        result = admin_obj.iscc_id_display(iscc_declaration)
        assert "<code>ISCC:KAA777777UJZXHQ2</code>" in result

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

    def test_is_deleted_true(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test deleted status display."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.deleted = True
        result = admin_obj.is_deleted(iscc_declaration)
        assert "✗ Deleted" in result
        assert "color: red" in result

    def test_is_deleted_false(self, iscc_declaration):
        # type: (IsccDeclaration) -> None
        """Test active status display."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        iscc_declaration.deleted = False
        result = admin_obj.is_deleted(iscc_declaration)
        assert "✓ Active" in result
        assert "color: green" in result

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
        assert "soft_delete" in actions
        assert "restore" in actions

    @pytest.mark.django_db
    def test_soft_delete_action(self, admin_request):
        # type: (HttpRequest) -> None
        """Test soft delete action."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        queryset = Mock()
        queryset.update = Mock(return_value=3)
        admin_obj.message_user = Mock()

        admin_obj.soft_delete(admin_request, queryset)

        queryset.update.assert_called_once_with(deleted=True)
        admin_obj.message_user.assert_called_once_with(admin_request, "3 declaration(s) marked as deleted.")

    @pytest.mark.django_db
    def test_restore_action(self, admin_request):
        # type: (HttpRequest) -> None
        """Test restore action."""
        admin_obj = IsccDeclarationAdmin(IsccDeclaration, site)
        queryset = Mock()
        queryset.update = Mock(return_value=2)
        admin_obj.message_user = Mock()

        admin_obj.restore(admin_request, queryset)

        queryset.update.assert_called_once_with(deleted=False)
        admin_obj.message_user.assert_called_once_with(admin_request, "2 declaration(s) restored.")


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
        """Test ISCC-ID display formatting."""
        admin_obj = EventAdmin(Event, site)
        result = admin_obj.iscc_id_display(event)
        assert "<code>ISCC:KAA777777UJZXHQ2</code>" in result

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

    def test_iscc_note_formatted_valid_json(self, event):
        # type: (Event) -> None
        """Test JSON formatting for valid data."""
        admin_obj = EventAdmin(Event, site)
        event.iscc_note = {"key": "value", "nested": {"data": 123}}
        result = admin_obj.iscc_note_formatted(event)
        assert "<pre" in result
        assert "background: #f5f5f5" in result
        # HTML-escaped quotes in the output
        assert "&quot;key&quot;: &quot;value&quot;" in result

    def test_iscc_note_formatted_invalid_json(self, event):
        # type: (Event) -> None
        """Test JSON formatting fallback for invalid data."""
        admin_obj = EventAdmin(Event, site)
        # Create a mock object that will raise TypeError when serialized
        mock_obj = Mock()
        mock_obj.__str__ = Mock(return_value="fallback_string")
        event.iscc_note = mock_obj

        # Mock json.dumps to raise TypeError
        import iscc_hub.admin

        original_dumps = iscc_hub.admin.json.dumps
        iscc_hub.admin.json.dumps = Mock(side_effect=TypeError("Cannot serialize"))

        result = admin_obj.iscc_note_formatted(event)

        # Restore original dumps
        iscc_hub.admin.json.dumps = original_dumps

        assert result == "fallback_string"

    def test_event_time_iso_with_time(self, event):
        # type: (Event) -> None
        """Test event time ISO formatting with timestamp."""
        admin_obj = EventAdmin(Event, site)
        event.event_time = datetime(2025, 8, 12, 10, 30, 45, 123456)
        result = admin_obj.event_time_iso(event)
        assert result == "2025-08-12T10:30:45.123Z"

    def test_event_time_iso_without_time(self, event):
        # type: (Event) -> None
        """Test event time ISO formatting without timestamp."""
        admin_obj = EventAdmin(Event, site)
        event.event_time = None
        result = admin_obj.event_time_iso(event)
        assert result == "—"
