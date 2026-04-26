"""
OpenAIProvider - Provider implementation for OpenAI API.

Uses the OpenAI SDK to communicate with GPT models.
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
OPENAI_MODELS = [
    ModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        tier=CostTier.BUDGET,
        tiers=[CostTier.BUDGET],
        capabilities=ModelCapabilities(
            coding=True,
            reasoning=False,
            research=True,
            tool_use=True,
            long_context=False,
        ),
        max_tokens=16384,
    ),
    ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
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
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        tier=CostTier.ADVANCED,
        tiers=[CostTier.ADVANCED],
        capabilities=ModelCapabilities(
            coding=True,
            reasoning=True,
            research=True,
            tool_use=True,
            long_context=True,
        ),
        max_tokens=4096,
    ),
    ModelInfo(
        id="o1",
        name="O1",
        tier=CostTier.PREMIUM,
        tiers=[CostTier.PREMIUM],
        capabilities=ModelCapabilities(
            coding=True,
            reasoning=True,
            research=True,
            tool_use=True,
            long_context=True,
        ),
        max_tokens=100000,
    ),
    ModelInfo(
        id="gpt-5",
        name="GPT-5",
        tier=CostTier.PREMIUM,
        tiers=[CostTier.PREMIUM],
        capabilities=ModelCapabilities(
            coding=True,
            reasoning=True,
            research=True,
            tool_use=True,
            long_context=True,
        ),
        max_tokens=128000,
    ),
]

# Cost per 1K tokens in USD
TOKEN_COSTS = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "o1": {"input": 0.015, "output": 0.06},
    "gpt-5": {"input": 0.02, "output": 0.08},
}

# Models that require temperature == 1.0 (per CLAUDE.md)
TEMPERATURE_LOCKED_MODELS = {"gpt-5"}


class OpenAIProvider(Provider):
    """Provider implementation for OpenAI API.

    Implements the Provider interface for GPT models via the
    OpenAI Python SDK. All configuration is passed explicitly -
    no environment variable discovery.

    Example:
        config = ProviderConfig(
            api_key="sk-...",
            timeout=30,
        )
        provider = OpenAIProvider(config)
        result = provider.complete(
            messages=[Message(role="user", content="Hello")],
            model="gpt-4o",
        )
    """

    def __init__(self, config: ProviderConfig):
        """Initialize OpenAI provider.

        Args:
            config: Provider configuration with API key
        """
        super().__init__(config)
        self._client = None  # Lazy initialization

    def _get_client(self):
        """Get or create the OpenAI client.

        Lazy initialization to avoid import errors if SDK not installed.

        Returns:
            OpenAI client instance

        Raises:
            ImportError: If openai SDK is not installed
        """
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "openai SDK not installed. Install with: pip install openai"
                )

            self._client = openai.OpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                timeout=float(self._config.timeout),
            )
        return self._client

    @property
    def name(self) -> str:
        """Provider name."""
        return "openai"

    @property
    def cli_command(self) -> str:
        """CLI command for OpenAI sessions."""
        return "openai"

    @property
    def models(self) -> list[ModelInfo]:
        """Available GPT models."""
        return list(OPENAI_MODELS)

    def complete(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResult:
        """Generate completion using OpenAI API.

        Args:
            messages: Conversation messages
            model: Model ID (defaults to gpt-4o)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (ignored for gpt-5)

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
            model = "gpt-4o"

        # Validate model exists
        if not any(m.id == model for m in self.models):
            raise ModelNotAvailableError(
                f"Model '{model}' not available",
                provider=self.name,
            )

        # Per CLAUDE.md: gpt-5 requires temperature == 1.0
        effective_temperature = temperature
        if model in TEMPERATURE_LOCKED_MODELS:
            effective_temperature = 1.0

        try:
            client = self._get_client()

            # Convert our Message format to OpenAI format
            openai_messages = [
                {"role": m.role, "content": m.content}
                for m in messages
            ]

            # Make the API call
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=effective_temperature,
                messages=openai_messages,
            )

            # Extract content
            content = ""
            if response.choices:
                choice = response.choices[0]
                if choice.message and choice.message.content:
                    content = choice.message.content

            # Determine stop reason
            stop_reason = None
            if response.choices:
                stop_reason = response.choices[0].finish_reason

            return CompletionResult(
                content=content,
                model=response.model,
                usage={
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
                stop_reason=stop_reason,
            )

        except ImportError:
            raise
        except Exception as e:
            # Handle specific OpenAI exceptions
            self._handle_exception(e)

    def _handle_exception(self, e: Exception) -> None:
        """Convert OpenAI SDK exceptions to our exception types.

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
                f"OpenAI authentication failed: {error_msg}",
                provider=self.name,
                cause=e,
            )

        if "RateLimitError" in error_type or "429" in error_msg:
            raise RateLimitError(
                f"OpenAI rate limit exceeded: {error_msg}",
                provider=self.name,
                cause=e,
            )

        if "NotFoundError" in error_type or "404" in error_msg:
            raise ModelNotAvailableError(
                f"OpenAI model not found: {error_msg}",
                provider=self.name,
                cause=e,
            )

        if "Timeout" in error_type or "timeout" in error_msg.lower():
            raise ProviderTimeoutError(
                f"OpenAI request timed out: {error_msg}",
                provider=self.name,
                timeout_seconds=self._config.timeout,
                cause=e,
            )

        if "Connection" in error_type or "connection" in error_msg.lower():
            raise ProviderConnectionError(
                f"OpenAI connection failed: {error_msg}",
                provider=self.name,
                cause=e,
            )

        # Check for status codes in error message
        if "500" in error_msg or "502" in error_msg or "503" in error_msg:
            raise APIError(
                f"OpenAI server error: {error_msg}",
                provider=self.name,
                status_code=500,
                cause=e,
            )

        if "400" in error_msg:
            raise APIError(
                f"OpenAI bad request: {error_msg}",
                provider=self.name,
                status_code=400,
                cause=e,
            )

        # Generic provider error for anything else
        raise ProviderError(
            f"OpenAI API error: {error_msg}",
            provider=self.name,
            cause=e,
        )

    def supports_streaming(self) -> bool:
        """Whether streaming is supported.

        Returns:
            True - OpenAI supports streaming
        """
        return True

    def _get_default_token_costs(self, model_id: str) -> dict[str, float]:
        """Get default token costs for OpenAI models.

        These are fallback costs used when not overridden in config.

        Args:
            model_id: Model ID

        Returns:
            Dict with 'input' and 'output' costs in USD per 1K tokens
        """
        return TOKEN_COSTS.get(model_id, {"input": 0.0, "output": 0.0})
