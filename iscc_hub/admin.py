"""Django admin configuration for ISCC Hub models."""

from typing import Any
from urllib.parse import urlparse

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.paginator import InfinitePaginator

from iscc_hub.models import Hub, IsccDeclaration, PubKey, User

admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    # Forms loaded from `unfold.forms`
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(Hub)
class HubAdmin(ModelAdmin):
    """Admin interface for Hub model."""

    list_display = ["hub_id", "pubkey_short", "url_display", "active"]
    list_filter = ["active"]
    search_fields = ["hub_id", "pubkey", "url"]

    readonly_fields = ["hub_id", "pubkey"]

    fieldsets = (
        ("Hub Identity", {"fields": ("hub_id", "pubkey")}),
        ("Network Configuration", {"fields": ("url", "active")}),
    )

    def pubkey_short(self, obj):
        # type: (Hub) -> str
        """Display truncated public key with tooltip."""
        if obj.pubkey:
            key_str = str(obj.pubkey)
            if len(key_str) > 16:
                return format_html('<span title="{}">{}...</span>', key_str, key_str[:16])
            return key_str
        return "—"

    pubkey_short.short_description = "Public Key"
    pubkey_short.admin_order_field = "pubkey"

    def url_display(self, obj):
        # type: (Hub) -> str
        """Display hub URL as clickable link."""
        if obj.url:
            try:
                parsed = urlparse(obj.url)
                domain = parsed.netloc or obj.url
                return format_html('<a href="{}" target="_blank" title="{}">{}</a>', obj.url, obj.url, domain)
            except Exception:
                return obj.url
        return "—"

    url_display.short_description = "Hub URL"
    url_display.admin_order_field = "url"

    def has_add_permission(self, request):
        # type: (HttpRequest) -> bool
        """Prevent adding hubs through admin (synced from authoritative list)."""
        return False

    def has_change_permission(self, request, obj=None):
        # type: (HttpRequest, Hub | None) -> bool
        """Allow viewing but not editing hubs (synced from authoritative list)."""
        return request.method == "GET"

    def has_delete_permission(self, request, obj=None):
        # type: (HttpRequest, Hub | None) -> bool
        """Prevent deleting hubs (synced from authoritative list)."""
        return False


@admin.register(PubKey)
class PubKeyAdmin(ModelAdmin):
    list_display = ["pubkey_short", "label", "user", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["pubkey", "label", "user__username"]

    def pubkey_short(self, obj):
        return f"{obj.pubkey[:8]}..."

    pubkey_short.short_description = "Public Key"


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
        "pubkey",
        "datahash",
        "nonce",
    ]

    readonly_fields = [
        "iscc_id",
        "iscc_code",
        "datahash",
        "nonce",
        "pubkey",
        "controller",
        "gateway",
        "metahash",
        "creation_time",
        "updated_at",
    ]

    fieldsets = (
        ("Core Identification", {"fields": ("iscc_id", "iscc_code", "datahash", "nonce")}),
        ("Identity Information", {"fields": ("pubkey", "controller", "gateway")}),
        ("Metadata", {"fields": ("metahash",)}),
        ("Timestamps", {"fields": ("creation_time", "updated_at"), "classes": ("collapse",)}),
        ("Status", {"fields": ("redacted",)}),
    )

    list_per_page = 50
    date_hierarchy = "updated_at"

    # Performance optimizations for large datasets
    paginator = InfinitePaginator  # Avoid expensive COUNT queries
    show_full_result_count = False  # Don't show total count
    list_select_related = []  # No FKs in list_display, but prepared for future use
    list_filter_submit = True  # Require explicit filter submission to reduce queries

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
        """Display truncated pubkey with tooltip."""
        pubkey_str = str(obj.pubkey)  # Ensure it's a string (PubkeyField returns string)
        if len(pubkey_str) > 20:
            return format_html('<span title="{}">{}</span>', pubkey_str, pubkey_str[:20] + "...")
        return pubkey_str

    actor_short.short_description = "Public Key"
    actor_short.admin_order_field = "pubkey"

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

    def has_delete_permission(self, request, obj=None):
        # type: (HttpRequest, IsccDeclaration | None) -> bool
        """Prevent deleting declarations through admin (use API with DELETE events)."""
        return False
