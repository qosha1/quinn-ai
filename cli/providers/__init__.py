"""AI provider implementations."""

# Re-export base types
from cli.providers.base import (
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
    from cli.providers.anthropic import AnthropicProvider
    return AnthropicProvider


def get_openai_provider():
    """Get OpenAIProvider class (lazy import)."""
    from cli.providers.openai import OpenAIProvider
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
