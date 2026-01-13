"""
Teams app configuration.
"""

from django.apps import AppConfig


class TeamsConfig(AppConfig):
    """Configuration for Teams app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.teams"
    verbose_name = "Teams"

    def ready(self):
        """Import signals when app is ready."""
        import apps.teams.signals  # noqa: F401
