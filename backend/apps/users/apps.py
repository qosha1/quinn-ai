"""
Users app configuration.
"""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """Configuration for Users app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = "Users"

    def ready(self):
        """Import signals when app is ready."""
        import apps.users.signals  # noqa: F401
