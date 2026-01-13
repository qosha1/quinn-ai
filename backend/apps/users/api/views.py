"""
API views for Users app.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.users.models import User
from apps.users.api.serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
)


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for User model.

    Provides user registration, profile management, and password change.

    Endpoints:
    - POST /users/ - Register new user (public)
    - GET /users/me/ - Get current user profile
    - PATCH /users/me/ - Update current user profile
    - POST /users/me/change-password/ - Change password
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        """
        Set permissions based on action.

        - Registration is public
        - All other actions require authentication
        """
        if self.action == "create":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        """
        Return appropriate serializer based on action.
        """
        if self.action == "create":
            return UserCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        elif self.action == "change_password":
            return ChangePasswordSerializer
        return UserSerializer

    def get_queryset(self):
        """
        Filter queryset to only current user for non-staff.
        """
        user = self.request.user

        if not user or not user.is_authenticated:
            return User.objects.none()

        # Staff can see all users
        if user.is_staff:
            return User.objects.all()

        # Regular users can only see themselves
        return User.objects.filter(id=user.id)

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        """
        Get or update current user profile.

        GET /users/me/ - Get profile
        PATCH /users/me/ - Update profile
        """
        user = request.user

        if request.method == "GET":
            serializer = UserSerializer(user)
            return Response(serializer.data)

        # PATCH
        serializer = UserUpdateSerializer(
            user,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(user).data)

    @action(detail=False, methods=["post"], url_path="me/change-password")
    def change_password(self, request):
        """
        Change current user's password.

        POST /users/me/change-password/
        {
            "old_password": "current_password",
            "new_password": "new_password",
            "new_password_confirm": "new_password"
        }
        """
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Password changed successfully."},
            status=status.HTTP_200_OK
        )
