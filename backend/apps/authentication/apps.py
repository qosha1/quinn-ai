"""
Authentication app configuration.
"""

from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    """Configuration for Authentication app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authentication"
    verbose_name = "Authentication"
