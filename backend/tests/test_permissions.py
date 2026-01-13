"""
Permission tests for the B2B SaaS API.

Tests cover:
- Owner-only actions
- Admin-level permissions
- Member-level access (read-only)
- Viewer restrictions
- Cross-company 404 (not 403) behavior
- Unauthenticated access

Usage:
    pytest tests/test_permissions.py -v
"""

import pytest
from rest_framework import status

from apps.teams.models import Team, TeamMember, TeamInvitation
from apps.authentication.models import APIKey


@pytest.mark.django_db
class TestOwnerOnlyActions:
    """Tests for actions that only company owners can perform."""

    def test_owner_can_update_company(self, owner_client, company):
        """
        Test that company owner can update company settings.
        """
        url = f"/api/v1/companies/{company.id}/"
        data = {"name": "Owner Updated Company"}

        response = owner_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        company.refresh_from_db()
        assert company.name == "Owner Updated Company"

    def test_owner_can_delete_company(self, api_client, company_factory):
        """
        Test that company owner can delete their company.
        """
        company, owner = company_factory(name="Deletable Company", return_owner=True)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(owner)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = f"/api/v1/companies/{company.id}/"

        response = api_client.delete(url)

        # Depending on implementation, might be 204 or may prevent deletion
        # due to related objects
        assert response.status_code in [
            status.HTTP_204_NO_CONTENT,
            status.HTTP_400_BAD_REQUEST,  # If deletion is blocked
        ]

    def test_admin_cannot_update_company(self, admin_client, company):
        """
        Test that admins cannot update company-level settings.

        Company updates should be restricted to owners only.
        """
        url = f"/api/v1/companies/{company.id}/"
        data = {"name": "Admin Attempted Update"}

        response = admin_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_cannot_update_company(self, member_client, company):
        """
        Test that members cannot update company settings.
        """
        url = f"/api/v1/companies/{company.id}/"
        data = {"name": "Member Attempted Update"}

        response = member_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_cannot_update_company(self, viewer_client, company):
        """
        Test that viewers cannot update company settings.
        """
        url = f"/api/v1/companies/{company.id}/"
        data = {"name": "Viewer Attempted Update"}

        response = viewer_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAdminLevelPermissions:
    """Tests for admin-level permissions."""

    def test_admin_can_create_team(self, admin_client, company):
        """
        Test that admin can create teams.
        """
        url = "/api/v1/teams/"
        data = {
            "name": "Admin Created Team",
            "company": str(company.id),
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

    def test_admin_can_update_team(self, admin_client, team):
        """
        Test that admin can update team settings.
        """
        url = f"/api/v1/teams/{team.id}/"
        data = {"name": "Admin Updated Team"}

        response = admin_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK

    def test_admin_can_delete_team(self, admin_client, team_factory, company):
        """
        Test that admin can delete teams.
        """
        team = team_factory(name="Team to Delete", company=company)
        url = f"/api/v1/teams/{team.id}/"

        response = admin_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_admin_can_manage_members(self, admin_client, team, user_factory, company):
        """
        Test that admin can add and remove team members.
        """
        new_user = user_factory(email="admin_add@example.com", company=company)

        # Add member
        url = "/api/v1/team-members/"
        data = {
            "user": str(new_user.id),
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = admin_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Remove member
        membership = TeamMember.objects.get(user=new_user, team=team)
        url = f"/api/v1/team-members/{membership.id}/"

        response = admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_admin_can_manage_invitations(self, admin_client, team):
        """
        Test that admin can create and manage invitations.
        """
        # Create invitation
        url = "/api/v1/team-invitations/"
        data = {
            "email": "admin_invite@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = admin_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Delete invitation
        invitation_id = response.data["id"]
        url = f"/api/v1/team-invitations/{invitation_id}/"

        response = admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_admin_can_manage_api_keys(self, admin_client, company):
        """
        Test that admin can create and manage API keys.
        """
        url = "/api/v1/api-keys/"
        data = {
            "name": "Admin Created Key",
            "scopes": ["read", "write"],
        }

        response = admin_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert "key" in response.data  # Raw key returned on creation


@pytest.mark.django_db
class TestMemberLevelAccess:
    """Tests for member-level access (read-only for most resources)."""

    def test_member_can_list_teams(self, member_client, team):
        """
        Test that members can list teams they have access to.
        """
        url = "/api/v1/teams/"

        response = member_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_member_can_view_team_details(self, member_client, team):
        """
        Test that members can view team details.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = member_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == team.name

    def test_member_can_list_team_members(self, member_client, team):
        """
        Test that members can view team member list.
        """
        url = "/api/v1/team-members/"

        response = member_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_member_cannot_create_team(self, member_client, company):
        """
        Test that members cannot create teams.
        """
        url = "/api/v1/teams/"
        data = {
            "name": "Member Created Team",
            "company": str(company.id),
        }

        response = member_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_cannot_update_team(self, member_client, team):
        """
        Test that members cannot update team settings.
        """
        url = f"/api/v1/teams/{team.id}/"
        data = {"name": "Member Updated Team"}

        response = member_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_cannot_delete_team(self, member_client, team):
        """
        Test that members cannot delete teams.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = member_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_cannot_add_team_members(
        self, member_client, team, user_factory, company
    ):
        """
        Test that members cannot add other members to the team.
        """
        new_user = user_factory(email="member_add@example.com", company=company)

        url = "/api/v1/team-members/"
        data = {
            "user": str(new_user.id),
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = member_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_member_cannot_create_invitations(self, member_client, team):
        """
        Test that members cannot create team invitations.
        """
        url = "/api/v1/team-invitations/"
        data = {
            "email": "member_invite@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = member_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestViewerRestrictions:
    """Tests for viewer restrictions (most restricted role)."""

    def test_viewer_can_list_teams(self, viewer_client, team):
        """
        Test that viewers can still list teams they have access to.
        """
        url = "/api/v1/teams/"

        response = viewer_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_viewer_can_view_team_details(self, viewer_client, team):
        """
        Test that viewers can view team details.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = viewer_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_viewer_cannot_create_team(self, viewer_client, company):
        """
        Test that viewers cannot create teams.
        """
        url = "/api/v1/teams/"
        data = {
            "name": "Viewer Created Team",
            "company": str(company.id),
        }

        response = viewer_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_cannot_update_team(self, viewer_client, team):
        """
        Test that viewers cannot update team settings.
        """
        url = f"/api/v1/teams/{team.id}/"
        data = {"name": "Viewer Updated Team"}

        response = viewer_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_cannot_delete_team(self, viewer_client, team):
        """
        Test that viewers cannot delete teams.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = viewer_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_cannot_manage_members(
        self, viewer_client, team, member_user
    ):
        """
        Test that viewers cannot add or remove members.
        """
        membership = TeamMember.objects.get(user=member_user, team=team)
        url = f"/api/v1/team-members/{membership.id}/"

        # Cannot change role
        response = viewer_client.patch(
            url, {"role": TeamMember.Role.ADMIN}, format="json"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Cannot remove member
        response = viewer_client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_cannot_create_invitations(self, viewer_client, team):
        """
        Test that viewers cannot create invitations.
        """
        url = "/api/v1/team-invitations/"
        data = {
            "email": "viewer_invite@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = viewer_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCrossCompany404Behavior:
    """
    Tests for cross-company isolation returning 404 instead of 403.

    When users try to access resources from other companies,
    they should receive 404 (not found) rather than 403 (forbidden)
    to prevent information disclosure.
    """

    def test_other_company_team_returns_404(self, other_company_client, team):
        """
        Test that accessing other company's team returns 404.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = other_company_client.get(url)

        # Should be 404, not 403, to prevent info leakage
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_other_company_team_update_returns_404(
        self, other_company_client, team
    ):
        """
        Test that updating other company's team returns 404.
        """
        url = f"/api/v1/teams/{team.id}/"
        data = {"name": "Cross-company Update"}

        response = other_company_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_other_company_team_delete_returns_404(
        self, other_company_client, team
    ):
        """
        Test that deleting other company's team returns 404.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = other_company_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_other_company_invitation_returns_404(
        self, other_company_client, invitation
    ):
        """
        Test that accessing other company's invitation returns 404.
        """
        url = f"/api/v1/team-invitations/{invitation.id}/"

        response = other_company_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_other_company_team_member_returns_404(
        self, other_company_client, team, member_user
    ):
        """
        Test that accessing other company's team member returns 404.
        """
        membership = TeamMember.objects.get(user=member_user, team=team)
        url = f"/api/v1/team-members/{membership.id}/"

        response = other_company_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestUnauthenticatedAccess:
    """Tests for unauthenticated access to protected endpoints."""

    def test_teams_require_auth(self, api_client):
        """
        Test that team endpoints require authentication.
        """
        url = "/api/v1/teams/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_companies_require_auth(self, api_client):
        """
        Test that company endpoints require authentication.
        """
        url = "/api/v1/companies/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_team_members_require_auth(self, api_client):
        """
        Test that team member endpoints require authentication.
        """
        url = "/api/v1/team-members/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invitations_require_auth(self, api_client):
        """
        Test that invitation endpoints require authentication.
        """
        url = "/api/v1/team-invitations/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_api_keys_require_auth(self, api_client):
        """
        Test that API key endpoints require authentication.
        """
        url = "/api/v1/api-keys/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_billing_endpoints_require_auth(self, api_client):
        """
        Test that billing endpoints require authentication.
        """
        endpoints = [
            "/api/v1/billing/subscription/current/",
            "/api/v1/billing/invoices/",
            "/api/v1/billing/usage/summary/",
        ]

        for url in endpoints:
            response = api_client.get(url)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, f"Failed for {url}"

    def test_plans_are_public(self, api_client, plan):
        """
        Test that plan listing is publicly accessible.
        """
        url = "/api/v1/plans/"

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestRoleHierarchy:
    """Tests for role hierarchy enforcement."""

    @pytest.mark.parametrize("role,expected_level", [
        (TeamMember.Role.OWNER, 4),
        (TeamMember.Role.ADMIN, 3),
        (TeamMember.Role.MEMBER, 2),
        (TeamMember.Role.VIEWER, 1),
    ])
    def test_role_hierarchy_levels(self, role, expected_level):
        """
        Test that role hierarchy is correctly defined.

        Owner > Admin > Member > Viewer
        """
        from apps.teams.permissions import HasTeamRole

        permission = HasTeamRole()
        actual_level = permission.ROLE_HIERARCHY.get(role)

        assert actual_level == expected_level

    @pytest.mark.parametrize("user_role,action,should_succeed", [
        # Create team
        (TeamMember.Role.OWNER, "create_team", True),
        (TeamMember.Role.ADMIN, "create_team", True),
        (TeamMember.Role.MEMBER, "create_team", False),
        (TeamMember.Role.VIEWER, "create_team", False),
        # Update team
        (TeamMember.Role.OWNER, "update_team", True),
        (TeamMember.Role.ADMIN, "update_team", True),
        (TeamMember.Role.MEMBER, "update_team", False),
        (TeamMember.Role.VIEWER, "update_team", False),
        # Delete team
        (TeamMember.Role.OWNER, "delete_team", True),
        (TeamMember.Role.ADMIN, "delete_team", True),
        (TeamMember.Role.MEMBER, "delete_team", False),
        (TeamMember.Role.VIEWER, "delete_team", False),
        # View team
        (TeamMember.Role.OWNER, "view_team", True),
        (TeamMember.Role.ADMIN, "view_team", True),
        (TeamMember.Role.MEMBER, "view_team", True),
        (TeamMember.Role.VIEWER, "view_team", True),
    ])
    def test_permission_matrix(
        self, api_client, user_factory, company_factory, team_factory,
        user_role, action, should_succeed
    ):
        """
        Comprehensive permission matrix test.

        Tests all role/action combinations to ensure consistent behavior.
        """
        company, owner = company_factory(return_owner=True)
        team = team_factory(company=company)
        user = user_factory(email=f"perm_{user_role}_{action}@test.com", company=company)

        # Create membership with specified role
        TeamMember.objects.create(
            user=user,
            team=team,
            role=user_role,
            invited_by=owner
        )

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        # Perform action based on test case
        if action == "create_team":
            url = "/api/v1/teams/"
            data = {"name": "Permission Test Team", "company": str(company.id)}
            response = api_client.post(url, data, format="json")
            success_status = status.HTTP_201_CREATED

        elif action == "update_team":
            url = f"/api/v1/teams/{team.id}/"
            data = {"name": "Updated Name"}
            response = api_client.patch(url, data, format="json")
            success_status = status.HTTP_200_OK

        elif action == "delete_team":
            # Create a separate team to delete
            delete_team = team_factory(name="Team to Delete", company=company)
            url = f"/api/v1/teams/{delete_team.id}/"
            response = api_client.delete(url)
            success_status = status.HTTP_204_NO_CONTENT

        elif action == "view_team":
            url = f"/api/v1/teams/{team.id}/"
            response = api_client.get(url)
            success_status = status.HTTP_200_OK

        else:
            raise ValueError(f"Unknown action: {action}")

        if should_succeed:
            assert response.status_code == success_status, \
                f"Expected {success_status} for {user_role} doing {action}, got {response.status_code}"
        else:
            assert response.status_code == status.HTTP_403_FORBIDDEN, \
                f"Expected 403 for {user_role} doing {action}, got {response.status_code}"


@pytest.mark.django_db
class TestCompanyMembershipRequired:
    """Tests for company membership requirement."""

    def test_user_without_company_cannot_access_teams(
        self, api_client, user_factory
    ):
        """
        Test that users without company cannot access team resources.
        """
        user = user_factory(email="nocompany@example.com", company=None)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/teams/"

        response = api_client.get(url)

        # Should return empty list or 403 depending on implementation
        assert response.status_code in [
            status.HTTP_200_OK,  # Empty list
            status.HTTP_403_FORBIDDEN,
        ]
        if response.status_code == status.HTTP_200_OK:
            assert len(response.data) == 0

    def test_user_without_company_can_create_company(
        self, api_client, user_factory
    ):
        """
        Test that users without company can create their first company.
        """
        user = user_factory(email="firstcompany@example.com", company=None)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/companies/"
        data = {"name": "My First Company"}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        user.refresh_from_db()
        assert user.company is not None
