"""AI provider implementations."""

# Re-export base types
from providers.base import (
    Provider,
    ProviderConfig,
    ModelInfo,
    ModelCapabilities,
    CostTier,
    CompletionResult,
    ProviderError,
)

# Lazy import concrete providers to avoid side effects
def get_anthropic_provider():
    """Get AnthropicProvider class (lazy import)."""
    from providers.anthropic import AnthropicProvider
    return AnthropicProvider


def get_openai_provider():
    """Get OpenAIProvider class (lazy import)."""
    from providers.openai import OpenAIProvider
    return OpenAIProvider


__all__ = [
    "Provider",
    "ProviderConfig",
    "ModelInfo",
    "ModelCapabilities",
    "CostTier",
    "CompletionResult",
    "ProviderError",
    "get_anthropic_provider",
    "get_openai_provider",
]
