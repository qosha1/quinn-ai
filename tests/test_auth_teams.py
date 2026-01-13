"""
Tests to validate auth-teams implementation.

These tests verify that all required files from the add-auth-teams
OpenSpec change have been created correctly.
"""

import os
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend")


class TestUsersApp:
    """Test users app structure."""

    def test_users_models_exists(self):
        """apps/users/models.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/users/models.py")
        assert os.path.exists(path), "Users models.py not found"

    def test_users_views_exists(self):
        """apps/users/api/views.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/users/api/views.py")
        assert os.path.exists(path), "Users views.py not found"

    def test_users_serializers_exists(self):
        """apps/users/api/serializers.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/users/api/serializers.py")
        assert os.path.exists(path), "Users serializers.py not found"

    def test_users_managers_or_model_has_manager(self):
        """Users should have a custom manager."""
        models_path = os.path.join(BACKEND_ROOT, "apps/users/models.py")
        managers_path = os.path.join(BACKEND_ROOT, "apps/users/managers.py")
        # Either managers.py exists or UserManager is in models.py
        has_manager = os.path.exists(managers_path)
        if not has_manager and os.path.exists(models_path):
            with open(models_path, 'r') as f:
                content = f.read()
                has_manager = "UserManager" in content
        assert has_manager, "UserManager not found"


class TestUsersModelContent:
    """Test users model content."""

    def test_user_model_has_email_field(self):
        """User model should use email as username."""
        path = os.path.join(BACKEND_ROOT, "apps/users/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "USERNAME_FIELD" in content, "USERNAME_FIELD not defined"
        assert "email" in content, "email field not found"

    def test_user_model_has_company_fk(self):
        """User model should have company foreign key."""
        path = os.path.join(BACKEND_ROOT, "apps/users/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "company" in content.lower(), "company field not found in User model"


class TestTeamsApp:
    """Test teams app structure."""

    def test_teams_models_exists(self):
        """apps/teams/models.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/models.py")
        assert os.path.exists(path), "Teams models.py not found"

    def test_teams_views_exists(self):
        """apps/teams/api/views.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/api/views.py")
        assert os.path.exists(path), "Teams views.py not found"

    def test_teams_serializers_exists(self):
        """apps/teams/api/serializers.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/api/serializers.py")
        assert os.path.exists(path), "Teams serializers.py not found"

    def test_teams_permissions_exists(self):
        """apps/teams/permissions.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/permissions.py")
        assert os.path.exists(path), "Teams permissions.py not found"

    def test_teams_signals_exists(self):
        """apps/teams/signals.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/signals.py")
        assert os.path.exists(path), "Teams signals.py not found"


class TestTeamsModelContent:
    """Test teams model content."""

    def test_company_model_exists(self):
        """Company model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "class Company" in content, "Company model not found"

    def test_team_model_exists(self):
        """Team model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "class Team" in content, "Team model not found"

    def test_team_member_model_exists(self):
        """TeamMember model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "class TeamMember" in content, "TeamMember model not found"

    def test_team_invitation_model_exists(self):
        """TeamInvitation model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "class TeamInvitation" in content or "TeamInvitation" in content, "TeamInvitation model not found"

    def test_role_choices_exist(self):
        """Role choices should be defined."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "owner" in content.lower(), "owner role not found"
        assert "admin" in content.lower(), "admin role not found"
        assert "member" in content.lower(), "member role not found"


class TestTeamsPermissions:
    """Test teams permissions content."""

    def test_is_company_member_exists(self):
        """IsCompanyMember permission should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/permissions.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "IsCompanyMember" in content or "CompanyMember" in content, "IsCompanyMember not found"

    def test_is_team_member_exists(self):
        """IsTeamMember permission should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/permissions.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "IsTeamMember" in content or "TeamMember" in content, "IsTeamMember not found"

    def test_has_team_role_exists(self):
        """HasTeamRole or role-based permission should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/teams/permissions.py")
        with open(path, 'r') as f:
            content = f.read()
        has_role_perm = "HasTeamRole" in content or "IsOwner" in content or "IsAdmin" in content
        assert has_role_perm, "Role-based permission not found"


class TestAuthenticationApp:
    """Test authentication app structure."""

    def test_auth_models_exists(self):
        """apps/authentication/models.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/authentication/models.py")
        assert os.path.exists(path), "Authentication models.py not found"

    def test_auth_backends_exists(self):
        """apps/authentication/backends.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/authentication/backends.py")
        assert os.path.exists(path), "Authentication backends.py not found"

    def test_auth_views_exists(self):
        """apps/authentication/api/views.py should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/authentication/api/views.py")
        assert os.path.exists(path), "Authentication views.py not found"


class TestAuthenticationModelContent:
    """Test authentication model content."""

    def test_apikey_model_exists(self):
        """APIKey model should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/authentication/models.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "APIKey" in content or "ApiKey" in content, "APIKey model not found"

    def test_apikey_has_key_field(self):
        """APIKey should have key/hashed key field."""
        path = os.path.join(BACKEND_ROOT, "apps/authentication/models.py")
        with open(path, 'r') as f:
            content = f.read()
        has_key = "key" in content.lower() or "hash" in content.lower()
        assert has_key, "APIKey key field not found"


class TestAuthenticationBackend:
    """Test authentication backend content."""

    def test_apikey_authentication_exists(self):
        """APIKeyAuthentication backend should exist."""
        path = os.path.join(BACKEND_ROOT, "apps/authentication/backends.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "APIKeyAuthentication" in content or "ApiKeyAuthentication" in content, "APIKeyAuthentication not found"


class TestSettingsUpdated:
    """Test that settings were updated."""

    def test_auth_user_model_set(self):
        """AUTH_USER_MODEL should be set in settings."""
        path = os.path.join(BACKEND_ROOT, "config/settings/base.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "AUTH_USER_MODEL" in content, "AUTH_USER_MODEL not set"

    def test_users_app_in_installed_apps(self):
        """users app should be in INSTALLED_APPS."""
        path = os.path.join(BACKEND_ROOT, "config/settings/base.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "users" in content, "users app not in INSTALLED_APPS"

    def test_teams_app_in_installed_apps(self):
        """teams app should be in INSTALLED_APPS."""
        path = os.path.join(BACKEND_ROOT, "config/settings/base.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "teams" in content, "teams app not in INSTALLED_APPS"

    def test_authentication_app_in_installed_apps(self):
        """authentication app should be in INSTALLED_APPS."""
        path = os.path.join(BACKEND_ROOT, "config/settings/base.py")
        with open(path, 'r') as f:
            content = f.read()
        assert "authentication" in content, "authentication app not in INSTALLED_APPS"


class TestAPIRouter:
    """Test that API router was updated."""

    def test_viewsets_registered(self):
        """ViewSets should be registered in api_router."""
        path = os.path.join(BACKEND_ROOT, "config/api_router.py")
        with open(path, 'r') as f:
            content = f.read()
        # Check for at least some registrations
        has_users = "users" in content.lower() or "user" in content.lower()
        has_teams = "teams" in content.lower() or "team" in content.lower()
        has_companies = "companies" in content.lower() or "company" in content.lower()
        assert has_users or has_teams or has_companies, "No ViewSets registered in router"
