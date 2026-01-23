"""
Base provider interface and data classes.

This module re-exports from shared.provider_types for backwards compatibility.
All new code should import directly from shared.
"""

# Re-export all provider types from shared
try:
    # When running from quinnai root (installed package)
    from shared.provider_types import (
        CostTier,
        ModelCapabilities,
        ModelInfo,
        ProviderConfig,
        RetryConfig,
        TokenCosts,
        Message,
        CompletionResult,
        Provider,
        ProviderError,
        AuthenticationError,
        RateLimitError,
        ModelNotAvailableError,
        ProviderConnectionError,
        ProviderTimeoutError,
        APIError,
        is_retryable_error,
        calculate_retry_delay,
        with_retry,
        with_retry_async,
    )
except ImportError:
    # Fallback for direct cli imports
    from quinnai.shared.provider_types import (
        CostTier,
        ModelCapabilities,
        ModelInfo,
        ProviderConfig,
        RetryConfig,
        TokenCosts,
        Message,
        CompletionResult,
        Provider,
        ProviderError,
        AuthenticationError,
        RateLimitError,
        ModelNotAvailableError,
        ProviderConnectionError,
        ProviderTimeoutError,
        APIError,
        is_retryable_error,
        calculate_retry_delay,
        with_retry,
        with_retry_async,
    )

__all__ = [
    "CostTier",
    "ModelCapabilities",
    "ModelInfo",
    "ProviderConfig",
    "RetryConfig",
    "TokenCosts",
    "Message",
    "CompletionResult",
    "Provider",
    "ProviderError",
    "AuthenticationError",
    "RateLimitError",
    "ModelNotAvailableError",
    "ProviderConnectionError",
    "ProviderTimeoutError",
    "APIError",
    "is_retryable_error",
    "calculate_retry_delay",
    "with_retry",
    "with_retry_async",
]
