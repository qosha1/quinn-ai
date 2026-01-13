"""
Tests to validate Docker infrastructure implementation.

These tests verify that all required files from the add-docker-infrastructure
OpenSpec change have been created correctly.
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestDockerComposeFiles:
    """Test Docker Compose configuration files exist and are valid."""

    def test_local_compose_exists(self):
        """docker-compose.local.yml should exist."""
        path = os.path.join(PROJECT_ROOT, "docker-compose.local.yml")
        assert os.path.exists(path), "docker-compose.local.yml not found"

    def test_production_compose_exists(self):
        """docker-compose.production.yml should exist."""
        path = os.path.join(PROJECT_ROOT, "docker-compose.production.yml")
        assert os.path.exists(path), "docker-compose.production.yml not found"


class TestLocalDjangoDocker:
    """Test local Django Docker configuration."""

    def test_dockerfile_exists(self):
        """compose/local/django/Dockerfile should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/local/django/Dockerfile")
        assert os.path.exists(path), "Local Django Dockerfile not found"

    def test_start_script_exists(self):
        """compose/local/django/start should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/local/django/start")
        assert os.path.exists(path), "Local Django start script not found"

    def test_entrypoint_exists(self):
        """compose/local/django/entrypoint should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/local/django/entrypoint")
        assert os.path.exists(path), "Local Django entrypoint not found"


class TestLocalNginxDocker:
    """Test local Nginx Docker configuration."""

    def test_dockerfile_exists(self):
        """compose/local/nginx/Dockerfile should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/local/nginx/Dockerfile")
        assert os.path.exists(path), "Local Nginx Dockerfile not found"

    def test_nginx_conf_exists(self):
        """compose/local/nginx/nginx.conf should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/local/nginx/nginx.conf")
        assert os.path.exists(path), "Local Nginx config not found"


class TestLocalNodeDocker:
    """Test local Node Docker configuration."""

    def test_dockerfile_exists(self):
        """compose/local/node/Dockerfile should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/local/node/Dockerfile")
        assert os.path.exists(path), "Local Node Dockerfile not found"


class TestProductionDjangoDocker:
    """Test production Django Docker configuration."""

    def test_dockerfile_exists(self):
        """compose/production/django/Dockerfile should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/production/django/Dockerfile")
        assert os.path.exists(path), "Production Django Dockerfile not found"

    def test_start_script_exists(self):
        """compose/production/django/start should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/production/django/start")
        assert os.path.exists(path), "Production Django start script not found"


class TestProductionTraefikDocker:
    """Test production Traefik configuration."""

    def test_traefik_yml_exists(self):
        """compose/production/traefik/traefik.yml should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/production/traefik/traefik.yml")
        assert os.path.exists(path), "Traefik config not found"

    def test_dynamic_yml_exists(self):
        """compose/production/traefik/dynamic.yml should exist."""
        path = os.path.join(PROJECT_ROOT, "compose/production/traefik/dynamic.yml")
        assert os.path.exists(path), "Traefik dynamic config not found"


class TestEnvironmentTemplates:
    """Test environment template files."""

    def test_local_django_example_exists(self):
        """.envs/.local/.django.example should exist."""
        path = os.path.join(PROJECT_ROOT, ".envs/.local/.django.example")
        assert os.path.exists(path), "Local Django env example not found"

    def test_local_postgres_example_exists(self):
        """.envs/.local/.postgres.example should exist."""
        path = os.path.join(PROJECT_ROOT, ".envs/.local/.postgres.example")
        assert os.path.exists(path), "Local Postgres env example not found"

    def test_production_django_example_exists(self):
        """.envs/.production/.django.example should exist."""
        path = os.path.join(PROJECT_ROOT, ".envs/.production/.django.example")
        assert os.path.exists(path), "Production Django env example not found"

    def test_production_postgres_example_exists(self):
        """.envs/.production/.postgres.example should exist."""
        path = os.path.join(PROJECT_ROOT, ".envs/.production/.postgres.example")
        assert os.path.exists(path), "Production Postgres env example not found"


class TestDeveloperTools:
    """Test developer tooling files."""

    def test_makefile_exists(self):
        """Makefile should exist."""
        path = os.path.join(PROJECT_ROOT, "Makefile")
        assert os.path.exists(path), "Makefile not found"

    def test_dockerignore_exists(self):
        """.dockerignore should exist."""
        path = os.path.join(PROJECT_ROOT, ".dockerignore")
        assert os.path.exists(path), ".dockerignore not found"
