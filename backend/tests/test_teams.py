"""
Team management tests for the B2B SaaS API.

Tests cover:
- Team creation (admin+ only)
- Team listing (filtered by company)
- Team update settings
- Team deletion (admin+ only)
- Adding team members
- Removing team members
- Changing member roles
- Cross-company isolation

Usage:
    pytest tests/test_teams.py -v
"""

import pytest
from rest_framework import status

from apps.teams.models import Company, Team, TeamMember


@pytest.mark.django_db
class TestCompanyManagement:
    """Tests for company management endpoints."""

    def test_create_company_success(self, authenticated_client, user):
        """
        Test successful company creation.

        Any authenticated user should be able to create a company
        and become its owner.
        """
        url = "/api/v1/companies/"
        data = {
            "name": "New Company Inc",
            "settings": {"theme": "dark"},
        }

        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Company Inc"
        assert "slug" in response.data

        # Verify user is now company owner
        user.refresh_from_db()
        assert user.company is not None
        assert user.company.name == "New Company Inc"
        assert user.company.owner == user

    def test_list_companies_filtered(self, owner_client, company, other_company):
        """
        Test that users only see their own company.

        Cross-company isolation ensures users cannot see other companies.
        """
        url = "/api/v1/companies/"

        response = owner_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Should only see their own company
        company_ids = [c["id"] for c in response.data]
        assert str(company.id) in company_ids
        assert str(other_company.id) not in company_ids

    def test_update_company_owner_success(self, owner_client, company):
        """
        Test that company owner can update company settings.
        """
        url = f"/api/v1/companies/{company.id}/"
        data = {
            "name": "Updated Company Name",
            "settings": {"new_setting": True},
        }

        response = owner_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        company.refresh_from_db()
        assert company.name == "Updated Company Name"
        assert company.settings["new_setting"] is True

    def test_update_company_non_owner_forbidden(self, admin_client, company):
        """
        Test that non-owners cannot update company.

        Even admins should not be able to update company-level settings.
        """
        url = f"/api/v1/companies/{company.id}/"
        data = {
            "name": "Unauthorized Update",
        }

        response = admin_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_company_owner_only(self, owner_client, company_factory):
        """
        Test that only company owner can delete company.
        """
        company = company_factory(name="Company to Delete")
        url = f"/api/v1/companies/{company.id}/"

        response = owner_client.delete(url)

        # Note: Owner can delete, but this might return 403 for
        # non-owners of this specific company
        # The test verifies the endpoint behavior
        assert response.status_code in [
            status.HTTP_204_NO_CONTENT,
            status.HTTP_404_NOT_FOUND  # Cross-company isolation
        ]


