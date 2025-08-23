"""Django admin configuration for ISCC Hub models."""

import json
from typing import Any
from urllib.parse import urlparse

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from iscc_hub.models import Event, IsccDeclaration


@admin.register(IsccDeclaration)
class IsccDeclarationAdmin(ModelAdmin):
    """Admin interface for IsccDeclaration model."""

    list_display = [
        "iscc_id_display",
        "iscc_code_short",
        "actor_short",
        "gateway_domain",
        "creation_time",
        "redacted",
    ]

    list_editable = ["redacted"]

    list_filter = [
        "redacted",
        "updated_at",
    ]

    search_fields = [
        "iscc_id",
        "iscc_code",
        "actor",
        "datahash",
        "nonce",
    ]

    readonly_fields = [
        "iscc_id",
        "event_seq",
        "creation_time",
        "updated_at",
    ]

    fieldsets = (
        ("Core Identification", {"fields": ("iscc_id", "iscc_code", "datahash", "nonce")}),
        ("Actor Information", {"fields": ("actor", "gateway")}),
        ("Metadata", {"fields": ("metahash", "event_seq")}),
        ("Timestamps", {"fields": ("creation_time", "updated_at"), "classes": ("collapse",)}),
        ("Status", {"fields": ("redacted",)}),
    )

    list_per_page = 50
    date_hierarchy = "updated_at"

    def iscc_id_display(self, obj):
        # type: (IsccDeclaration) -> str
        """Display ISCC-ID."""
        return str(obj.iscc_id)

    iscc_id_display.short_description = "ISCC-ID"
    iscc_id_display.admin_order_field = "iscc_id"

    def iscc_code_short(self, obj):
        # type: (IsccDeclaration) -> str
        """Display truncated ISCC-CODE with tooltip."""
        if len(obj.iscc_code) > 30:
            return format_html('<span title="{}">{}</span>', obj.iscc_code, obj.iscc_code[:30] + "...")
        return obj.iscc_code

    iscc_code_short.short_description = "ISCC-CODE"
    iscc_code_short.admin_order_field = "iscc_code"

    def actor_short(self, obj):
        # type: (IsccDeclaration) -> str
        """Display truncated actor key with tooltip."""
        if len(obj.actor) > 20:
            return format_html('<span title="{}">{}</span>', obj.actor, obj.actor[:20] + "...")
        return obj.actor

    actor_short.short_description = "Actor"
    actor_short.admin_order_field = "actor"

    def gateway_domain(self, obj):
        # type: (IsccDeclaration) -> str
        """Display only the domain part of gateway URL with full URL on hover."""
        if not obj.gateway:
            return "—"

        try:
            parsed = urlparse(obj.gateway)
            domain = parsed.netloc or obj.gateway
            return format_html('<span title="{}">{}</span>', obj.gateway, domain)
        except Exception:
            # Fallback to original gateway if parsing fails
            return obj.gateway

    gateway_domain.short_description = "Gateway"
    gateway_domain.admin_order_field = "gateway"

    def creation_time(self, obj):
        # type: (IsccDeclaration) -> str
        """Extract creation timestamp from ISCC-ID."""
        if obj.iscc_id:
            from iscc_hub.iscc_id import IsccID

            iscc_obj = IsccID(obj.iscc_id)
            return iscc_obj.timestamp_iso
        return "—"

    creation_time.short_description = "Declaration Time"
    creation_time.admin_order_field = "iscc_id"

    def get_actions(self, request):
        # type: (HttpRequest) -> dict[str, Any]
        """Add custom batch actions."""
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    @admin.action(description="Redact selected declarations")
    def redact(self, request, queryset):
        # type: (HttpRequest, QuerySet[IsccDeclaration]) -> None
        """Redact selected declarations."""
        updated = queryset.update(redacted=True)
        self.message_user(request, f"{updated} declaration(s) redacted.")

    @admin.action(description="Unredact selected declarations")
    def unredact(self, request, queryset):
        # type: (HttpRequest, QuerySet[IsccDeclaration]) -> None
        """Unredact selected declarations."""
        updated = queryset.update(redacted=False)
        self.message_user(request, f"{updated} declaration(s) unredacted.")

    actions = ["redact", "unredact"]

    def has_add_permission(self, request):
        # type: (HttpRequest) -> bool
        """Prevent adding declarations through admin (materialized from events)."""
        return False


@admin.register(Event)
class EventAdmin(ModelAdmin):
    """Admin interface for Event model (read-only)."""

    list_display = [
        "seq",
        "event_type_display",
        "iscc_id_display",
        "iscc_id_timestamp",
        "event_time",
    ]

    list_filter = [
        "event_type",
    ]

    list_filter_sheet = False
    list_filter_submit = False

    search_fields = [
        "seq",
        "iscc_id",
    ]

    readonly_fields = [
        "seq",
        "event_type",
        "iscc_id",
        "iscc_id_timestamp",
        "event_time",
        "iscc_note_formatted",
    ]

    fieldsets = (
        ("Event Information", {"fields": ("seq", "event_type", "iscc_id", "iscc_id_timestamp", "event_time")}),
        ("Event Data", {"fields": ("iscc_note_formatted",), "classes": ("wide",)}),
    )

    list_per_page = 100
    date_hierarchy = "event_time"

    def has_add_permission(self, request):
        # type: (HttpRequest) -> bool
        """Prevent adding events through admin (append-only log)."""
        return False

    def has_change_permission(self, request, obj=None):
        # type: (HttpRequest, Event | None) -> bool
        """Allow viewing but not editing events."""
        return request.method == "GET"

    def has_delete_permission(self, request, obj=None):
        # type: (HttpRequest, Event | None) -> bool
        """Prevent deleting events (append-only log)."""
        return False

    def event_type_display(self, obj):
        # type: (Event) -> str
        """Display event type with color coding."""
        colors = {
            1: ("CREATED", "green"),
            2: ("UPDATED", "blue"),
            3: ("DELETED", "red"),
        }
        event_name, color = colors.get(obj.event_type, ("UNKNOWN", "black"))
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, event_name)

    event_type_display.short_description = "Event Type"
    event_type_display.admin_order_field = "event_type"

    def iscc_id_display(self, obj):
        # type: (Event) -> str
        """Display ISCC-ID."""
        return str(obj.iscc_id)

    iscc_id_display.short_description = "ISCC-ID"
    iscc_id_display.admin_order_field = "iscc_id"

    def iscc_id_timestamp(self, obj):
        # type: (Event) -> str
        """Extract initial declaration timestamp from ISCC-ID."""
        if obj.iscc_id:
            from iscc_hub.iscc_id import IsccID

            iscc_obj = IsccID(obj.iscc_id)
            return iscc_obj.timestamp_iso
        return "—"

    iscc_id_timestamp.short_description = "Declaration Time (ISCC-ID)"
    iscc_id_timestamp.admin_order_field = "iscc_id"

    def iscc_note_formatted(self, obj):
        # type: (Event) -> str
        """Display formatted JSON for IsccNote."""
        try:
            formatted = json.dumps(obj.iscc_note, indent=2)
            return format_html(
                '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto;">{}</pre>',
                formatted,
            )
        except (TypeError, ValueError):
            return str(obj.iscc_note)

    iscc_note_formatted.short_description = "ISCC Note Data"
