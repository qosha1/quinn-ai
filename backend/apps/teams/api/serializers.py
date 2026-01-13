"""
Serializers for Teams models.
"""

from django.utils import timezone
from rest_framework import serializers

from apps.teams.models import Company, Team, TeamMember, TeamInvitation
from apps.users.api.serializers import UserSerializer


class CompanySerializer(serializers.ModelSerializer):
    """
    Serializer for Company model.
    """

    owner_details = UserSerializer(source="owner", read_only=True)
    teams_count = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "slug",
            "settings",
            "owner",
            "owner_details",
            "teams_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "created_at",
            "updated_at",
        ]

    def get_teams_count(self, obj):
        """Get count of teams in the company."""
        return obj.teams.count()


class CompanyCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new company.

    Auto-assigns the requesting user as owner.
    """

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "settings",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        """
        Create company with requesting user as owner.

        Args:
            validated_data: Validated data dictionary

        Returns:
            Company: Created company instance
        """
        user = self.context["request"].user
        validated_data["owner"] = user
        company = super().create(validated_data)

        # Update user's company
        user.company = company
        user.save(update_fields=["company"])

        return company


class TeamSerializer(serializers.ModelSerializer):
    """
    Serializer for Team model.
    """

    company_details = CompanySerializer(source="company", read_only=True)
    members_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "slug",
            "company",
            "company_details",
            "settings",
            "members_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "created_at",
            "updated_at",
        ]

    def get_members_count(self, obj):
        """Get count of members in the team."""
        return obj.members.count()


class TeamMemberSerializer(serializers.ModelSerializer):
    """
    Serializer for TeamMember model.
    """

    user_details = UserSerializer(source="user", read_only=True)
    team_details = TeamSerializer(source="team", read_only=True)
    invited_by_details = UserSerializer(source="invited_by", read_only=True)

    class Meta:
        model = TeamMember
        fields = [
            "id",
            "user",
            "user_details",
            "team",
            "team_details",
            "role",
            "invited_by",
            "invited_by_details",
            "joined_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "invited_by",
            "joined_at",
            "created_at",
            "updated_at",
        ]


class TeamMemberCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for adding a member to a team.
    """

    class Meta:
        model = TeamMember
        fields = [
            "id",
            "user",
            "team",
            "role",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        """
        Create team member with invited_by set to requesting user.

        Args:
            validated_data: Validated data dictionary

        Returns:
            TeamMember: Created team member instance
        """
        user = self.context["request"].user
        validated_data["invited_by"] = user
        return super().create(validated_data)


class TeamInvitationSerializer(serializers.ModelSerializer):
    """
    Serializer for TeamInvitation model.
    """

    team_details = TeamSerializer(source="team", read_only=True)
    invited_by_details = UserSerializer(source="invited_by", read_only=True)
    is_expired = serializers.BooleanField(source="is_expired", read_only=True)
    is_accepted = serializers.BooleanField(source="is_accepted", read_only=True)

    class Meta:
        model = TeamInvitation
        fields = [
            "id",
            "email",
            "team",
            "team_details",
            "role",
            "token",
            "invited_by",
            "invited_by_details",
            "expires_at",
            "accepted_at",
            "is_expired",
            "is_accepted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "token",
            "invited_by",
            "expires_at",
            "accepted_at",
            "created_at",
            "updated_at",
        ]


class TeamInvitationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating team invitations.
    """

    class Meta:
        model = TeamInvitation
        fields = [
            "id",
            "email",
            "team",
            "role",
        ]
        read_only_fields = ["id"]

    def validate_email(self, value):
        """
        Validate that user is not already a team member.

        Args:
            value: Email address

        Returns:
            str: Validated email

        Raises:
            ValidationError: If user is already a member
        """
        team = self.initial_data.get("team")
        if team and TeamMember.objects.filter(
            user__email=value,
            team_id=team
        ).exists():
            raise serializers.ValidationError(
                "This user is already a member of the team."
            )
        return value

    def create(self, validated_data):
        """
        Create invitation with invited_by set to requesting user.

        Args:
            validated_data: Validated data dictionary

        Returns:
            TeamInvitation: Created invitation instance
        """
        user = self.context["request"].user
        validated_data["invited_by"] = user
        return super().create(validated_data)


class TeamInvitationAcceptSerializer(serializers.Serializer):
    """
    Serializer for accepting team invitations.
    """

    token = serializers.CharField(required=True)

    def validate_token(self, value):
        """
        Validate that invitation exists and is valid.

        Args:
            value: Invitation token

        Returns:
            str: Validated token

        Raises:
            ValidationError: If invitation is invalid
        """
        try:
            invitation = TeamInvitation.objects.get(token=value)
        except TeamInvitation.DoesNotExist:
            raise serializers.ValidationError("Invalid invitation token.")

        if invitation.is_expired():
            raise serializers.ValidationError("This invitation has expired.")

        if invitation.is_accepted():
            raise serializers.ValidationError("This invitation has already been accepted.")

        self.invitation = invitation
        return value

    def save(self):
        """
        Accept the invitation and create team membership.

        Returns:
            TeamMember: Created team member instance
        """
        user = self.context["request"].user
        invitation = self.invitation

        # Create team membership
        team_member = TeamMember.objects.create(
            user=user,
            team=invitation.team,
            role=invitation.role,
            invited_by=invitation.invited_by
        )

        # Mark invitation as accepted
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])

        # Update user's company if not set
        if not user.company:
            user.company = invitation.team.company
            user.save(update_fields=["company"])

        return team_member
