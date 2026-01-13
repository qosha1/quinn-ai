"""
Tests for Teams app.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.teams.models import Company, Team, TeamMember

User = get_user_model()


class CompanyModelTests(TestCase):
    """Tests for Company model."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="testpass123"
        )

    def test_create_company(self):
        """Test creating a company."""
        company = Company.objects.create(
            name="Test Company",
            owner=self.user
        )

        self.assertEqual(company.name, "Test Company")
        self.assertEqual(company.owner, self.user)
        self.assertTrue(company.slug)

    def test_company_auto_creates_team(self):
        """Test that creating a company auto-creates default team."""
        company = Company.objects.create(
            name="Test Company",
            owner=self.user
        )

        # Check default team was created
        self.assertEqual(company.teams.count(), 1)
        default_team = company.teams.first()
        self.assertEqual(default_team.name, "Default Team")

        # Check owner was added as team member
        membership = TeamMember.objects.filter(
            user=self.user,
            team=default_team
        ).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, TeamMember.Role.OWNER)


class TeamMemberTests(TestCase):
    """Tests for TeamMember model."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="testpass123"
        )
        self.company = Company.objects.create(
            name="Test Company",
            owner=self.owner
        )
        self.team = self.company.teams.first()

    def test_add_team_member(self):
        """Test adding a member to a team."""
        member_user = User.objects.create_user(
            email="member@example.com",
            password="testpass123"
        )

        membership = TeamMember.objects.create(
            user=member_user,
            team=self.team,
            role=TeamMember.Role.MEMBER,
            invited_by=self.owner
        )

        self.assertEqual(membership.user, member_user)
        self.assertEqual(membership.team, self.team)
        self.assertEqual(membership.role, TeamMember.Role.MEMBER)
        self.assertEqual(membership.invited_by, self.owner)
