"""
API views for Authentication app.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.authentication.models import APIKey
from apps.teams.mixins import CompanyOwnedMixin
from apps.teams.permissions import IsCompanyMember, IsAdmin
from apps.authentication.api.serializers import (
    APIKeySerializer,
    APIKeyCreateSerializer,
)


class APIKeyViewSet(CompanyOwnedMixin, viewsets.ModelViewSet):
    """
    ViewSet for APIKey model.

    Manage API keys for server-to-server authentication.
    Admin or higher can create/manage API keys.

    Endpoints:
    - GET /api-keys/ - List API keys (filtered to user's company)
    - POST /api-keys/ - Create new API key (admin+)
    - GET /api-keys/{id}/ - Get API key details
    - PATCH /api-keys/{id}/ - Update API key (admin+)
    - DELETE /api-keys/{id}/ - Delete API key (admin+)
    - POST /api-keys/{id}/revoke/ - Revoke API key (admin+)
    """

    queryset = APIKey.objects.select_related("company", "created_by").all()
    serializer_class = APIKeySerializer
    permission_classes = [IsAuthenticated, IsCompanyMember]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return APIKeyCreateSerializer
        return APIKeySerializer

    def get_permissions(self):
        """
        Set permissions based on action.

        - All actions require admin role and company membership
        """
        return [IsAuthenticated(), IsCompanyMember(), IsAdmin()]

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        """
        Revoke an API key (set is_active to False).

        POST /api-keys/{id}/revoke/
        """
        api_key = self.get_object()
        api_key.is_active = False
        api_key.save(update_fields=["is_active"])

        return Response(
            {"detail": f"API key '{api_key.name}' has been revoked."},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """
        Activate a previously revoked API key.

        POST /api-keys/{id}/activate/
        """
        api_key = self.get_object()

        if api_key.is_valid():
            return Response(
                {"detail": "API key is already active."},
                status=status.HTTP_400_BAD_REQUEST
            )

        api_key.is_active = True
        api_key.save(update_fields=["is_active"])

        return Response(
            {"detail": f"API key '{api_key.name}' has been activated."},
            status=status.HTTP_200_OK
        )
