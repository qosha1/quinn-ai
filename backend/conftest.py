"""
Pytest configuration and fixtures.

This file is automatically discovered by pytest and provides
global fixtures and configuration for all tests.

The comprehensive test fixtures are located in tests/conftest.py.
This file provides minimal setup for backward compatibility.
"""

import pytest
from django.conf import settings
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """
    Enable database access for all tests.

    This fixture is automatically used for all tests.
    """
    pass


@pytest.fixture(autouse=True)
def media_storage(settings, tmpdir):
    """
    Use temporary directory for media files during tests.
    """
    settings.MEDIA_ROOT = tmpdir.strpath
