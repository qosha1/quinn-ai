"""
Initial migration for teams app.
"""

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.contrib.postgres.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier for this record",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last updated",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Company name",
                        max_length=255,
                        verbose_name="name",
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        db_index=True,
                        help_text="URL-friendly identifier for the company",
                        max_length=255,
                        unique=True,
                        verbose_name="slug",
                    ),
                ),
                (
                    "settings",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Company-specific settings and configuration",
                        verbose_name="settings",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        help_text="Company owner with full administrative access",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="owned_companies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "company",
                "verbose_name_plural": "companies",
                "db_table": "companies",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Team",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier for this record",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last updated",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Team name",
                        max_length=255,
                        verbose_name="name",
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        db_index=True,
                        help_text="URL-friendly identifier for the team",
                        max_length=255,
                        verbose_name="slug",
                    ),
                ),
                (
                    "settings",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Team-specific settings and configuration",
                        verbose_name="settings",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        help_text="Company this team belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teams",
                        to="teams.company",
                    ),
                ),
            ],
            options={
                "verbose_name": "team",
                "verbose_name_plural": "teams",
                "db_table": "teams",
                "ordering": ["company", "name"],
                "unique_together": {("company", "slug")},
            },
        ),
        migrations.CreateModel(
            name="TeamMember",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier for this record",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last updated",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("admin", "Admin"),
                            ("member", "Member"),
                            ("viewer", "Viewer"),
                        ],
                        default="member",
                        help_text="User's role in the team",
                        max_length=20,
                        verbose_name="role",
                    ),
                ),
                (
                    "joined_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when the user joined the team",
                        verbose_name="joined at",
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who invited this member",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invited_members",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        help_text="Team the user belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="teams.team",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="User who is a member of the team",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="team_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "team member",
                "verbose_name_plural": "team members",
                "db_table": "team_members",
                "ordering": ["team", "-joined_at"],
                "unique_together": {("user", "team")},
            },
        ),
        migrations.CreateModel(
            name="TeamInvitation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier for this record",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last updated",
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        db_index=True,
                        help_text="Email address of the invited user",
                        max_length=254,
                        verbose_name="email",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("admin", "Admin"),
                            ("member", "Member"),
                            ("viewer", "Viewer"),
                        ],
                        default="member",
                        help_text="Role the user will have when they accept",
                        max_length=20,
                        verbose_name="role",
                    ),
                ),
                (
                    "token",
                    models.CharField(
                        db_index=True,
                        help_text="Unique token for accepting the invitation",
                        max_length=64,
                        unique=True,
                        verbose_name="token",
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        help_text="Timestamp when the invitation expires",
                        verbose_name="expires at",
                    ),
                ),
                (
                    "accepted_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp when the invitation was accepted",
                        null=True,
                        verbose_name="accepted at",
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        help_text="User who sent the invitation",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sent_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        help_text="Team the user is invited to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invitations",
                        to="teams.team",
                    ),
                ),
            ],
            options={
                "verbose_name": "team invitation",
                "verbose_name_plural": "team invitations",
                "db_table": "team_invitations",
                "ordering": ["-created_at"],
            },
        ),
    ]
