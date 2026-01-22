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
    """Maximum retry attempts for failed requests."""


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
