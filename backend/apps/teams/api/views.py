"""
API views for Teams app.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.teams.models import Company, Team, TeamMember, TeamInvitation
from apps.teams.mixins import CompanyOwnedMixin, TeamOwnedMixin
from apps.teams.permissions import IsCompanyMember, IsAdmin, IsOwner
from apps.teams.api.serializers import (
    CompanySerializer,
    CompanyCreateSerializer,
    TeamSerializer,
    TeamMemberSerializer,
    TeamMemberCreateSerializer,
    TeamInvitationSerializer,
    TeamInvitationCreateSerializer,
    TeamInvitationAcceptSerializer,
)


class CompanyViewSet(CompanyOwnedMixin, viewsets.ModelViewSet):
    """
    ViewSet for Company model.

    Users can only see and manage their own company.
    Only company owners can update/delete companies.

    Endpoints:
    - GET /companies/ - List companies (filtered to user's company)
    - POST /companies/ - Create new company
    - GET /companies/{id}/ - Get company details
    - PATCH /companies/{id}/ - Update company (owner only)
    - DELETE /companies/{id}/ - Delete company (owner only)
    """

    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return CompanyCreateSerializer
        return CompanySerializer

    def get_permissions(self):
        """
        Set permissions based on action.

        - Update/Delete require owner role
        - Other actions require authentication
        """
        if self.action in ["update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsOwner()]
        return [IsAuthenticated()]


class TeamViewSet(TeamOwnedMixin, viewsets.ModelViewSet):
    """
    ViewSet for Team model.

    Users can see teams in their company.
    Admin or higher can create/update/delete teams.

    Endpoints:
    - GET /teams/ - List teams (filtered to user's company)
    - POST /teams/ - Create new team (admin+)
    - GET /teams/{id}/ - Get team details
    - PATCH /teams/{id}/ - Update team (admin+)
    - DELETE /teams/{id}/ - Delete team (admin+)
    """

    queryset = Team.objects.select_related("company").all()
    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get_permissions(self):
        """
        Set permissions based on action.

        - Create/Update/Delete require admin role
        - Other actions require company membership
        """
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsCompanyMember(), IsAdmin()]
        return [IsAuthenticated(), IsCompanyMember()]


class TeamMemberViewSet(TeamOwnedMixin, viewsets.ModelViewSet):
    """
    ViewSet for TeamMember model.

    Manage team memberships and roles.
    Admin or higher can add/remove members and change roles.

    Endpoints:
    - GET /team-members/ - List team members
    - POST /team-members/ - Add member to team (admin+)
    - GET /team-members/{id}/ - Get member details
    - PATCH /team-members/{id}/ - Update member role (admin+)
    - DELETE /team-members/{id}/ - Remove member (admin+)
    """

    queryset = TeamMember.objects.select_related(
        "user", "team", "team__company", "invited_by"
    ).all()
    serializer_class = TeamMemberSerializer
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return TeamMemberCreateSerializer
        return TeamMemberSerializer

    def get_permissions(self):
        """
        Set permissions based on action.

        - Create/Update/Delete require admin role
        - Other actions require company membership
        """
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsCompanyMember(), IsAdmin()]
        return [IsAuthenticated(), IsCompanyMember()]

    @action(detail=False, methods=["get"], url_path="my-teams")
    def my_teams(self, request):
        """
        Get teams the current user is a member of.

        GET /team-members/my-teams/
        """
        memberships = TeamMember.objects.filter(
            user=request.user
        ).select_related("team", "team__company")

        serializer = self.get_serializer(memberships, many=True)
        return Response(serializer.data)


class TeamInvitationViewSet(TeamOwnedMixin, viewsets.ModelViewSet):
    """
    ViewSet for TeamInvitation model.

    Manage team invitations.
    Admin or higher can send invitations.
    Any user can accept invitations.

    Endpoints:
    - GET /team-invitations/ - List invitations
    - POST /team-invitations/ - Send invitation (admin+)
    - GET /team-invitations/{id}/ - Get invitation details
    - DELETE /team-invitations/{id}/ - Cancel invitation (admin+)
    - POST /team-invitations/accept/ - Accept invitation (public)
    """

    queryset = TeamInvitation.objects.select_related(
        "team", "team__company", "invited_by"
    ).all()
    serializer_class = TeamInvitationSerializer
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return TeamInvitationCreateSerializer
        elif self.action == "accept":
            return TeamInvitationAcceptSerializer
        return TeamInvitationSerializer

    def get_permissions(self):
        """
        Set permissions based on action.

        - Create/Delete require admin role
        - Accept is authenticated only
        - Other actions require company membership
        """
        if self.action in ["create", "destroy"]:
            return [IsAuthenticated(), IsCompanyMember(), IsAdmin()]
        elif self.action == "accept":
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsCompanyMember()]

    @action(detail=False, methods=["post"])
    def accept(self, request):
        """
        Accept a team invitation.

        POST /team-invitations/accept/
        {
            "token": "invitation_token"
        }
        """
        serializer = TeamInvitationAcceptSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        team_member = serializer.save()

        return Response(
            TeamMemberSerializer(team_member).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        """
        Resend a team invitation (updates expiration).

        POST /team-invitations/{id}/resend/
        """
        invitation = self.get_object()

        if invitation.is_accepted():
            return Response(
                {"detail": "This invitation has already been accepted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update expiration
        from django.utils import timezone
        invitation.expires_at = timezone.now() + timezone.timedelta(days=7)
        invitation.save(update_fields=["expires_at"])

        return Response(
            TeamInvitationSerializer(invitation).data,
            status=status.HTTP_200_OK
        )
