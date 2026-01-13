"""
Custom authentication backends for DRF.
"""

from rest_framework import authentication
from rest_framework import exceptions

from apps.authentication.models import APIKey


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    API Key authentication backend for Django REST Framework.

    Authenticates requests using the X-API-Key header.
    Returns the user who created the API key as the authenticated user.
    """

    keyword = "X-API-Key"

    def authenticate(self, request):
        """
        Authenticate the request using API key in header.

        Args:
            request: The HTTP request

        Returns:
            tuple: (user, api_key) if authentication succeeds
            None: If no API key header is present

        Raises:
            AuthenticationFailed: If the API key is invalid
        """
        api_key_header = request.META.get("HTTP_X_API_KEY")

        if not api_key_header:
            return None

        # Find API key by prefix for efficiency
        prefix = api_key_header[:8]
        api_keys = APIKey.objects.filter(
            prefix=prefix,
            is_active=True
        ).select_related("created_by", "company")

        # Verify the key
        for api_key in api_keys:
            if api_key.verify_key(api_key_header):
                if not api_key.is_valid():
                    raise exceptions.AuthenticationFailed("API key has expired or is inactive")

                # Update last used timestamp
                api_key.update_last_used()

                # Attach API key to request for later use
                request.api_key = api_key

                return (api_key.created_by, api_key)

        raise exceptions.AuthenticationFailed("Invalid API key")

    def authenticate_header(self, request):
        """
        Return the authentication scheme to use in WWW-Authenticate header.

        Args:
            request: The HTTP request

        Returns:
            str: The authentication scheme
        """
        return self.keyword
