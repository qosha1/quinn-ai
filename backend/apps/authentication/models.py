"""
Models for API key authentication.
"""

import secrets
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


def generate_api_key():
    """Generate a secure random API key."""
    return secrets.token_urlsafe(32)


class APIKey(BaseModel):
    """
    Model for API key authentication.

    API keys are used for server-to-server authentication.
    Keys are hashed before storage for security.
    """

    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("Descriptive name for this API key")
    )
    key = models.CharField(
        _("key"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Hashed API key")
    )
    prefix = models.CharField(
        _("prefix"),
        max_length=8,
        db_index=True,
        help_text=_("First 8 characters of the key for identification")
    )
    company = models.ForeignKey(
        "teams.Company",
        on_delete=models.CASCADE,
        related_name="api_keys",
        help_text=_("Company this API key belongs to")
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_api_keys",
        help_text=_("User who created this API key")
    )
    scopes = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
        help_text=_("List of scopes/permissions for this API key")
    )
    last_used_at = models.DateTimeField(
        _("last used at"),
        null=True,
        blank=True,
        help_text=_("Timestamp when the API key was last used")
    )
    expires_at = models.DateTimeField(
        _("expires at"),
        null=True,
        blank=True,
        help_text=_("Timestamp when the API key expires")
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Whether this API key is currently active")
    )

    class Meta:
        verbose_name = _("API key")
        verbose_name_plural = _("API keys")
        db_table = "api_keys"
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the API key."""
        return f"{self.name} ({self.prefix}...)"

    def save(self, *args, **kwargs):
        """Hash the key before saving if it's a new instance."""
        # If this is a new key (not hashed yet) or key is being updated
        if not self.pk or not self.key.startswith("pbkdf2_"):
            # Store prefix before hashing
            if not self.prefix:
                self.prefix = self.key[:8]
            # Hash the key
            self.key = make_password(self.key)
        super().save(*args, **kwargs)

    def verify_key(self, raw_key):
        """
        Verify a raw API key against the hashed key.

        Args:
            raw_key: The unhashed API key to verify

        Returns:
            bool: True if the key matches, False otherwise
        """
        return check_password(raw_key, self.key)

    def is_valid(self):
        """
        Check if the API key is valid for use.

        Returns:
            bool: True if the key is active and not expired
        """
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def update_last_used(self):
        """Update the last_used_at timestamp."""
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

    @classmethod
    def create_key(cls, name, company, created_by, scopes=None, expires_at=None):
        """
        Create a new API key and return both the instance and raw key.

        Args:
            name: Name for the API key
            company: Company the key belongs to
            created_by: User creating the key
            scopes: List of scopes for the key
            expires_at: Expiration timestamp

        Returns:
            tuple: (APIKey instance, raw_key string)
        """
        raw_key = generate_api_key()
        api_key = cls(
            name=name,
            key=raw_key,  # Will be hashed in save()
            company=company,
            created_by=created_by,
            scopes=scopes or [],
            expires_at=expires_at,
        )
        api_key.save()
        return api_key, raw_key
