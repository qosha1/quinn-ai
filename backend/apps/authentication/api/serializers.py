"""
Serializers for Authentication models.
"""

from rest_framework import serializers

from apps.authentication.models import APIKey
from apps.teams.api.serializers import CompanySerializer
from apps.users.api.serializers import UserSerializer


class APIKeySerializer(serializers.ModelSerializer):
    """
    Serializer for APIKey model (read operations).

    Does not expose the actual key value for security.
    """

    company_details = CompanySerializer(source="company", read_only=True)
    created_by_details = UserSerializer(source="created_by", read_only=True)
    is_valid = serializers.BooleanField(source="is_valid", read_only=True)

    class Meta:
        model = APIKey
        fields = [
            "id",
            "name",
            "prefix",
            "company",
            "company_details",
            "created_by",
            "created_by_details",
            "scopes",
            "last_used_at",
            "expires_at",
            "is_active",
            "is_valid",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "prefix",
            "created_by",
            "last_used_at",
            "created_at",
            "updated_at",
        ]


class APIKeyCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating API keys.

    Returns the raw key on creation (only time it's visible).
    """

    key = serializers.CharField(read_only=True)

    class Meta:
        model = APIKey
        fields = [
            "id",
            "name",
            "scopes",
            "expires_at",
            "key",
        ]
        read_only_fields = ["id", "key"]

    def create(self, validated_data):
        """
        Create API key and return raw key.

        Args:
            validated_data: Validated data dictionary

        Returns:
            APIKey: Created API key instance
        """
        user = self.context["request"].user
        company = user.company

        if not company:
            raise serializers.ValidationError(
                {"company": "You must be a member of a company to create API keys."}
            )

        # Create API key using model method
        api_key, raw_key = APIKey.create_key(
            name=validated_data["name"],
            company=company,
            created_by=user,
            scopes=validated_data.get("scopes", []),
            expires_at=validated_data.get("expires_at"),
        )

        # Attach raw key to instance for serialization
        api_key._raw_key = raw_key

        return api_key

    def to_representation(self, instance):
        """
        Override to include raw key in response.

        Args:
            instance: APIKey instance

        Returns:
            dict: Serialized representation
        """
        data = super().to_representation(instance)

        # Include raw key if available (only on creation)
        if hasattr(instance, "_raw_key"):
            data["key"] = instance._raw_key
            data["prefix"] = instance.prefix
            data["message"] = "Store this key securely. It will not be shown again."

        return data
