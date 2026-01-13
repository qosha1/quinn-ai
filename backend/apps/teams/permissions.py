"""
Permission classes for team-based access control.
"""

from rest_framework import permissions

from apps.teams.models import TeamMember


class IsCompanyMember(permissions.BasePermission):
    """
    Permission to check if user belongs to the company.

    User must be authenticated and have a company assigned.
    """

    message = "You must be a member of this company to perform this action."

    def has_permission(self, request, view):
        """
        Check if user has company membership.

        Args:
            request: The HTTP request
            view: The view being accessed

        Returns:
            bool: True if user has a company, False otherwise
        """
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.company
        )

    def has_object_permission(self, request, view, obj):
        """
        Check if user's company matches the object's company.

        Args:
            request: The HTTP request
            view: The view being accessed
            obj: The object being accessed

        Returns:
            bool: True if companies match, False otherwise
        """
        if not request.user or not request.user.is_authenticated:
            return False

        # Get company from object
        if hasattr(obj, "company"):
            return obj.company == request.user.company
        elif hasattr(obj, "team") and hasattr(obj.team, "company"):
            return obj.team.company == request.user.company

        return False


class IsTeamMember(permissions.BasePermission):
    """
    Permission to check if user is a member of the team.

    User must be authenticated and have membership in the team.
    """

    message = "You must be a member of this team to perform this action."

    def has_object_permission(self, request, view, obj):
        """
        Check if user is a member of the team.

        Args:
            request: The HTTP request
            view: The view being accessed
            obj: The object being accessed

        Returns:
            bool: True if user is team member, False otherwise
        """
        if not request.user or not request.user.is_authenticated:
            return False

        # Get team from object
        team = None
        if hasattr(obj, "team"):
            team = obj.team
        elif obj.__class__.__name__ == "Team":
            team = obj

        if not team:
            return False

        # Check if user is a member of the team
        return TeamMember.objects.filter(
            user=request.user,
            team=team
        ).exists()


class HasTeamRole(permissions.BasePermission):
    """
    Permission to check if user has the required role level in a team.

    Role hierarchy: owner > admin > member > viewer
    """

    message = "You do not have the required role to perform this action."

    # Define role hierarchy (higher number = more permissions)
    ROLE_HIERARCHY = {
        TeamMember.Role.VIEWER: 1,
        TeamMember.Role.MEMBER: 2,
        TeamMember.Role.ADMIN: 3,
        TeamMember.Role.OWNER: 4,
    }

    def __init__(self, required_role=TeamMember.Role.MEMBER):
        """
        Initialize with required role.

        Args:
            required_role: Minimum role required (from TeamMember.Role)
        """
        self.required_role = required_role

    def has_permission(self, request, view):
        """
        Check if user has minimum required role in any team.

        Args:
            request: The HTTP request
            view: The view being accessed

        Returns:
            bool: True if user has sufficient role, False otherwise
        """
        if not request.user or not request.user.is_authenticated:
            return False

        # Get required role from view if available
        required_role = getattr(view, "required_role", self.required_role)

        # Check if user has any membership with sufficient role
        return TeamMember.objects.filter(
            user=request.user,
            role__in=self._get_sufficient_roles(required_role)
        ).exists()

    def has_object_permission(self, request, view, obj):
        """
        Check if user has required role for the specific object.

        Args:
            request: The HTTP request
            view: The view being accessed
            obj: The object being accessed

        Returns:
            bool: True if user has sufficient role, False otherwise
        """
        if not request.user or not request.user.is_authenticated:
            return False

        # Get team from object
        team = None
        if hasattr(obj, "team"):
            team = obj.team
        elif obj.__class__.__name__ == "Team":
            team = obj

        if not team:
            return False

        # Get required role from view if available
        required_role = getattr(view, "required_role", self.required_role)

        # Get user's role in the team
        try:
            membership = TeamMember.objects.get(
                user=request.user,
                team=team
            )
            user_role_level = self.ROLE_HIERARCHY.get(membership.role, 0)
            required_role_level = self.ROLE_HIERARCHY.get(required_role, 0)

            return user_role_level >= required_role_level
        except TeamMember.DoesNotExist:
            return False

    def _get_sufficient_roles(self, required_role):
        """
        Get list of roles that meet or exceed the required role.

        Args:
            required_role: Minimum required role

        Returns:
            list: List of role values that are sufficient
        """
        required_level = self.ROLE_HIERARCHY.get(required_role, 0)
        return [
            role for role, level in self.ROLE_HIERARCHY.items()
            if level >= required_level
        ]


class IsOwner(HasTeamRole):
    """Permission requiring owner role."""

    def __init__(self):
        super().__init__(required_role=TeamMember.Role.OWNER)


class IsAdmin(HasTeamRole):
    """Permission requiring admin role or higher."""

    def __init__(self):
        super().__init__(required_role=TeamMember.Role.ADMIN)


class IsMember(HasTeamRole):
    """Permission requiring member role or higher."""

    def __init__(self):
        super().__init__(required_role=TeamMember.Role.MEMBER)
