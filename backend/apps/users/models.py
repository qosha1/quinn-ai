"""
User models for authentication and profile management.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.users.managers import UserManager


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """
    Custom user model with email as the username field.

    Features:
    - Email-based authentication (no username)
    - Email verification support
    - Company association for multi-tenancy
    - Standard Django auth integration
    """

    email = models.EmailField(
        _("email address"),
        unique=True,
        db_index=True,
        help_text=_("User's email address, used for authentication")
    )
    first_name = models.CharField(
        _("first name"),
        max_length=150,
        blank=True,
        help_text=_("User's first name")
    )
    last_name = models.CharField(
        _("last name"),
        max_length=150,
        blank=True,
        help_text=_("User's last name")
    )
    is_email_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Whether the user's email address has been verified")
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into admin site")
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Designates whether this user should be treated as active")
    )
    company = models.ForeignKey(
        "teams.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text=_("User's primary company")
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        db_table = "users"
        ordering = ["-created_at"]

    def __str__(self):
        """Return string representation of the user."""
        return self.email

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name or self.email
