"""
Serializers for User model.
"""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model.

    Provides full user details for authenticated requests.
    """

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_email_verified",
            "company",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "is_email_verified",
            "created_at",
            "updated_at",
        ]


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.

    Includes password fields and validation.
    """

    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "password",
            "password_confirm",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        """
        Validate that passwords match.

        Args:
            attrs: Attribute dictionary

        Returns:
            dict: Validated attributes

        Raises:
            ValidationError: If passwords don't match
        """
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs

    def create(self, validated_data):
        """
        Create a new user with hashed password.

        Args:
            validated_data: Validated data dictionary

        Returns:
            User: Created user instance
        """
        # Remove password_confirm as it's not needed
        validated_data.pop("password_confirm", None)

        # Create user using manager's create_user method
        user = User.objects.create_user(**validated_data)
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user profile.

    Excludes sensitive fields that shouldn't be updated directly.
    """

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change endpoint.
    """

    old_password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"}
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        validators=[validate_password],
        style={"input_type": "password"}
    )
    new_password_confirm = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"}
    )

    def validate_old_password(self, value):
        """
        Validate that old password is correct.

        Args:
            value: Old password value

        Returns:
            str: Validated password

        Raises:
            ValidationError: If old password is incorrect
        """
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, attrs):
        """
        Validate that new passwords match.

        Args:
            attrs: Attribute dictionary

        Returns:
            dict: Validated attributes

        Raises:
            ValidationError: If passwords don't match
        """
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "New passwords do not match."}
            )
        return attrs

    def save(self):
        """
        Update user's password.

        Returns:
            User: Updated user instance
        """
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user
