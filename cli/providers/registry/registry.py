"""
ProviderRegistry - Registry for LLM providers.

Manages provider registration and provides worker-based selection
of providers and models based on cost and skill requirements.
"""

from typing import Optional

from cli.providers.base import (
    CostTier,
    ModelInfo,
    ModelNotAvailableError,
    Provider,
)

from cli.providers.registry.base import (
    DEFAULT_THRESHOLDS,
    skills_to_capabilities,
)

from cli.providers.registry.selection import _select_model_for_tier


class ProviderRegistry:
    """Registry for available providers.

    Manages provider registration and provides worker-based selection
    of providers and models based on cost and skill requirements.

    No string dispatch - all behavior is polymorphic through Provider instances.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._providers: dict[str, Provider] = {}
        self._default_provider: Optional[str] = None
        # Configurable thresholds with defaults (copy to avoid mutation)
        self._thresholds: dict[str, int] = dict(DEFAULT_THRESHOLDS)
        # Authorized providers - empty list means all registered are authorized
        self._authorized_providers: list[str] = []

    @property
    def authorized_providers(self) -> list[str]:
        """Get authorized provider names.

        Returns:
            List of authorized provider names (empty = all authorized)
        """
        return self._authorized_providers

    def set_authorized_providers(self, providers: list[str]) -> None:
        """Set list of authorized providers.

        Args:
            providers: List of provider names (empty = all authorized)
        """
        self._authorized_providers = list(providers)

    def is_authorized(self, name: str) -> bool:
        """Check if a provider is authorized.

        Args:
            name: Provider name to check

        Returns:
            True if authorized (or no restrictions set)
        """
        if not self._authorized_providers:
            return True
        return name in self._authorized_providers

    @property
    def thresholds(self) -> dict[str, int]:
        """Get current skill thresholds.

        Returns:
            Dict mapping skill names to threshold values
        """
        return self._thresholds

    def set_thresholds(
        self,
        coding: Optional[int] = None,
        reasoning: Optional[int] = None,
        research: Optional[int] = None,
        management: Optional[int] = None,
        strategy: Optional[int] = None,
    ) -> None:
        """Set skill thresholds from config.

        Args:
            coding: Threshold for coding capability requirement
            reasoning: Threshold for reasoning capability requirement
            research: Threshold for research capability requirement
            management: Threshold for tool_use capability requirement
            strategy: Threshold for long_context capability requirement
        """
        if coding is not None:
            self._thresholds["coding"] = coding
        if reasoning is not None:
            self._thresholds["reasoning"] = reasoning
        if research is not None:
            self._thresholds["research"] = research
        if management is not None:
            self._thresholds["management"] = management
        if strategy is not None:
            self._thresholds["strategy"] = strategy

    def register(self, provider: Provider) -> None:
        """Register a provider.

        Args:
            provider: Provider instance to register
        """
        self._providers[provider.name] = provider

    def unregister(self, name: str) -> None:
        """Unregister a provider.

        Args:
            name: Provider name to unregister
        """
        if name in self._providers:
            del self._providers[name]
            if self._default_provider == name:
                self._default_provider = None

    def get(self, name: str) -> Provider:
        """Get provider by name.

        Args:
            name: Provider name

        Returns:
            Provider instance

        Raises:
            ValueError: If provider not found
        """
        if name not in self._providers:
            raise ValueError(f"Provider not found: {name}")
        return self._providers[name]

    def has(self, name: str) -> bool:
        """Check if provider is registered.

        Args:
            name: Provider name

        Returns:
            True if provider is registered
        """
        return name in self._providers

    def set_default(self, name: str) -> None:
        """Set default provider.

        Args:
            name: Provider name to set as default

        Raises:
            ValueError: If provider not found
        """
        if name not in self._providers:
            raise ValueError(f"Provider not found: {name}")
        self._default_provider = name

    @property
    def default(self) -> Provider:
        """Get default provider.

        Returns:
            Default provider instance

        Raises:
            ValueError: If no default set
        """
        if self._default_provider is None:
            raise ValueError("No default provider set")
        return self._providers[self._default_provider]

    @property
    def default_name(self) -> Optional[str]:
        """Get default provider name.

        Returns:
            Default provider name or None
        """
        return self._default_provider

    def select_for_worker(
        self,
        cost: int,
        skills: dict[str, int],
        preferred_provider: Optional[str] = None,
    ) -> tuple[Provider, ModelInfo]:
        """Select best provider and model for a worker.

        Derives required capabilities from worker skills and finds the
        best matching provider and model. Only considers authorized providers.

        Args:
            cost: Worker cost score (0-100)
            skills: Worker skills dict (skill_name -> score 0-100)
            preferred_provider: Optional preferred provider name

        Returns:
            Tuple of (Provider, ModelInfo)

        Raises:
            ValueError: If no provider can satisfy requirements
        """
        # Derive required capabilities from skills
        required = self._skills_to_capabilities(skills)

        # Try preferred provider first (if authorized)
        if (
            preferred_provider
            and preferred_provider in self._providers
            and self.is_authorized(preferred_provider)
        ):
            provider = self._providers[preferred_provider]
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                pass  # Fall through to other providers

        # Try default provider (if authorized)
        if (
            self._default_provider
            and self._default_provider != preferred_provider
            and self.is_authorized(self._default_provider)
        ):
            provider = self._providers[self._default_provider]
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                pass

        # Try all other authorized providers
        for name, provider in self._providers.items():
            if name == preferred_provider or name == self._default_provider:
                continue
            if not self.is_authorized(name):
                continue
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                continue

        raise ValueError(
            f"No provider can satisfy cost={cost}, capabilities={required}"
        )

    def _skills_to_capabilities(self, skills: dict[str, int]) -> list[str]:
        """Convert worker skills to required capabilities.

        Uses configurable thresholds set via set_thresholds().

        Args:
            skills: Worker skills dict

        Returns:
            List of required capability names
        """
        return skills_to_capabilities(skills, self._thresholds)

    def list_providers(self) -> list[str]:
        """List registered provider names.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    def get_model_for_tier(
        self,
        tier: CostTier,
        required_capabilities: Optional[list[str]] = None,
    ) -> tuple[Provider, ModelInfo]:
        """Get a model for a specific tier from any provider.

        Tries providers in order: default first, then others.
        Returns the first matching model at the requested tier.

        Args:
            tier: Target cost tier
            required_capabilities: Optional capability requirements

        Returns:
            Tuple of (Provider, ModelInfo)

        Raises:
            ValueError: If no model available for tier
        """
        fallback_chain = self._build_fallback_chain(tier, required_capabilities)
        if not fallback_chain:
            raise ValueError(f"No model available for tier {tier.value}")
        return fallback_chain[0]

    def _build_fallback_chain(
        self,
        tier: CostTier,
        required_capabilities: Optional[list[str]] = None,
    ) -> list[tuple[Provider, ModelInfo]]:
        """Build ordered list of provider/model pairs for fallback.

        Builds a list of (provider, model) tuples that can serve
        the requested tier. List is ordered by preference:
        1. Default provider first
        2. Other authorized providers in registration order

        Args:
            tier: Target cost tier
            required_capabilities: Optional capability requirements

        Returns:
            List of (Provider, ModelInfo) tuples in fallback order
        """
        if required_capabilities is None:
            required_capabilities = []

        fallback: list[tuple[Provider, ModelInfo]] = []

        # Build provider order: default first
        provider_order = []
        if self._default_provider and self.is_authorized(self._default_provider):
            provider_order.append(self._default_provider)
        for name in self._providers:
            if name not in provider_order and self.is_authorized(name):
                provider_order.append(name)

        # Try each provider
        for name in provider_order:
            provider = self._providers[name]
            try:
                model = _select_model_for_tier(provider, tier, required_capabilities)
                fallback.append((provider, model))
            except (ValueError, ModelNotAvailableError):
                continue

        return fallback

    def __len__(self) -> int:
        """Number of registered providers."""
        return len(self._providers)
