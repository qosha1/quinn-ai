"""
Django admin configuration for Teams app.
"""

from django.contrib import admin

from apps.teams.models import Company, Team, TeamMember, TeamInvitation


class TeamInline(admin.TabularInline):
    """Inline admin for teams within a company."""
    model = Team
    extra = 0
    fields = ["name", "slug", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Admin interface for Company model."""

    list_display = ["name", "slug", "owner", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "slug", "owner__email"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [TeamInline]

    fieldsets = (
        (None, {"fields": ("name", "slug", "owner")}),
        ("Settings", {"fields": ("settings",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


class TeamMemberInline(admin.TabularInline):
    """Inline admin for team members within a team."""
    model = TeamMember
    extra = 0
    fields = ["user", "role", "invited_by", "joined_at"]
    readonly_fields = ["joined_at"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Admin interface for Team model."""

    list_display = ["name", "company", "slug", "created_at"]
    list_filter = ["company", "created_at"]
    search_fields = ["name", "slug", "company__name"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [TeamMemberInline]

    fieldsets = (
        (None, {"fields": ("name", "slug", "company")}),
        ("Settings", {"fields": ("settings",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    """Admin interface for TeamMember model."""

    list_display = ["user", "team", "role", "invited_by", "joined_at"]
    list_filter = ["role", "team__company", "joined_at"]
    search_fields = ["user__email", "team__name"]
    readonly_fields = ["joined_at", "created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("user", "team", "role")}),
        ("Invitation", {"fields": ("invited_by",)}),
        ("Timestamps", {"fields": ("joined_at", "created_at", "updated_at")}),
    )


@admin.register(TeamInvitation)
class TeamInvitationAdmin(admin.ModelAdmin):
    """Admin interface for TeamInvitation model."""

    list_display = ["email", "team", "role", "invited_by", "expires_at", "accepted_at", "created_at"]
    list_filter = ["role", "team__company", "accepted_at", "created_at"]
    search_fields = ["email", "team__name", "token"]
    readonly_fields = ["token", "created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("email", "team", "role")}),
        ("Token", {"fields": ("token", "expires_at", "accepted_at")}),
        ("Invitation", {"fields": ("invited_by",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
