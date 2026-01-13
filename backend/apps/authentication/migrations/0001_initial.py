"""
Initial migration for authentication app.
"""

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.contrib.postgres.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("teams", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="APIKey",
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
                        help_text="Descriptive name for this API key",
                        max_length=255,
                        verbose_name="name",
                    ),
                ),
                (
                    "key",
                    models.CharField(
                        db_index=True,
                        help_text="Hashed API key",
                        max_length=255,
                        unique=True,
                        verbose_name="key",
                    ),
                ),
                (
                    "prefix",
                    models.CharField(
                        db_index=True,
                        help_text="First 8 characters of the key for identification",
                        max_length=8,
                        verbose_name="prefix",
                    ),
                ),
                (
                    "scopes",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=100),
                        blank=True,
                        default=list,
                        help_text="List of scopes/permissions for this API key",
                        size=None,
                    ),
                ),
                (
                    "last_used_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp when the API key was last used",
                        null=True,
                        verbose_name="last used at",
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp when the API key expires",
                        null=True,
                        verbose_name="expires at",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Whether this API key is currently active",
                        verbose_name="active",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        help_text="Company this API key belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="api_keys",
                        to="teams.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        help_text="User who created this API key",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="created_api_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "API key",
                "verbose_name_plural": "API keys",
                "db_table": "api_keys",
                "ordering": ["-created_at"],
            },
        ),
    ]
