"""
Configuration loading for provider registry.

This module handles loading providers from YAML configuration files
and creating configured registry instances.
"""

import os
import re
from pathlib import Path
from typing import Optional, Type

from cli.providers.base import Provider, ProviderConfig
from cli.providers.registry.registry import ProviderRegistry


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
        from cli.providers.anthropic import AnthropicProvider
        classes["anthropic"] = AnthropicProvider
    except ImportError:
        pass

    try:
        from cli.providers.openai import OpenAIProvider
        classes["openai"] = OpenAIProvider
    except ImportError:
        pass

    return classes


def create_registry_from_config(config: "ProvidersConfig") -> ProviderRegistry:
    """Create and configure a ProviderRegistry from ProvidersConfig.

    Initializes the registry with:
    - Skill thresholds from config
    - Authorized providers list from config
    - Default provider name from config (set after providers are registered)

    Note: Provider instances must be registered separately after creation
    since concrete Provider implementations are created elsewhere.

    Args:
        config: Loaded ProvidersConfig from providers.yaml

    Returns:
        Configured ProviderRegistry ready for provider registration

    Example:
        config = load_providers_config(config_path)
        registry = create_registry_from_config(config)
        registry.register(AnthropicProvider(provider_config))
        registry.set_default(config.default)  # After registration
    """
    # Avoid circular import
    from cli.core.config import ProvidersConfig

    registry = ProviderRegistry()

    # Set skill thresholds from config
    registry.set_thresholds(
        coding=config.thresholds.coding,
        reasoning=config.thresholds.reasoning,
        research=config.thresholds.research,
    )

    # Set authorized providers
    if config.authorized_providers:
        registry.set_authorized_providers(config.authorized_providers)

    return registry
