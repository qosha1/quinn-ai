"""
Django admin configuration for Authentication app.
"""

from django.contrib import admin

from apps.authentication.models import APIKey


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    """Admin interface for APIKey model."""

    list_display = ["name", "prefix", "company", "created_by", "is_active", "last_used_at", "expires_at", "created_at"]
    list_filter = ["is_active", "company", "created_at", "last_used_at"]
    search_fields = ["name", "prefix", "company__name", "created_by__email"]
    readonly_fields = ["prefix", "key", "last_used_at", "created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("name", "company", "created_by")}),
        ("Key Information", {"fields": ("prefix", "key", "scopes")}),
        ("Status", {"fields": ("is_active", "expires_at", "last_used_at")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        """Disable adding API keys through admin (use API instead)."""
        return False
