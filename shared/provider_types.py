"""
Provider interfaces and data classes for QuinnAI.

Defines the abstract Provider class and supporting data structures
that all AI provider implementations must use.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Import canonical Message from shared.core
from shared.core import Message


class CostTier(str, Enum):
    """Model cost/quality tiers.

    Maps worker cost scores to model quality tiers:
    - BUDGET (0-30): Fast, cheap models for simple tasks
    - STANDARD (31-60): Balanced models for general purpose
    - ADVANCED (61-80): High capability for complex reasoning
    - PREMIUM (81-100): Best available for strategic decisions
    """

    BUDGET = "budget"
    STANDARD = "standard"
    ADVANCED = "advanced"
    PREMIUM = "premium"


@dataclass
class ModelCapabilities:
    """Capabilities available for a model.

    Each capability indicates what tasks the model can perform well.
    Used for matching worker skills to model abilities.
    """

    coding: bool = False
    """Code generation and analysis capability."""

    reasoning: bool = False
    """Complex reasoning and problem-solving capability."""

    research: bool = False
    """Information retrieval and synthesis capability."""

    tool_use: bool = False
    """Function/tool calling capability."""

    long_context: bool = False
    """Extended context window capability."""

    def has_capabilities(self, required: list[str]) -> bool:
        """Check if model has all required capabilities.

        Args:
            required: List of capability names to check

        Returns:
            True if all required capabilities are present
        """
        for cap in required:
            if not getattr(self, cap, False):
                return False
        return True


@dataclass
class ModelInfo:
    """Information about a specific model.

    Describes a model's identity, cost tier, capabilities, and limits.
    Supports both the legacy cost_tier tuple and the new tier-based selection.
    """

    id: str
    """Model identifier for API calls (e.g., 'claude-3-5-sonnet-20241022')."""

    name: str
    """Human-readable model name (e.g., 'Claude 3.5 Sonnet')."""

    cost_tier: tuple[int, int] = (0, 100)
    """Min and max cost scores (0-100) this model serves (legacy)."""

    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    """What tasks this model can perform."""

    max_tokens: int = 4096
    """Maximum tokens for generation."""

    tier: Optional[CostTier] = None
    """Explicit tier assignment (preferred over cost_tier)."""

    tiers: Optional[list[CostTier]] = None
    """Multiple tiers this model can serve (e.g., sonnet serves standard and advanced)."""

    temperature: Optional[float] = None
    """Override default temperature (e.g., gpt-5 requires 1.0)."""

    def matches_cost(self, cost: int) -> bool:
        """Check if this model serves the given cost tier.

        Args:
            cost: Worker cost score (0-100)

        Returns:
            True if cost falls within this model's tier
        """
        return self.cost_tier[0] <= cost <= self.cost_tier[1]

    def matches_tier(self, tier: CostTier) -> bool:
        """Check if this model serves the given tier.

        Args:
            tier: CostTier to check

        Returns:
            True if model serves this tier
        """
        if self.tiers:
            return tier in self.tiers
        if self.tier:
            return self.tier == tier
        # Fall back to cost_tier mapping
        return self._tier_from_cost_range() == tier

    def _tier_from_cost_range(self) -> CostTier:
        """Derive tier from legacy cost_tier range."""
        min_cost = self.cost_tier[0]
        if min_cost <= 30:
            return CostTier.BUDGET
        elif min_cost <= 60:
            return CostTier.STANDARD
        elif min_cost <= 80:
            return CostTier.ADVANCED
        else:
            return CostTier.PREMIUM


@dataclass
class RetryConfig:
    """Configuration for retry behavior on transient failures.

    Controls exponential backoff parameters for retrying failed provider calls.
    Only transient errors (connection, timeout, 429, 5xx) are retried.
    Client errors (4xx except 429) are not retried.
    """

    max_retries: int = 3
    """Maximum number of retry attempts (0 = no retries)."""

    initial_delay: float = 1.0
    """Initial delay in seconds before first retry."""

    max_delay: float = 60.0
    """Maximum delay in seconds (caps exponential growth)."""

    exponential_base: float = 2.0
    """Base for exponential backoff calculation."""

    jitter: bool = True
    """Add random jitter to delays to avoid thundering herd."""


@dataclass
class ProviderConfig:
    """Configuration for a provider.

    All configuration values are explicitly provided - no discovery.
    """

    api_key: str
    """API key for authentication."""

    base_url: Optional[str] = None
    """Custom API endpoint (provider-specific default if None)."""

    timeout: int = 30
    """Request timeout in seconds."""

    max_retries: int = 3
    """Maximum retry attempts for failed requests (legacy, use retry_config)."""

    retry_config: Optional[RetryConfig] = None
    """Detailed retry configuration. If None, uses default RetryConfig with max_retries."""

    def get_retry_config(self) -> RetryConfig:
        """Get effective retry configuration.

        Returns RetryConfig, using legacy max_retries if retry_config not set.
        """
        if self.retry_config is not None:
            return self.retry_config
        return RetryConfig(max_retries=self.max_retries)


@dataclass
class CompletionResult:
    """Result from a completion call.

    Contains the generated content and metadata about the generation.
    """

    content: str
    """Generated text content."""

    model: str
    """Model ID that was used."""

    usage: dict[str, int]
    """Token usage: {'input_tokens': N, 'output_tokens': M}."""

    stop_reason: Optional[str] = None
    """Why generation stopped: 'end_turn', 'max_tokens', etc."""


class Provider(ABC):
    """Abstract base for AI providers.

    All provider implementations MUST inherit from this class and implement
    all abstract methods. This ensures a consistent interface regardless of
    which AI provider is being used.

    Implementations MUST NOT:
    - Have module-level side effects (no code runs on import)
    - Use string-based dispatch for behavior
    - Discover configuration (all config passed explicitly)
    """

    def __init__(self, config: ProviderConfig):
        """Initialize provider with configuration.

        Args:
            config: Provider configuration (passed explicitly, not discovered)
        """
        self._config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'anthropic', 'openai').

        Returns:
            Unique identifier for this provider
        """
        pass

    @property
    def cli_command(self) -> str:
        """CLI command for this provider's session.

        Returns the command to spawn a session for this provider.
        Override in subclasses for provider-specific commands.

        Returns:
            CLI command name (e.g., 'claude' for Anthropic)
        """
        # Default implementation - subclasses should override
        return self.name

    @property
    @abstractmethod
    def models(self) -> list[ModelInfo]:
        """Available models from this provider.

        Returns:
            List of ModelInfo objects for all available models
        """
        pass

    def select_model(
        self,
        cost: int,
        required_capabilities: Optional[list[str]] = None,
    ) -> ModelInfo:
        """Select best model for cost and capabilities.

        Args:
            cost: Worker cost score (0-100)
            required_capabilities: Required capability names

        Returns:
            Best matching ModelInfo

        Raises:
            ValueError: If no suitable model available
        """
        if required_capabilities is None:
            required_capabilities = []

        # Find all models that match cost tier
        matching = [m for m in self.models if m.matches_cost(cost)]

        if not matching:
            raise ValueError(
                f"No {self.name} model available for cost={cost}"
            )

        # Filter by capabilities
        if required_capabilities:
            capable = [
                m for m in matching
                if m.capabilities.has_capabilities(required_capabilities)
            ]
            if capable:
                matching = capable

        # Return first matching (implementations should order by preference)
        return matching[0]

    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResult:
        """Generate completion from messages.

        Args:
            messages: Conversation messages
            model: Specific model ID (uses cost-selected if not provided)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            CompletionResult with generated content

        Raises:
            ProviderError: If the API call fails
        """
        pass

    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming responses.

        Returns:
            True if streaming is supported, False otherwise
        """
        pass

    def get_token_costs(self, model_id: str) -> dict[str, float]:
        """Get cost per 1K tokens for a model.

        Default implementation returns zeros - providers should override
        with their actual pricing.

        Args:
            model_id: Model ID to get costs for

        Returns:
            Dict with 'input' and 'output' costs per 1K tokens in USD
        """
        return {"input": 0.0, "output": 0.0}

    def estimate_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost for a completion request.

        Uses get_token_costs() to calculate estimated cost based on
        token counts.

        Args:
            model_id: Model ID for pricing
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        costs = self.get_token_costs(model_id)
        input_cost = (input_tokens / 1000) * costs.get("input", 0.0)
        output_cost = (output_tokens / 1000) * costs.get("output", 0.0)
        return input_cost + output_cost


class ProviderError(Exception):
    """Base exception for provider errors.

    All provider-specific exceptions should inherit from this.
    """

    def __init__(self, message: str, provider: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.provider = provider
        self.cause = cause


class AuthenticationError(ProviderError):
    """Raised when authentication fails."""
    pass


class RateLimitError(ProviderError):
    """Raised when rate limit is exceeded."""
    pass


class ModelNotAvailableError(ProviderError):
    """Raised when requested model is not available."""
    pass


class ProviderConnectionError(ProviderError):
    """Raised when connection to provider API fails.

    This includes network errors, DNS failures, SSL errors, and
    other connection-level issues.
    """
    pass


class ProviderTimeoutError(ProviderError):
    """Raised when provider API request times out.

    Includes both connection timeouts and read timeouts.
    """

    def __init__(
        self,
        message: str,
        provider: str,
        timeout_seconds: float,
        cause: Exception | None = None,
    ):
        super().__init__(message, provider, cause)
        self.timeout_seconds = timeout_seconds


class APIError(ProviderError):
    """Raised for API-level errors from the provider.

    This includes server errors (5xx), bad requests (4xx not covered
    by specific exceptions), and other API-level failures.
    """

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, provider, cause)
        self.status_code = status_code


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable (transient).

    Retryable errors:
    - ProviderConnectionError: Network/connection issues
    - ProviderTimeoutError: Request timeouts
    - RateLimitError: 429 rate limiting
    - APIError with 5xx status codes (server errors)

    Non-retryable errors:
    - AuthenticationError: Credentials won't change between retries
    - ModelNotAvailableError: Model availability won't change
    - APIError with 4xx status codes (except 429): Client errors
    - Any other ProviderError: Unknown errors, safer not to retry

    Args:
        error: The exception to check

    Returns:
        True if the error is transient and should be retried
    """
    # Connection and timeout errors are always retryable
    if isinstance(error, (ProviderConnectionError, ProviderTimeoutError)):
        return True

    # Rate limit errors (429) are retryable
    if isinstance(error, RateLimitError):
        return True

    # API errors: only retry 5xx server errors
    if isinstance(error, APIError):
        if error.status_code is not None:
            return error.status_code >= 500
        # Unknown status code - don't retry
        return False

    # Auth errors and model availability errors are not retryable
    if isinstance(error, (AuthenticationError, ModelNotAvailableError)):
        return False

    # Other ProviderErrors - don't retry by default
    return False


