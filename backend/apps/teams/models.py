"""
Models for multi-tenancy, companies, teams, and memberships.
"""

import secrets
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Company(BaseModel):
    """
    Root tenant model representing a company/organization.

    A company is the top-level organizational unit in the multi-tenant system.
    Each company can have multiple teams and users.
    """

    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("Company name")
    )
    slug = models.SlugField(
        _("slug"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("URL-friendly identifier for the company")
    )
    settings = models.JSONField(
        _("settings"),
        default=dict,
        blank=True,
        help_text=_("Company-specific settings and configuration")
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_companies",
        help_text=_("Company owner with full administrative access")
    )

    class Meta:
        verbose_name = _("company")
        verbose_name_plural = _("companies")
        db_table = "companies"
        ordering = ["name"]

    def __str__(self):
        """Return string representation of the company."""
        return self.name

    def save(self, *args, **kwargs):
        """Auto-generate slug from name if not provided."""
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure uniqueness
            original_slug = self.slug
            counter = 1
            while Company.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)


class Team(BaseModel):
    """
    Team model representing a workspace within a company.

    Teams are organizational units within a company that group users
    and resources together for collaboration.
    """

    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("Team name")
    )
    slug = models.SlugField(
        _("slug"),
        max_length=255,
        db_index=True,
        help_text=_("URL-friendly identifier for the team")
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="teams",
        help_text=_("Company this team belongs to")
    )
    settings = models.JSONField(
        _("settings"),
        default=dict,
        blank=True,
        help_text=_("Team-specific settings and configuration")
    )

    class Meta:
        verbose_name = _("team")
        verbose_name_plural = _("teams")
        db_table = "teams"
        ordering = ["company", "name"]
        unique_together = [["company", "slug"]]

    def __str__(self):
        """Return string representation of the team."""
        return f"{self.company.name} - {self.name}"

    def save(self, *args, **kwargs):
        """Auto-generate slug from name if not provided."""
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure uniqueness within company
            original_slug = self.slug
            counter = 1
            while Team.objects.filter(company=self.company, slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)


class TeamMember(BaseModel):
    """
    Through model for Team-User many-to-many relationship.

    Represents a user's membership in a team with a specific role.
    Role hierarchy: owner > admin > member > viewer
    """

    class Role(models.TextChoices):
        """Role choices for team members."""
        OWNER = "owner", _("Owner")
        ADMIN = "admin", _("Admin")
        MEMBER = "member", _("Member")
        VIEWER = "viewer", _("Viewer")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_memberships",
        help_text=_("User who is a member of the team")
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="members",
        help_text=_("Team the user belongs to")
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
        help_text=_("User's role in the team")
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invited_members",
        help_text=_("User who invited this member")
    )
    joined_at = models.DateTimeField(
        _("joined at"),
        auto_now_add=True,
        help_text=_("Timestamp when the user joined the team")
    )

    class Meta:
        verbose_name = _("team member")
        verbose_name_plural = _("team members")
        db_table = "team_members"
        ordering = ["team", "-joined_at"]
        unique_together = [["user", "team"]]

    def __str__(self):
        """Return string representation of the team member."""
        return f"{self.user.email} - {self.team.name} ({self.role})"


class TeamInvitation(BaseModel):
    """
    Model for team invitations sent to users.

    Allows inviting users to join a team via email with a unique token.
    """

    email = models.EmailField(
        _("email"),
        db_index=True,
        help_text=_("Email address of the invited user")
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="invitations",
        help_text=_("Team the user is invited to")
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=TeamMember.Role.choices,
        default=TeamMember.Role.MEMBER,
        help_text=_("Role the user will have when they accept")
    )
    token = models.CharField(
        _("token"),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("Unique token for accepting the invitation")
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_invitations",
        help_text=_("User who sent the invitation")
    )
    expires_at = models.DateTimeField(
        _("expires at"),
        help_text=_("Timestamp when the invitation expires")
    )
    accepted_at = models.DateTimeField(
        _("accepted at"),
        null=True,
        blank=True,
        help_text=_("Timestamp when the invitation was accepted")
    )

    class Meta:
        verbose_name = _("team invitation")
        verbose_name_plural = _("team invitations")
        db_table = "team_invitations"
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the invitation."""
        return f"Invitation for {self.email} to {self.team.name}"

    def save(self, *args, **kwargs):
        """Auto-generate token and expiration if not provided."""
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        if not self.expires_at:
            # Default expiration: 7 days from now
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    def is_expired(self):
        """Check if the invitation has expired."""
        return timezone.now() > self.expires_at

    def is_accepted(self):
        """Check if the invitation has been accepted."""
        return self.accepted_at is not None