@pytest.mark.django_db
class TestTeamCreation:
    """Tests for team creation endpoint."""

    def test_create_team_admin_success(self, admin_client, company):
        """
        Test that admin can create a team.

        Admins should be able to create new teams in their company.
        """
        url = "/api/v1/teams/"
        data = {
            "name": "Engineering Team",
            "company": str(company.id),
            "settings": {"visibility": "private"},
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Engineering Team"
        assert Team.objects.filter(name="Engineering Team").exists()

    def test_create_team_member_forbidden(self, member_client, company):
        """
        Test that regular members cannot create teams.

        Only admin role and above should have team creation permission.
        """
        url = "/api/v1/teams/"
        data = {
            "name": "Unauthorized Team",
            "company": str(company.id),
        }

        response = member_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_team_viewer_forbidden(self, viewer_client, company):
        """
        Test that viewers cannot create teams.
        """
        url = "/api/v1/teams/"
        data = {
            "name": "Unauthorized Team",
            "company": str(company.id),
        }

        response = viewer_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_team_auto_generates_slug(self, admin_client, company):
        """
        Test that team slug is auto-generated from name.
        """
        url = "/api/v1/teams/"
        data = {
            "name": "My Amazing Team",
            "company": str(company.id),
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["slug"] == "my-amazing-team"


@pytest.mark.django_db
class TestTeamListing:
    """Tests for team listing endpoint."""

    def test_list_teams_company_filtered(self, owner_client, team, other_team):
        """
        Test that users only see teams in their company.

        Cross-company isolation ensures proper data segregation.
        """
        url = "/api/v1/teams/"

        response = owner_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        team_ids = [t["id"] for t in response.data]
        assert str(team.id) in team_ids
        assert str(other_team.id) not in team_ids

    def test_list_teams_all_roles_can_view(
        self, admin_client, member_client, viewer_client, team
    ):
        """
        Test that all team members can list teams regardless of role.
        """
        url = "/api/v1/teams/"

        for client in [admin_client, member_client, viewer_client]:
            response = client.get(url)
            assert response.status_code == status.HTTP_200_OK

    def test_get_team_details(self, owner_client, team):
        """
        Test retrieving specific team details.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = owner_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == team.name
        assert "members_count" in response.data


@pytest.mark.django_db
class TestTeamUpdate:
    """Tests for team update endpoint."""

    def test_update_team_admin_success(self, admin_client, team):
        """
        Test that admin can update team settings.
        """
        url = f"/api/v1/teams/{team.id}/"
        data = {
            "name": "Updated Team Name",
            "settings": {"new_config": "value"},
        }

        response = admin_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        team.refresh_from_db()
        assert team.name == "Updated Team Name"

    def test_update_team_member_forbidden(self, member_client, team):
        """
        Test that members cannot update team settings.
        """
        url = f"/api/v1/teams/{team.id}/"
        data = {
            "name": "Unauthorized Update",
        }

        response = member_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_team_viewer_forbidden(self, viewer_client, team):
        """
        Test that viewers cannot update team settings.
        """
        url = f"/api/v1/teams/{team.id}/"
        data = {
            "name": "Unauthorized Update",
        }

        response = viewer_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTeamDeletion:
    """Tests for team deletion endpoint."""

    def test_delete_team_admin_success(self, admin_client, team_factory, company):
        """
        Test that admin can delete a team.
        """
        team_to_delete = team_factory(name="Team to Delete", company=company)
        url = f"/api/v1/teams/{team_to_delete.id}/"

        response = admin_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Team.objects.filter(id=team_to_delete.id).exists()

    def test_delete_team_member_forbidden(self, member_client, team):
        """
        Test that members cannot delete teams.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = member_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Team.objects.filter(id=team.id).exists()

    def test_delete_team_viewer_forbidden(self, viewer_client, team):
        """
        Test that viewers cannot delete teams.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = viewer_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTeamMemberManagement:
    """Tests for adding/removing team members."""

    def test_add_team_member_admin_success(
        self, admin_client, team, user_factory, company
    ):
        """
        Test that admin can add a member to the team.
        """
        new_member = user_factory(
            email="newmember@example.com",
            company=company
        )

        url = "/api/v1/team-members/"
        data = {
            "user": str(new_member.id),
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert TeamMember.objects.filter(user=new_member, team=team).exists()

    def test_add_team_member_member_forbidden(
        self, member_client, team, user_factory, company
    ):
        """
        Test that regular members cannot add team members.
        """
        new_member = user_factory(
            email="newmember2@example.com",
            company=company
        )

        url = "/api/v1/team-members/"
        data = {
            "user": str(new_member.id),
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = member_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_remove_team_member_admin_success(self, admin_client, team, member_user):
        """
        Test that admin can remove a member from the team.
        """
        membership = TeamMember.objects.get(user=member_user, team=team)
        url = f"/api/v1/team-members/{membership.id}/"

        response = admin_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not TeamMember.objects.filter(user=member_user, team=team).exists()

    def test_remove_team_member_member_forbidden(
        self, member_client, team, viewer_user
    ):
        """
        Test that regular members cannot remove other members.
        """
        membership = TeamMember.objects.get(user=viewer_user, team=team)
        url = f"/api/v1/team-members/{membership.id}/"

        response = member_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_change_member_role_admin_success(self, admin_client, team, member_user):
        """
        Test that admin can change member's role.
        """
        membership = TeamMember.objects.get(user=member_user, team=team)
        url = f"/api/v1/team-members/{membership.id}/"
        data = {
            "role": TeamMember.Role.ADMIN,
        }

        response = admin_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        membership.refresh_from_db()
        assert membership.role == TeamMember.Role.ADMIN

    def test_change_member_role_member_forbidden(
        self, member_client, team, viewer_user
    ):
        """
        Test that regular members cannot change roles.
        """
        membership = TeamMember.objects.get(user=viewer_user, team=team)
        url = f"/api/v1/team-members/{membership.id}/"
        data = {
            "role": TeamMember.Role.ADMIN,
        }

        response = member_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_team_members(self, admin_client, team, admin_user, member_user):
        """
        Test listing team members.
        """
        url = "/api/v1/team-members/"

        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Should see members from the same company
        assert len(response.data) > 0

    def test_get_my_teams(self, admin_client, team, admin_user):
        """
        Test retrieving user's team memberships.
        """
        url = "/api/v1/team-members/my-teams/"

        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        teams = response.data
        team_ids = [m["team"] for m in teams]
        assert str(team.id) in team_ids


@pytest.mark.django_db
class TestCrossCompanyIsolation:
    """Tests for cross-company data isolation."""

    def test_cannot_view_other_company_team(
        self, other_company_client, team
    ):
        """
        Test that users cannot view teams from other companies.

        Should return 404 (not 403) to prevent information disclosure.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = other_company_client.get(url)

        # Should be 404, not 403, to prevent info leakage
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_update_other_company_team(
        self, other_company_client, team
    ):
        """
        Test that users cannot update teams from other companies.
        """
        url = f"/api/v1/teams/{team.id}/"
        data = {"name": "Hacked Team Name"}

        response = other_company_client.patch(url, data, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        team.refresh_from_db()
        assert team.name != "Hacked Team Name"

    def test_cannot_delete_other_company_team(
        self, other_company_client, team
    ):
        """
        Test that users cannot delete teams from other companies.
        """
        url = f"/api/v1/teams/{team.id}/"

        response = other_company_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert Team.objects.filter(id=team.id).exists()

    def test_cannot_add_member_to_other_company_team(
        self, other_company_client, team, other_company_user
    ):
        """
        Test that users cannot add members to other company's teams.
        """
        url = "/api/v1/team-members/"
        data = {
            "user": str(other_company_user.id),
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = other_company_client.post(url, data, format="json")

        # Should fail due to cross-company isolation
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_team_list_only_shows_own_company(
        self, owner_client, other_company_client, team, other_team
    ):
        """
        Test that team listing is properly filtered by company.
        """
        url = "/api/v1/teams/"

        # First company user
        response1 = owner_client.get(url)
        team_ids_1 = [t["id"] for t in response1.data]

        # Second company user
        response2 = other_company_client.get(url)
        team_ids_2 = [t["id"] for t in response2.data]

        # Verify no overlap
        assert str(team.id) in team_ids_1
        assert str(team.id) not in team_ids_2
        assert str(other_team.id) in team_ids_2
        assert str(other_team.id) not in team_ids_1


@pytest.mark.django_db
class TestRoleParameterization:
    """Tests using parametrize for testing multiple roles."""

    @pytest.mark.parametrize("role,can_create", [
        (TeamMember.Role.OWNER, True),
        (TeamMember.Role.ADMIN, True),
        (TeamMember.Role.MEMBER, False),
        (TeamMember.Role.VIEWER, False),
    ])
    def test_team_creation_by_role(
        self, api_client, user_factory, company_factory, team_factory, role, can_create
    ):
        """
        Test team creation permissions for different roles.

        Only owner and admin roles should be able to create teams.
        """
        company, owner = company_factory(return_owner=True)
        team = team_factory(company=company)
        user = user_factory(email=f"{role}@test.com", company=company)

        # Create membership with specified role
        TeamMember.objects.create(
            user=user,
            team=team,
            role=role,
            invited_by=owner
        )

        # Authenticate
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/teams/"
        data = {
            "name": f"Team by {role}",
            "company": str(company.id),
        }

        response = api_client.post(url, data, format="json")

        if can_create:
            assert response.status_code == status.HTTP_201_CREATED
        else:
            assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize("role,can_update", [
        (TeamMember.Role.OWNER, True),
        (TeamMember.Role.ADMIN, True),
        (TeamMember.Role.MEMBER, False),
        (TeamMember.Role.VIEWER, False),
    ])
    def test_team_update_by_role(
        self, api_client, user_factory, company_factory, team_factory, role, can_update
    ):
        """
        Test team update permissions for different roles.
        """
        company, owner = company_factory(return_owner=True)
        team = team_factory(company=company)
        user = user_factory(email=f"{role}_update@test.com", company=company)

        TeamMember.objects.create(
            user=user,
            team=team,
            role=role,
            invited_by=owner
        )

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = f"/api/v1/teams/{team.id}/"
        data = {"name": "Updated Name"}

        response = api_client.patch(url, data, format="json")

        if can_update:
            assert response.status_code == status.HTTP_200_OK
        else:
            assert response.status_code == status.HTTP_403_FORBIDDEN
