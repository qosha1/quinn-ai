"""
Mixins for team-based ViewSets.
"""

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.teams.models import TeamMember


class TeamOwnedMixin:
    """
    Mixin for ViewSets to filter queryset by user's company/team.

    Automatically filters querysets to only return objects that belong
    to the user's company or teams they are a member of.
    """

    def get_queryset(self):
        """
        Filter queryset to only include objects from user's company/teams.

        Returns:
            QuerySet: Filtered queryset
        """
        queryset = super().get_queryset()
        user = self.request.user

        if not user or not user.is_authenticated:
            return queryset.none()

        # If user is superuser, return all
        if user.is_superuser:
            return queryset

        # Get user's company
        company = user.company

        if not company:
            return queryset.none()

        # Filter by company if the model has a company field
        model = queryset.model
        if hasattr(model, "company"):
            return queryset.filter(company=company)

        # Filter by team if the model has a team field
        if hasattr(model, "team"):
            # Get all teams user is a member of
            user_teams = TeamMember.objects.filter(
                user=user
            ).values_list("team_id", flat=True)

            return queryset.filter(
                Q(team_id__in=user_teams) |
                Q(team__company=company)
            )

        return queryset

    def perform_create(self, serializer):
        """
        Auto-assign company/team when creating objects.

        Args:
            serializer: The serializer instance
        """
        user = self.request.user

        # Auto-assign company if model has company field
        if hasattr(serializer.Meta.model, "company"):
            if not user.company:
                raise PermissionDenied("You must be a member of a company to create this resource.")
            serializer.save(company=user.company)
        else:
            serializer.save()


class CompanyOwnedMixin:
    """
    Mixin specifically for company-scoped resources.

    Simpler version of TeamOwnedMixin for models that only have company field.
    """

    def get_queryset(self):
        """
        Filter queryset to only include objects from user's company.

        Returns:
            QuerySet: Filtered queryset
        """
        queryset = super().get_queryset()
        user = self.request.user

        if not user or not user.is_authenticated:
            return queryset.none()

        # If user is superuser, return all
        if user.is_superuser:
            return queryset

        # Filter by company
        company = user.company
        if not company:
            return queryset.none()

        return queryset.filter(company=company)

    def perform_create(self, serializer):
        """
        Auto-assign company when creating objects.

        Args:
            serializer: The serializer instance
        """
        user = self.request.user
        if not user.company:
            raise PermissionDenied("You must be a member of a company to create this resource.")
        serializer.save(company=user.company)
