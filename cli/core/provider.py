"""
Provider registry and selection logic.

Manages registered providers and handles worker-to-model selection
based on cost and skill requirements.
"""

import os
from pathlib import Path
from typing import Optional, Type

from providers.base import (
    ModelInfo,
    Provider,
    ProviderConfig,
)


# Default thresholds - can be overridden via config
DEFAULT_CODING_THRESHOLD = 80
DEFAULT_REASONING_THRESHOLD = 60
DEFAULT_RESEARCH_THRESHOLD = 80


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
        # Configurable thresholds with defaults
        self._coding_threshold = DEFAULT_CODING_THRESHOLD
        self._reasoning_threshold = DEFAULT_REASONING_THRESHOLD
        self._research_threshold = DEFAULT_RESEARCH_THRESHOLD

    def set_thresholds(
        self,
        coding: Optional[int] = None,
        reasoning: Optional[int] = None,
        research: Optional[int] = None,
    ) -> None:
        """Set skill thresholds from config.

        Args:
            coding: Threshold for coding capability requirement
            reasoning: Threshold for reasoning capability requirement
            research: Threshold for research capability requirement
        """
        if coding is not None:
            self._coding_threshold = coding
        if reasoning is not None:
            self._reasoning_threshold = reasoning
        if research is not None:
            self._research_threshold = research

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
        best matching provider and model.

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

        # Try preferred provider first
        if preferred_provider and preferred_provider in self._providers:
            provider = self._providers[preferred_provider]
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                pass  # Fall through to other providers

        # Try default provider
        if self._default_provider and self._default_provider != preferred_provider:
            provider = self._providers[self._default_provider]
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                pass

        # Try all other providers
        for name, provider in self._providers.items():
            if name == preferred_provider or name == self._default_provider:
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
        required = []

        if skills.get("coding", 0) >= self._coding_threshold:
            required.append("coding")
        if skills.get("reasoning", 0) >= self._reasoning_threshold:
            required.append("reasoning")
        if skills.get("research", 0) >= self._research_threshold:
            required.append("research")

        return required

    def list_providers(self) -> list[str]:
        """List registered provider names.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    def __len__(self) -> int:
        """Number of registered providers."""
        return len(self._providers)


def _expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports ${VAR} syntax.

    Args:
        value: String potentially containing env vars

    Returns:
        String with env vars expanded
    """
    if "${" not in value:
        return value

    import re
    pattern = r'\$\{([^}]+)\}'

    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return re.sub(pattern, replace, value)


def load_providers_from_config(
    config_path: Path,
    provider_classes: Optional[dict[str, Type[Provider]]] = None,
) -> ProviderRegistry:
    """Load providers from YAML configuration.

    Configuration format:
    ```yaml
    default: anthropic
    providers:
      anthropic:
        enabled: true
        api_key: ${ANTHROPIC_API_KEY}
        timeout: 30
      openai:
        enabled: false
        api_key: ${OPENAI_API_KEY}
    ```

    Args:
        config_path: Path to providers.yaml
        provider_classes: Optional mapping of provider name -> class

    Returns:
        Initialized ProviderRegistry

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    import yaml

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError("Empty configuration file")

    registry = ProviderRegistry()

    # Default provider classes (lazy imports to avoid side effects)
    if provider_classes is None:
        provider_classes = _get_default_provider_classes()

    # Load each enabled provider
    for name, provider_config in config.get("providers", {}).items():
        if not provider_config.get("enabled", True):
            continue

        if name not in provider_classes:
            continue  # Skip unknown providers

        provider_class = provider_classes[name]

        # Create config with env var expansion
        api_key = provider_config.get("api_key", "")
        if isinstance(api_key, str):
            api_key = _expand_env_vars(api_key)

        base_url = provider_config.get("base_url")
        if isinstance(base_url, str):
            base_url = _expand_env_vars(base_url)

        pconfig = ProviderConfig(
            api_key=api_key,
            base_url=base_url if base_url else None,
            timeout=provider_config.get("timeout", 30),
            max_retries=provider_config.get("max_retries", 3),
        )

        # Initialize and register
        provider = provider_class(pconfig)
        registry.register(provider)

    # Set default if specified
    default_name = config.get("default")
    if default_name and registry.has(default_name):
        registry.set_default(default_name)
    elif len(registry) > 0:
        # Set first provider as default if not specified
        registry.set_default(registry.list_providers()[0])

    # Set thresholds from config if present
    thresholds = config.get("thresholds", {})
    registry.set_thresholds(
        coding=thresholds.get("coding"),
        reasoning=thresholds.get("reasoning"),
        research=thresholds.get("research"),
    )

    return registry


def _get_default_provider_classes() -> dict[str, Type[Provider]]:
    """Get default provider class mapping.

    Lazy import to avoid module-level side effects.

    Returns:
        Mapping of provider name -> provider class
    """
    # Import here to avoid circular imports and side effects
    classes: dict[str, Type[Provider]] = {}

    # Only import if the module exists and is implemented
    try:
        from providers.anthropic import AnthropicProvider
        classes["anthropic"] = AnthropicProvider
    except ImportError:
        pass

    try:
        from providers.openai import OpenAIProvider
        classes["openai"] = OpenAIProvider
    except ImportError:
        pass

    return classes
