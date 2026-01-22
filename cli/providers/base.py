"""
Base provider interface and data classes.

This module re-exports from shared.provider_types for backwards compatibility.
All new code should import directly from shared.
"""

# Re-export all provider types from shared
from shared.provider_types import (
    ModelCapabilities,
    ModelInfo,
    ProviderConfig,
    Message,
    CompletionResult,
    Provider,
    ProviderError,
    AuthenticationError,
    RateLimitError,
    ModelNotAvailableError,
)

__all__ = [
    "ModelCapabilities",
    "ModelInfo",
    "ProviderConfig",
    "Message",
    "CompletionResult",
    "Provider",
    "ProviderError",
    "AuthenticationError",
    "RateLimitError",
    "ModelNotAvailableError",
]
