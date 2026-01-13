"""
Tests for Authentication app.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.teams.models import Company
from apps.authentication.models import APIKey

User = get_user_model()


class APIKeyTests(TestCase):
    """Tests for APIKey model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.company = Company.objects.create(
            name="Test Company",
            owner=self.user
        )

    def test_create_api_key(self):
        """Test creating an API key."""
        api_key, raw_key = APIKey.create_key(
            name="Test Key",
            company=self.company,
            created_by=self.user
        )

        self.assertEqual(api_key.name, "Test Key")
        self.assertEqual(api_key.company, self.company)
        self.assertEqual(api_key.created_by, self.user)
        self.assertTrue(api_key.is_active)
        self.assertIsNotNone(raw_key)

    def test_api_key_verification(self):
        """Test API key verification."""
        api_key, raw_key = APIKey.create_key(
            name="Test Key",
            company=self.company,
            created_by=self.user
        )

        # Verify with correct key
        self.assertTrue(api_key.verify_key(raw_key))

        # Verify with incorrect key
        self.assertFalse(api_key.verify_key("wrong_key"))

    def test_api_key_is_valid(self):
        """Test API key validity checks."""
        api_key, raw_key = APIKey.create_key(
            name="Test Key",
            company=self.company,
            created_by=self.user
        )

        # Should be valid initially
        self.assertTrue(api_key.is_valid())

        # Should be invalid when deactivated
        api_key.is_active = False
        self.assertFalse(api_key.is_valid())
