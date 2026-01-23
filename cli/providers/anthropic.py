"""
AnthropicProvider - Provider implementation for Claude API.

Uses the Anthropic SDK to communicate with Claude models.
All configuration is explicit - no environment variable discovery.
"""

from typing import Optional

from cli.providers.base import (
    Provider,
    ProviderConfig,
    ModelInfo,
    ModelCapabilities,
    CostTier,
    CompletionResult,
    ProviderError,
    AuthenticationError,
    RateLimitError,
    ModelNotAvailableError,
    ProviderConnectionError,
    ProviderTimeoutError,
    APIError,
)
from shared.core import Message


# Model definitions with explicit capabilities and tier mappings
ANTHROPIC_MODELS = [
    ModelInfo(
        id="claude-3-5-haiku-20241022",
        name="Claude 3.5 Haiku",
        tier=CostTier.BUDGET,
        tiers=[CostTier.BUDGET],
        capabilities=ModelCapabilities(
            coding=True,
            reasoning=False,
            research=True,
            tool_use=True,
            long_context=False,
        ),
        max_tokens=8192,
    ),
    ModelInfo(
        id="claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        tier=CostTier.STANDARD,
        tiers=[CostTier.STANDARD, CostTier.ADVANCED],
        capabilities=ModelCapabilities(
            coding=True,
            reasoning=True,
            research=True,
            tool_use=True,
            long_context=True,
        ),
        max_tokens=16384,
    ),
    ModelInfo(
        id="claude-opus-4-5-20251101",
        name="Claude Opus 4.5",
        tier=CostTier.PREMIUM,
        tiers=[CostTier.PREMIUM],
        capabilities=ModelCapabilities(
            coding=True,
            reasoning=True,
            research=True,
            tool_use=True,
            long_context=True,
        ),
        max_tokens=32768,
    ),
]

# Cost per 1K tokens in USD (as of 2024)
TOKEN_COSTS = {
    "claude-3-5-haiku-20241022": {"input": 0.00025, "output": 0.00125},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-opus-4-5-20251101": {"input": 0.015, "output": 0.075},
}


class AnthropicProvider(Provider):
    """Provider implementation for Anthropic Claude API.

    Implements the Provider interface for Claude models via the
    Anthropic Python SDK. All configuration is passed explicitly -
    no environment variable discovery.

    Example:
        config = ProviderConfig(
            api_key="sk-ant-...",
            timeout=30,
        )
        provider = AnthropicProvider(config)
        result = provider.complete(
            messages=[Message(role="user", content="Hello")],
            model="claude-sonnet-4-20250514",
        )
    """

    def __init__(self, config: ProviderConfig):
        """Initialize Anthropic provider.

        Args:
            config: Provider configuration with API key
        """
        super().__init__(config)
        self._client = None  # Lazy initialization

    def _get_client(self):
        """Get or create the Anthropic client.

        Lazy initialization to avoid import errors if SDK not installed.

        Returns:
            Anthropic client instance

        Raises:
            ImportError: If anthropic SDK is not installed
        """
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic SDK not installed. Install with: pip install anthropic"
                )

            self._client = anthropic.Anthropic(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                timeout=float(self._config.timeout),
            )
        return self._client

    @property
    def name(self) -> str:
        """Provider name."""
        return "anthropic"

    @property
    def cli_command(self) -> str:
        """CLI command for Claude Code sessions."""
        return "claude"

    @property
    def models(self) -> list[ModelInfo]:
        """Available Claude models."""
        return list(ANTHROPIC_MODELS)

    def complete(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResult:
        """Generate completion using Claude API.

        Args:
            messages: Conversation messages
            model: Model ID (defaults to claude-sonnet-4)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            CompletionResult with generated content

        Raises:
            AuthenticationError: If API key is invalid
            RateLimitError: If rate limit exceeded
            ModelNotAvailableError: If model doesn't exist
            ProviderTimeoutError: If request times out
            ProviderConnectionError: If connection fails
            APIError: For other API errors
        """
        if model is None:
            model = "claude-sonnet-4-20250514"

        # Validate model exists
        if not any(m.id == model for m in self.models):
            raise ModelNotAvailableError(
                f"Model '{model}' not available",
                provider=self.name,
            )

        try:
            client = self._get_client()

            # Convert our Message format to Anthropic format
            anthropic_messages = [
                {"role": m.role, "content": m.content}
                for m in messages
            ]

            # Make the API call
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=anthropic_messages,
            )

            # Extract content
            content = ""
            if response.content:
                for block in response.content:
                    if hasattr(block, "text"):
                        content += block.text

            return CompletionResult(
                content=content,
                model=response.model,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                stop_reason=response.stop_reason,
            )

        except ImportError:
            raise
        except Exception as e:
            # Handle specific Anthropic exceptions
            self._handle_exception(e)

    def _handle_exception(self, e: Exception) -> None:
        """Convert Anthropic SDK exceptions to our exception types.

        Args:
            e: Exception from SDK

        Raises:
            Appropriate ProviderError subclass
        """
        error_type = type(e).__name__
        error_msg = str(e)

        # Check for specific exception types
        if "AuthenticationError" in error_type or "401" in error_msg:
            raise AuthenticationError(
                f"Anthropic authentication failed: {error_msg}",
                provider=self.name,
                cause=e,
            )

        if "RateLimitError" in error_type or "429" in error_msg:
            raise RateLimitError(
                f"Anthropic rate limit exceeded: {error_msg}",
                provider=self.name,
                cause=e,
            )

        if "NotFoundError" in error_type or "404" in error_msg:
            raise ModelNotAvailableError(
                f"Anthropic model not found: {error_msg}",
                provider=self.name,
                cause=e,
            )

        if "Timeout" in error_type or "timeout" in error_msg.lower():
            raise ProviderTimeoutError(
                f"Anthropic request timed out: {error_msg}",
                provider=self.name,
                timeout_seconds=self._config.timeout,
                cause=e,
            )

        if "Connection" in error_type or "connection" in error_msg.lower():
            raise ProviderConnectionError(
                f"Anthropic connection failed: {error_msg}",
                provider=self.name,
                cause=e,
            )

        # Check for status codes in error message
        if "500" in error_msg or "502" in error_msg or "503" in error_msg:
            raise APIError(
                f"Anthropic server error: {error_msg}",
                provider=self.name,
                status_code=500,
                cause=e,
            )

        if "400" in error_msg:
            raise APIError(
                f"Anthropic bad request: {error_msg}",
                provider=self.name,
                status_code=400,
                cause=e,
            )

        # Generic provider error for anything else
        raise ProviderError(
            f"Anthropic API error: {error_msg}",
            provider=self.name,
            cause=e,
        )

    def supports_streaming(self) -> bool:
        """Whether streaming is supported.

        Returns:
            True - Anthropic supports streaming
        """
        return True

    def _get_default_token_costs(self, model_id: str) -> dict[str, float]:
        """Get default token costs for Anthropic models.

        These are fallback costs used when not overridden in config.

        Args:
            model_id: Model ID

        Returns:
            Dict with 'input' and 'output' costs in USD per 1K tokens
        """
        return TOKEN_COSTS.get(model_id, {"input": 0.0, "output": 0.0})
