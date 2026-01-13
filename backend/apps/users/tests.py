"""
Tests for Users app.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class UserModelTests(TestCase):
    """Tests for User model."""

    def test_create_user(self):
        """Test creating a user with email."""
        email = "test@example.com"
        password = "testpass123"
        user = User.objects.create_user(
            email=email,
            password=password
        )

        self.assertEqual(user.email, email)
        self.assertTrue(user.check_password(password))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_superuser(self):
        """Test creating a superuser."""
        email = "admin@example.com"
        password = "testpass123"
        user = User.objects.create_superuser(
            email=email,
            password=password
        )

        self.assertEqual(user.email, email)
        self.assertTrue(user.check_password(password))
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_email_normalized(self):
        """Test email is normalized."""
        email = "test@EXAMPLE.COM"
        user = User.objects.create_user(email=email, password="test123")
        self.assertEqual(user.email, email.lower())

    def test_user_string_representation(self):
        """Test user string representation."""
        user = User.objects.create_user(
            email="test@example.com",
            password="test123"
        )
        self.assertEqual(str(user), user.email)
