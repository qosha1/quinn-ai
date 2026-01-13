"""
Test settings.

Usage:
    DJANGO_SETTINGS_MODULE=config.settings.test
    pytest
"""

from .base import *  # noqa: F403, F401

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Use in-memory database for faster tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Use MD5 password hasher for faster tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Celery - Always eager in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Email - Use memory backend for tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Disable migrations for faster tests (optional)
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#
#     def __getitem__(self, item):
#         return None
#
# MIGRATION_MODULES = DisableMigrations()

# Logging - Reduce noise in tests
LOGGING["handlers"]["console"]["level"] = "ERROR"  # noqa: F405
LOGGING["loggers"]["django"]["level"] = "ERROR"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "ERROR"  # noqa: F405

# Media files - Use temporary directory for tests
MEDIA_ROOT = "/tmp/test_media"  # noqa: S108

# CORS - Allow all for testing
CORS_ALLOW_ALL_ORIGINS = True
