"""
Core utility functions.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    """
    Extract client IP address from request.

    Handles X-Forwarded-For header for proxied requests.

    Args:
        request: Django request object

    Returns:
        Client IP address as string
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def normalize_email(email: str) -> str:
    """
    Normalize email address to lowercase.

    Args:
        email: Email address to normalize

    Returns:
        Normalized email address
    """
    return email.lower().strip()


def sanitize_dict(data: Dict[str, Any], exclude_keys: list = None) -> Dict[str, Any]:
    """
    Remove sensitive keys from dictionary for logging.

    Args:
        data: Dictionary to sanitize
        exclude_keys: List of keys to remove (defaults to common sensitive keys)

    Returns:
        Sanitized dictionary
    """
    if exclude_keys is None:
        exclude_keys = ["password", "token", "secret", "api_key", "access_token"]

    return {
        key: "***REDACTED***" if key in exclude_keys else value
        for key, value in data.items()
    }