def calculate_retry_delay(
    retry_config: RetryConfig,
    attempt: int,
) -> float:
    """Calculate delay before next retry attempt.

    Uses exponential backoff with optional jitter.
    Formula: min(initial_delay * (base ^ attempt), max_delay) + jitter

    Args:
        retry_config: Retry configuration
        attempt: Current attempt number (0-indexed, so first retry is attempt=0)

    Returns:
        Delay in seconds before next retry
    """
    import random

    delay = retry_config.initial_delay * (retry_config.exponential_base ** attempt)
    delay = min(delay, retry_config.max_delay)

    if retry_config.jitter:
        # Add random jitter up to 25% of delay
        jitter_amount = delay * 0.25 * random.random()
        delay += jitter_amount

    return delay


def with_retry(
    func: callable,
    retry_config: RetryConfig,
    provider_name: str = "unknown",
) -> callable:
    """Wrap a function with retry logic for transient failures.

    Creates a wrapper that automatically retries the function on transient errors
    using exponential backoff. Non-retryable errors are raised immediately.

    Args:
        func: The function to wrap (must be callable)
        retry_config: Retry configuration
        provider_name: Provider name for logging/error context

    Returns:
        Wrapped function with retry logic

    Example:
        ```python
        config = RetryConfig(max_retries=3)
        retryable_call = with_retry(provider.complete, config, "anthropic")
        result = retryable_call(messages=messages, model="claude-3")
        ```
    """
    import functools
    import time
    import logging

    logger = logging.getLogger(__name__)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        last_error: Exception | None = None

        for attempt in range(retry_config.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e

                # Check if this error is retryable
                if not is_retryable_error(e):
                    raise

                # Check if we have retries remaining
                if attempt >= retry_config.max_retries:
                    logger.warning(
                        f"[{provider_name}] Max retries ({retry_config.max_retries}) "
                        f"exhausted. Last error: {e}"
                    )
                    raise

                # Calculate delay and sleep
                delay = calculate_retry_delay(retry_config, attempt)
                logger.info(
                    f"[{provider_name}] Retryable error on attempt {attempt + 1}: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                time.sleep(delay)

        # Should not reach here, but just in case
        if last_error:
            raise last_error

    return wrapper


async def with_retry_async(
    func: callable,
    retry_config: RetryConfig,
    provider_name: str = "unknown",
) -> callable:
    """Async version of with_retry for async provider calls.

    Creates an async wrapper that automatically retries the function on transient
    errors using exponential backoff. Non-retryable errors are raised immediately.

    Args:
        func: The async function to wrap (must be async callable)
        retry_config: Retry configuration
        provider_name: Provider name for logging/error context

    Returns:
        Wrapped async function with retry logic
    """
    import functools
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        last_error: Exception | None = None

        for attempt in range(retry_config.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e

                # Check if this error is retryable
                if not is_retryable_error(e):
                    raise

                # Check if we have retries remaining
                if attempt >= retry_config.max_retries:
                    logger.warning(
                        f"[{provider_name}] Max retries ({retry_config.max_retries}) "
                        f"exhausted. Last error: {e}"
                    )
                    raise

                # Calculate delay and sleep
                delay = calculate_retry_delay(retry_config, attempt)
                logger.info(
                    f"[{provider_name}] Retryable error on attempt {attempt + 1}: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        if last_error:
            raise last_error

    return wrapper
