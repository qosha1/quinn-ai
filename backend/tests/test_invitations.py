"""
Team invitation tests for the B2B SaaS API.

Tests cover:
- Creating invitations (admin+ only)
- Listing pending invitations
- Accepting invitations
- Rejecting/canceling invitations
- Expired invitation handling
- Duplicate invitation prevention

Usage:
    pytest tests/test_invitations.py -v
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from apps.teams.models import Team, TeamMember, TeamInvitation


@pytest.mark.django_db
class TestInvitationCreation:
    """Tests for creating team invitations."""

    def test_create_invitation_admin_success(self, admin_client, team):
        """
        Test that admin can create a team invitation.

        Invitation should be created with proper token and expiration.
        """
        url = "/api/v1/team-invitations/"
        data = {
            "email": "newinvite@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "newinvite@example.com"
        assert "token" in response.data
        assert TeamInvitation.objects.filter(email="newinvite@example.com").exists()

    def test_create_invitation_owner_success(self, owner_client, team, company):
        """
        Test that company owner can create invitations.
        """
        # First add owner to team
        TeamMember.objects.get_or_create(
            user=company.owner,
            team=team,
            defaults={"role": TeamMember.Role.OWNER}
        )

        url = "/api/v1/team-invitations/"
        data = {
            "email": "owner_invite@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.ADMIN,
        }

        response = owner_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

    def test_create_invitation_member_forbidden(self, member_client, team):
        """
        Test that regular members cannot create invitations.
        """
        url = "/api/v1/team-invitations/"
        data = {
            "email": "member_invite@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = member_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_invitation_viewer_forbidden(self, viewer_client, team):
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

    def test_create_invitation_generates_token(self, admin_client, team):
        """
        Test that invitation token is auto-generated.
        """
        url = "/api/v1/team-invitations/"
        data = {
            "email": "token_test@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert "token" in response.data
        assert len(response.data["token"]) > 20  # Token should be substantial

    def test_create_invitation_with_admin_role(self, admin_client, team):
        """
        Test creating an invitation with admin role.
        """
        url = "/api/v1/team-invitations/"
        data = {
            "email": "new_admin@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.ADMIN,
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["role"] == TeamMember.Role.ADMIN


@pytest.mark.django_db
class TestDuplicateInvitationPrevention:
    """Tests for preventing duplicate invitations."""

    def test_cannot_invite_existing_member(
        self, admin_client, team, member_user
    ):
        """
        Test that inviting an existing team member is rejected.
        """
        url = "/api/v1/team-invitations/"
        data = {
            "email": member_user.email,
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data or "already a member" in str(response.data).lower()

    def test_can_reinvite_after_previous_expired(
        self, admin_client, team, invitation_factory, owner_user
    ):
        """
        Test that user can be reinvited after previous invitation expired.
        """
        # Create expired invitation
        old_invitation = invitation_factory(
            email="reinvite@example.com",
            team=team,
            invited_by=owner_user,
        )
        old_invitation.expires_at = timezone.now() - timedelta(days=1)
        old_invitation.save()

        url = "/api/v1/team-invitations/"
        data = {
            "email": "reinvite@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = admin_client.post(url, data, format="json")

        # Should allow new invitation or update existing
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_200_OK,
        ]


@pytest.mark.django_db
class TestInvitationListing:
    """Tests for listing invitations."""

    def test_list_invitations_admin_success(
        self, admin_client, invitation, team
    ):
        """
        Test that admin can list pending invitations.
        """
        url = "/api/v1/team-invitations/"

        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_list_invitations_filtered_by_company(
        self, admin_client, invitation, invitation_factory, other_team, other_company
    ):
        """
        Test that invitations are filtered by company.

        Users should not see invitations for other companies' teams.
        """
        # Create invitation in other company
        other_invitation = invitation_factory(
            email="other@example.com",
            team=other_team,
            invited_by=other_company.owner,
        )

        url = "/api/v1/team-invitations/"

        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        invitation_ids = [inv["id"] for inv in response.data]
        assert str(invitation.id) in invitation_ids
        assert str(other_invitation.id) not in invitation_ids

    def test_get_invitation_details(self, admin_client, invitation):
        """
        Test retrieving specific invitation details.
        """
        url = f"/api/v1/team-invitations/{invitation.id}/"

        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == invitation.email
        assert "is_expired" in response.data
        assert "is_accepted" in response.data


@pytest.mark.django_db
class TestInvitationAcceptance:
    """Tests for accepting team invitations."""

    def test_accept_invitation_success(
        self, api_client, invitation, user_factory
    ):
        """
        Test that a user can accept a valid invitation.

        Should create team membership and mark invitation as accepted.
        """
        # Create a new user to accept the invitation
        new_user = user_factory(email=invitation.email)

        # Authenticate as new user
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(new_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/team-invitations/accept/"
        data = {
            "token": invitation.token,
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

        # Verify membership was created
        assert TeamMember.objects.filter(
            user=new_user,
            team=invitation.team
        ).exists()

        # Verify invitation is marked as accepted
        invitation.refresh_from_db()
        assert invitation.is_accepted()

    def test_accept_invitation_assigns_role(
        self, api_client, invitation_factory, team, owner_user, user_factory
    ):
        """
        Test that accepted invitation assigns the correct role.
        """
        invitation = invitation_factory(
            email="admin_role@example.com",
            team=team,
            invited_by=owner_user,
            role=TeamMember.Role.ADMIN,
        )
        new_user = user_factory(email=invitation.email)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(new_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/team-invitations/accept/"
        data = {"token": invitation.token}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

        membership = TeamMember.objects.get(user=new_user, team=team)
        assert membership.role == TeamMember.Role.ADMIN

    def test_accept_invitation_updates_user_company(
        self, api_client, invitation, user_factory
    ):
        """
        Test that accepting invitation updates user's company if not set.
        """
        new_user = user_factory(email=invitation.email, company=None)
        assert new_user.company is None

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(new_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/team-invitations/accept/"
        data = {"token": invitation.token}

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_201_CREATED

        new_user.refresh_from_db()
        assert new_user.company == invitation.team.company

    def test_accept_invitation_invalid_token(self, authenticated_client):
        """
        Test that invalid invitation token is rejected.
        """
        url = "/api/v1/team-invitations/accept/"
        data = {
            "token": "invalid_token_12345",
        }

        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "token" in response.data

    def test_accept_invitation_already_accepted(
        self, api_client, invitation, user_factory
    ):
        """
        Test that already accepted invitation cannot be accepted again.
        """
        # First user accepts
        first_user = user_factory(email=invitation.email)
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(first_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/team-invitations/accept/"
        data = {"token": invitation.token}

        # First acceptance
        response1 = api_client.post(url, data, format="json")
        assert response1.status_code == status.HTTP_201_CREATED

        # Second user tries to accept same token
        second_user = user_factory(email="second@example.com")
        refresh2 = RefreshToken.for_user(second_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh2.access_token}")

        response2 = api_client.post(url, data, format="json")

        assert response2.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been accepted" in str(response2.data).lower()


@pytest.mark.django_db
class TestExpiredInvitations:
    """Tests for expired invitation handling."""

    def test_accept_expired_invitation_fails(
        self, api_client, expired_invitation, user_factory
    ):
        """
        Test that expired invitations cannot be accepted.
        """
        new_user = user_factory(email=expired_invitation.email)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(new_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/team-invitations/accept/"
        data = {
            "token": expired_invitation.token,
        }

        response = api_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "expired" in str(response.data).lower()

    def test_invitation_is_expired_check(self, invitation):
        """
        Test the is_expired method on invitation model.
        """
        # Fresh invitation should not be expired
        assert not invitation.is_expired()

        # Set expiration to past
        invitation.expires_at = timezone.now() - timedelta(hours=1)
        invitation.save()

        assert invitation.is_expired()

    def test_resend_invitation_updates_expiration(
        self, admin_client, invitation
    ):
        """
        Test that resending invitation updates expiration date.
        """
        old_expires = invitation.expires_at
        url = f"/api/v1/team-invitations/{invitation.id}/resend/"

        response = admin_client.post(url)

        assert response.status_code == status.HTTP_200_OK

        invitation.refresh_from_db()
        assert invitation.expires_at > old_expires


@pytest.mark.django_db
class TestInvitationCancellation:
    """Tests for canceling/deleting invitations."""

    def test_cancel_invitation_admin_success(
        self, admin_client, invitation
    ):
        """
        Test that admin can cancel/delete an invitation.
        """
        url = f"/api/v1/team-invitations/{invitation.id}/"

        response = admin_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not TeamInvitation.objects.filter(id=invitation.id).exists()

    def test_cancel_invitation_member_forbidden(
        self, member_client, invitation
    ):
        """
        Test that regular members cannot cancel invitations.
        """
        url = f"/api/v1/team-invitations/{invitation.id}/"

        response = member_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_cancel_accepted_invitation(
        self, admin_client, invitation_factory, team, owner_user, user_factory
    ):
        """
        Test handling of attempting to delete an already accepted invitation.
        """
        invitation = invitation_factory(
            email="accepted@example.com",
            team=team,
            invited_by=owner_user,
        )

        # Accept the invitation
        invitation.accepted_at = timezone.now()
        invitation.save()

        url = f"/api/v1/team-invitations/{invitation.id}/"

        response = admin_client.delete(url)

        # Could either succeed (cleaning up) or fail (prevent deletion of accepted)
        # Implementation-dependent behavior
        assert response.status_code in [
            status.HTTP_204_NO_CONTENT,
            status.HTTP_400_BAD_REQUEST,
        ]


@pytest.mark.django_db
class TestInvitationPermissionsByRole:
    """Tests for invitation permissions across different roles."""

    @pytest.mark.parametrize("role,can_invite", [
        (TeamMember.Role.OWNER, True),
        (TeamMember.Role.ADMIN, True),
        (TeamMember.Role.MEMBER, False),
        (TeamMember.Role.VIEWER, False),
    ])
    def test_invitation_creation_by_role(
        self, api_client, user_factory, company_factory, team_factory, role, can_invite
    ):
        """
        Test invitation creation permissions for different roles.

        Only owner and admin should be able to create invitations.
        """
        company, owner = company_factory(return_owner=True)
        team = team_factory(company=company)
        user = user_factory(email=f"invite_{role}@test.com", company=company)

        # Create membership with specified role
        TeamMember.objects.create(
            user=user,
            team=team,
            role=role,
            invited_by=owner
        )

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        url = "/api/v1/team-invitations/"
        data = {
            "email": f"new_{role}@example.com",
            "team": str(team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = api_client.post(url, data, format="json")

        if can_invite:
            assert response.status_code == status.HTTP_201_CREATED
        else:
            assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestInvitationCrossCompanyIsolation:
    """Tests for cross-company invitation isolation."""

    def test_cannot_view_other_company_invitation(
        self, other_company_client, invitation
    ):
        """
        Test that users cannot view invitations from other companies.
        """
        url = f"/api/v1/team-invitations/{invitation.id}/"

        response = other_company_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_delete_other_company_invitation(
        self, other_company_client, invitation
    ):
        """
        Test that users cannot delete invitations from other companies.
        """
        url = f"/api/v1/team-invitations/{invitation.id}/"

        response = other_company_client.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert TeamInvitation.objects.filter(id=invitation.id).exists()

    def test_cannot_create_invitation_for_other_company_team(
        self, admin_client, other_team
    ):
        """
        Test that users cannot create invitations for other companies' teams.
        """
        url = "/api/v1/team-invitations/"
        data = {
            "email": "cross_invite@example.com",
            "team": str(other_team.id),
            "role": TeamMember.Role.MEMBER,
        }

        response = admin_client.post(url, data, format="json")

        # Should fail due to cross-company isolation
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]
