"""
Authentication tests for the B2B SaaS API.

Tests cover:
- User registration
- JWT token obtain (login)
- JWT token refresh
- JWT token verify
- API key authentication
- Invalid credentials handling
- Missing authentication handling

Usage:
    pytest tests/test_authentication.py -v
"""

import pytest
from django.urls import reverse
from rest_framework import status

from apps.users.models import User
from apps.authentication.models import APIKey


@pytest.mark.django_db
class TestUserRegistration:
    """Tests for user registration endpoint."""

    def test_register_user_success(self, api_client):
        """
        Test successful user registration with valid data.

        Verifies that a new user can register with email and password,
        and the response contains the expected user data.
        """
        url = "/api/v1/users/"
        data = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "newuser@example.com"
        assert response.data["first_name"] == "New"
        assert response.data["last_name"] == "User"
        assert "password" not in response.data
        assert User.objects.filter(email="newuser@example.com").exists()

    def test_register_user_password_mismatch(self, api_client):
        """
        Test registration fails when passwords do not match.

        Verifies proper validation error is returned.
        """
        url = "/api/v1/users/"
        data = {
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "password_confirm": "DifferentPass123!",
            "first_name": "New",
            "last_name": "User",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password_confirm" in response.data

    def test_register_user_weak_password(self, api_client):
        """
        Test registration fails with weak password.

        Django password validators should reject short/simple passwords.
        """
        url = "/api/v1/users/"
        data = {
            "email": "newuser@example.com",
            "password": "123",
            "password_confirm": "123",
            "first_name": "New",
            "last_name": "User",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_register_user_duplicate_email(self, api_client, user):
        """
        Test registration fails with already registered email.

        Verifies that duplicate emails are rejected.
        """
        url = "/api/v1/users/"
        data = {
            "email": user.email,
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    def test_register_user_invalid_email(self, api_client):
        """
        Test registration fails with invalid email format.
        """
        url = "/api/v1/users/"
        data = {
            "email": "not-an-email",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    def test_register_user_missing_required_fields(self, api_client):
        """
        Test registration fails with missing required fields.
        """
        url = "/api/v1/users/"
        data = {
            "first_name": "New",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data
        assert "password" in response.data


@pytest.mark.django_db
class TestJWTTokenObtain:
    """Tests for JWT token obtain (login) endpoint."""

    def test_obtain_token_success(self, api_client, user_factory):
        """
        Test successful token obtain with valid credentials.

        Verifies that access and refresh tokens are returned.
        """
        password = "TestPassword123!"
        user = user_factory(email="login@example.com", password=password)

        url = "/api/v1/auth/token/"
        data = {
            "email": user.email,
            "password": password,
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_obtain_token_invalid_password(self, api_client, user):
        """
        Test token obtain fails with incorrect password.

        Verifies 401 response with proper error message.
        """
        url = "/api/v1/auth/token/"
        data = {
            "email": user.email,
            "password": "WrongPassword123!",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_obtain_token_nonexistent_user(self, api_client):
        """
        Test token obtain fails for non-existent user.

        Should return 401 to prevent user enumeration.
        """
        url = "/api/v1/auth/token/"
        data = {
            "email": "nonexistent@example.com",
            "password": "SomePassword123!",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_obtain_token_inactive_user(self, api_client, user_factory):
        """
        Test token obtain fails for inactive user.
        """
        password = "TestPassword123!"
        user = user_factory(
            email="inactive@example.com",
            password=password,
            is_active=False
        )

        url = "/api/v1/auth/token/"
        data = {
            "email": user.email,
            "password": password,
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_obtain_token_missing_credentials(self, api_client):
        """
        Test token obtain fails with missing credentials.
        """
        url = "/api/v1/auth/token/"
        data = {}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestJWTTokenRefresh:
    """Tests for JWT token refresh endpoint."""

    def test_refresh_token_success(self, api_client, jwt_refresh_token):
        """
        Test successful token refresh with valid refresh token.

        Verifies that a new access token is returned.
        """
        url = "/api/v1/auth/token/refresh/"
        data = {
            "refresh": jwt_refresh_token,
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_refresh_token_invalid(self, api_client):
        """
        Test token refresh fails with invalid refresh token.
        """
        url = "/api/v1/auth/token/refresh/"
        data = {
            "refresh": "invalid.refresh.token",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_token_missing(self, api_client):
        """
        Test token refresh fails with missing refresh token.
        """
        url = "/api/v1/auth/token/refresh/"
        data = {}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestJWTTokenVerify:
    """Tests for JWT token verify endpoint."""

    def test_verify_token_success(self, api_client, jwt_token):
        """
        Test successful token verification with valid token.
        """
        url = "/api/v1/auth/token/verify/"
        data = {
            "token": jwt_token,
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK

    def test_verify_token_invalid(self, api_client):
        """
        Test token verification fails with invalid token.
        """
        url = "/api/v1/auth/token/verify/"
        data = {
            "token": "invalid.access.token",
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_verify_token_missing(self, api_client):
        """
        Test token verification fails with missing token.
        """
        url = "/api/v1/auth/token/verify/"
        data = {}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestAPIKeyAuthentication:
    """Tests for API key authentication."""

    def test_api_key_auth_success(self, api_key_client, company):
        """
        Test successful authentication with valid API key.

        Verifies that requests with valid X-API-Key header succeed.
        """
        url = "/api/v1/users/me/"

        response = api_key_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_api_key_auth_invalid_key(self, api_client, company):
        """
        Test authentication fails with invalid API key.
        """
        api_client.credentials(HTTP_X_API_KEY="invalid_api_key_12345678")
        url = "/api/v1/users/me/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_api_key_auth_revoked_key(self, api_client, company, owner_user):
        """
        Test authentication fails with revoked (inactive) API key.
        """
        api_key, raw_key = APIKey.create_key(
            name="Revoked Key",
            company=company,
            created_by=owner_user,
            scopes=["read"],
        )
        api_key.is_active = False
        api_key.save()

        api_client.credentials(HTTP_X_API_KEY=raw_key)
        url = "/api/v1/users/me/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_api_key_auth_expired_key(self, api_client, company, owner_user):
        """
        Test authentication fails with expired API key.
        """
        from django.utils import timezone
        from datetime import timedelta

        api_key, raw_key = APIKey.create_key(
            name="Expired Key",
            company=company,
            created_by=owner_user,
            scopes=["read"],
            expires_at=timezone.now() - timedelta(days=1),
        )

        api_client.credentials(HTTP_X_API_KEY=raw_key)
        url = "/api/v1/users/me/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_api_key_updates_last_used(self, api_client, company, owner_user):
        """
        Test that successful API key auth updates last_used_at timestamp.
        """
        api_key, raw_key = APIKey.create_key(
            name="Test Key",
            company=company,
            created_by=owner_user,
            scopes=["read"],
        )

        assert api_key.last_used_at is None

        api_client.credentials(HTTP_X_API_KEY=raw_key)
        url = "/api/v1/users/me/"

        response = api_client.get(url)

        api_key.refresh_from_db()
        assert api_key.last_used_at is not None


@pytest.mark.django_db
class TestUnauthenticatedAccess:
    """Tests for unauthenticated access to protected endpoints."""

    def test_protected_endpoint_no_auth(self, api_client):
        """
        Test that protected endpoints return 401 without authentication.
        """
        url = "/api/v1/users/me/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_protected_endpoint_invalid_auth_header(self, api_client):
        """
        Test that invalid Authorization header format returns 401.
        """
        api_client.credentials(HTTP_AUTHORIZATION="Invalid header format")
        url = "/api/v1/users/me/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_protected_endpoint_malformed_token(self, api_client):
        """
        Test that malformed JWT token returns 401.
        """
        api_client.credentials(HTTP_AUTHORIZATION="Bearer malformed.token.here")
        url = "/api/v1/users/me/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_registration_is_public(self, api_client):
        """
        Test that user registration endpoint is publicly accessible.
        """
        url = "/api/v1/users/"
        data = {
            "email": "public@example.com",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "Public",
            "last_name": "User",
        }

        response = api_client.post(url, data, format="json")

        # Should succeed without authentication
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestUserProfile:
    """Tests for user profile endpoints."""

    def test_get_current_user_profile(self, authenticated_client, user):
        """
        Test retrieving current user profile.
        """
        url = "/api/v1/users/me/"

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == user.email
        assert response.data["first_name"] == user.first_name

    def test_update_current_user_profile(self, authenticated_client, user):
        """
        Test updating current user profile.
        """
        url = "/api/v1/users/me/"
        data = {
            "first_name": "Updated",
            "last_name": "Name",
        }

        response = authenticated_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == "Updated"
        assert user.last_name == "Name"

    def test_change_password_success(self, authenticated_client, user_factory):
        """
        Test successful password change.
        """
        old_password = "OldPassword123!"
        new_password = "NewSecurePass456!"
        user = user_factory(email="pwchange@example.com", password=old_password)

        # Re-authenticate with the specific user
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        authenticated_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

        url = "/api/v1/users/me/change-password/"
        data = {
            "old_password": old_password,
            "new_password": new_password,
            "new_password_confirm": new_password,
        }

        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK

        # Verify new password works
        user.refresh_from_db()
        assert user.check_password(new_password)

    def test_change_password_wrong_old_password(self, authenticated_client, user):
        """
        Test password change fails with incorrect old password.
        """
        url = "/api/v1/users/me/change-password/"
        data = {
            "old_password": "WrongOldPassword123!",
            "new_password": "NewSecurePass456!",
            "new_password_confirm": "NewSecurePass456!",
        }

        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "old_password" in response.data

    def test_change_password_new_password_mismatch(self, authenticated_client, user_factory):
        """
        Test password change fails when new passwords don't match.
        """
        old_password = "OldPassword123!"
        user = user_factory(email="pwchange2@example.com", password=old_password)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        authenticated_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

        url = "/api/v1/users/me/change-password/"
        data = {
            "old_password": old_password,
            "new_password": "NewSecurePass456!",
            "new_password_confirm": "DifferentPass789!",
        }

        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "new_password_confirm" in response.data
