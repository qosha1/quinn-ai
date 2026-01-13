"""
Tests to validate Django backend core implementation.

These tests verify that all required files from the add-backend-django-core
OpenSpec change have been created correctly.
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")


class TestProjectStructure:
    """Test Django project structure."""

    def test_manage_py_exists(self):
        """manage.py should exist."""
        path = os.path.join(BACKEND_ROOT, "manage.py")
        assert os.path.exists(path), "manage.py not found"

    def test_conftest_exists(self):
        """conftest.py should exist."""
        path = os.path.join(BACKEND_ROOT, "conftest.py")
        assert os.path.exists(path), "conftest.py not found"

    def test_pyproject_toml_exists(self):
        """pyproject.toml should exist."""
        path = os.path.join(BACKEND_ROOT, "pyproject.toml")
        assert os.path.exists(path), "pyproject.toml not found"


class TestConfigModule:
    """Test Django config module."""

    def test_settings_base_exists(self):
        """config/settings/base.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/settings/base.py")
        assert os.path.exists(path), "Settings base.py not found"

    def test_settings_local_exists(self):
        """config/settings/local.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/settings/local.py")
        assert os.path.exists(path), "Settings local.py not found"

    def test_settings_production_exists(self):
        """config/settings/production.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/settings/production.py")
        assert os.path.exists(path), "Settings production.py not found"

    def test_settings_test_exists(self):
        """config/settings/test.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/settings/test.py")
        assert os.path.exists(path), "Settings test.py not found"

    def test_urls_exists(self):
        """config/urls.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/urls.py")
        assert os.path.exists(path), "urls.py not found"

    def test_api_router_exists(self):
        """config/api_router.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/api_router.py")
        assert os.path.exists(path), "api_router.py not found"

    def test_celery_app_exists(self):
        """config/celery_app.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/celery_app.py")
        assert os.path.exists(path), "celery_app.py not found"

    def test_asgi_exists(self):
        """config/asgi.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/asgi.py")
        assert os.path.exists(path), "asgi.py not found"

    def test_wsgi_exists(self):
        """config/wsgi.py should exist."""
        path = os.path.join(BACKEND_ROOT, "config/wsgi.py")
        assert os.path.exists(path), "wsgi.py not found"


class TestCoreApp:
    """Test core Django application."""

    def test_core_models_exists(self):
        """apps/core/models.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/core/models.py")
        assert os.path.exists(path), "Core models.py not found"

    def test_core_apps_exists(self):
        """apps/core/apps.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/core/apps.py")
        assert os.path.exists(path), "Core apps.py not found"

    def test_core_utils_exists(self):
        """apps/core/utils.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/core/utils.py")
        assert os.path.exists(path), "Core utils.py not found"


class TestCoreAPI:
    """Test core API module."""

    def test_api_views_exists(self):
        """apps/core/api/views.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/core/api/views.py")
        assert os.path.exists(path), "API views.py not found"

    def test_api_mixins_exists(self):
        """apps/core/api/mixins.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/core/api/mixins.py")
        assert os.path.exists(path), "API mixins.py not found"


class TestRequirements:
    """Test requirements files."""

    def test_base_requirements_exists(self):
        """requirements/base.txt should exist."""
        path = os.path.join(BACKEND_ROOT, "requirements/base.txt")
        assert os.path.exists(path), "Base requirements not found"

    def test_local_requirements_exists(self):
        """requirements/local.txt should exist."""
        path = os.path.join(BACKEND_ROOT, "requirements/local.txt")
        assert os.path.exists(path), "Local requirements not found"

    def test_production_requirements_exists(self):
        """requirements/production.txt should exist."""
        path = os.path.join(BACKEND_ROOT, "requirements/production.txt")
        assert os.path.exists(path), "Production requirements not found"


class TestBaseModelContent:
    """Test BaseModel implementation content."""

    def test_basemodel_has_uuid_field(self):
        """BaseModel should use UUID primary key."""
        path = os.path.join(BACKEND_ROOT, "apps/core/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "UUIDField" in content, "BaseModel should use UUID field"
        assert "primary_key=True" in content, "UUID should be primary key"

    def test_basemodel_has_timestamps(self):
        """BaseModel should have created_at and updated_at."""
        path = os.path.join(BACKEND_ROOT, "apps/core/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "created_at" in content, "BaseModel should have created_at"
        assert "updated_at" in content, "BaseModel should have updated_at"
        assert "auto_now_add" in content, "created_at should use auto_now_add"
        assert "auto_now" in content, "updated_at should use auto_now"


class TestHealthCheckEndpoint:
    """Test health check endpoint implementation."""

    def test_health_check_view_exists(self):
        """Health check view should exist in views.py."""
        path = os.path.join(BACKEND_ROOT, "apps/core/api/views.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "health_check" in content, "health_check view not found"
        assert "AllowAny" in content, "Health check should allow any access"
