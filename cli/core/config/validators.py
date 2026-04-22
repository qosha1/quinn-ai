"""
Validation functions for QuinnAI configuration.

All validation logic lives here. No YAML I/O, no dataclass definitions.
"""

import re
import warnings
from pathlib import Path
from urllib.parse import urlparse

import yaml

from shared.exceptions import ConfigurationError
from .models import (
    PlaintextApiKeyWarning,
    ProviderSettings,
    ProvidersConfig,
    OrgConfig,
)


# API key format patterns for known providers
# These are minimum format checks, not full validation
API_KEY_PATTERNS: dict[str, re.Pattern] = {
    "anthropic": re.compile(r"^sk-ant-[a-zA-Z0-9_-]{20,}$"),
    "openai": re.compile(r"^sk-[a-zA-Z0-9_-]{20,}$"),
}

# Pattern to detect environment variable references
ENV_VAR_PATTERN = re.compile(r'\$\{[^}]+\}')


def validate_api_key_format(provider: str, api_key: str) -> bool:
    """Check if API key matches expected format for provider.

    Args:
        provider: Provider name (e.g., 'anthropic', 'openai')
        api_key: API key string to validate

    Returns:
        True if format is valid or provider has no known format
    """
    pattern = API_KEY_PATTERNS.get(provider)
    if pattern is None:
        return True
    return bool(pattern.match(api_key))


def validate_url(url: str) -> bool:
    """Check if URL is valid.

    Args:
        url: URL string to validate

    Returns:
        True if URL has valid format
    """
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except (ValueError, AttributeError):
        return False


def validate_provider_settings(
    provider_name: str,
    settings: ProviderSettings,
    require_api_key: bool = True,
) -> list[ConfigurationError]:
    """Validate settings for a single provider.

    Args:
        provider_name: Name of the provider
        settings: Provider settings to validate
        require_api_key: Whether to require non-empty API key

    Returns:
        List of ConfigurationError (empty if valid)
    """
    errors: list[ConfigurationError] = []

    if not settings.enabled:
        return errors

    if require_api_key and not settings.api_key:
        errors.append(ConfigurationError(
            "API key is required but not set. "
            f"Set the environment variable or configure directly.",
            provider=provider_name,
            field="api_key",
        ))
    elif settings.api_key:
        if not validate_api_key_format(provider_name, settings.api_key):
            errors.append(ConfigurationError(
                f"API key does not match expected format for {provider_name}. "
                "Please verify your API key is correct.",
                provider=provider_name,
                field="api_key",
            ))

    if settings.base_url and not validate_url(settings.base_url):
        errors.append(ConfigurationError(
            f"Invalid URL format: {settings.base_url}",
            provider=provider_name,
            field="base_url",
        ))

    if settings.timeout <= 0:
        errors.append(ConfigurationError(
            f"Timeout must be positive, got {settings.timeout}",
            provider=provider_name,
            field="timeout",
        ))

    if settings.max_retries < 0:
        errors.append(ConfigurationError(
            f"max_retries must be non-negative, got {settings.max_retries}",
            provider=provider_name,
            field="max_retries",
        ))

    return errors


def validate_providers_config(
    config: ProvidersConfig,
    require_default_provider: bool = True,
) -> list[ConfigurationError]:
    """Validate complete providers configuration.

    Performs startup validation to catch configuration errors early:
    - Checks that default provider exists and is enabled
    - Validates each enabled provider's settings
    - Checks API key format where applicable
    - Validates endpoint URLs

    Args:
        config: ProvidersConfig to validate
        require_default_provider: Whether default must be enabled

    Returns:
        List of ConfigurationError (empty if valid)
    """
    errors: list[ConfigurationError] = []

    if not config.providers:
        errors.append(ConfigurationError(
            "No providers configured. At least one provider must be defined."
        ))
        return errors

    if require_default_provider:
        if config.default not in config.providers:
            errors.append(ConfigurationError(
                f"Default provider '{config.default}' is not in providers list. "
                f"Available providers: {list(config.providers.keys())}"
            ))
        elif not config.providers[config.default].enabled:
            errors.append(ConfigurationError(
                f"Default provider '{config.default}' is disabled. "
                "Enable it or change the default provider."
            ))

    for name, settings in config.providers.items():
        provider_errors = validate_provider_settings(name, settings)
        errors.extend(provider_errors)

    enabled_providers = [
        name for name, settings in config.providers.items()
        if settings.enabled
    ]
    if not enabled_providers:
        errors.append(ConfigurationError(
            "No providers are enabled. At least one provider must be enabled."
        ))

    return errors


def validate_org_config(config: OrgConfig) -> list[ConfigurationError]:
    """Validate complete organization configuration.

    Args:
        config: OrgConfig to validate

    Returns:
        List of ConfigurationError (empty if valid)
    """
    return validate_providers_config(config.providers)


def validate_and_raise(config: ProvidersConfig | OrgConfig) -> None:
    """Validate configuration and raise on first error.

    Convenience function for startup validation that fails fast.

    Args:
        config: Configuration to validate

    Raises:
        ConfigurationError: If any validation error found
    """
    if isinstance(config, OrgConfig):
        errors = validate_org_config(config)
    else:
        errors = validate_providers_config(config)

    if errors:
        raise errors[0]


def is_plaintext_api_key(value: str) -> bool:
    """Check if a value appears to be a plaintext API key (not an env var reference).

    Args:
        value: The API key value to check

    Returns:
        True if the value looks like a plaintext key (not an env var reference)
    """
    if not value:
        return False
    if ENV_VAR_PATTERN.search(value):
        return False
    for pattern in API_KEY_PATTERNS.values():
        if pattern.match(value):
            return True
    if value.startswith("sk-") and len(value) > 20:
        return True
    return False


def check_plaintext_api_keys(config_path: Path) -> list[tuple[str, str]]:
    """Check a config file for plaintext API keys.

    Reads the raw YAML to detect keys before environment variable expansion.

    Args:
        config_path: Path to providers.yaml file

    Returns:
        List of (provider_name, field_name) tuples for detected plaintext keys
    """
    if not config_path.exists():
        return []

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        return []

    plaintext_keys: list[tuple[str, str]] = []

    for provider_name, provider_data in data.get("providers", {}).items():
        if not isinstance(provider_data, dict):
            continue

        api_key = provider_data.get("api_key", "")
        if is_plaintext_api_key(api_key):
            plaintext_keys.append((provider_name, "api_key"))

    return plaintext_keys


def warn_plaintext_api_keys(config_path: Path) -> None:
    """Issue warnings for any plaintext API keys found in config.

    Args:
        config_path: Path to providers.yaml file
    """
    plaintext_keys = check_plaintext_api_keys(config_path)

    for provider_name, field_name in plaintext_keys:
        warnings.warn(
            f"Plaintext API key detected for provider '{provider_name}' in {config_path}. "
            f"Use environment variable reference (e.g., ${{ANTHROPIC_API_KEY}}) instead.",
            PlaintextApiKeyWarning,
            stacklevel=3,
        )


def mask_secret(value: str, visible_chars: int = 4) -> str:
    """Mask a secret value, showing only the first few characters.

    Args:
        value: The secret to mask
        visible_chars: Number of characters to show at the start

    Returns:
        Masked string like "sk-a****" or "****" if too short
    """
    if not value:
        return ""
    if len(value) <= visible_chars:
        return "*" * len(value)
    return value[:visible_chars] + "*" * (len(value) - visible_chars)


def mask_provider_settings(settings: ProviderSettings) -> dict:
    """Create a dict representation of provider settings with masked secrets.

    Args:
        settings: ProviderSettings to mask

    Returns:
        Dict with api_key masked
    """
    return {
        "enabled": settings.enabled,
        "api_key": mask_secret(settings.api_key) if settings.api_key else "",
        "base_url": settings.base_url,
        "timeout": settings.timeout,
        "max_retries": settings.max_retries,
    }


def mask_providers_config(config: ProvidersConfig) -> dict:
    """Create a dict representation of providers config with masked secrets.

    Args:
        config: ProvidersConfig to mask

    Returns:
        Dict safe for display/logging
    """
    return {
        "default": config.default,
        "providers": {
            name: mask_provider_settings(settings)
            for name, settings in config.providers.items()
        },
        "thresholds": {
            "coding": config.thresholds.coding,
            "reasoning": config.thresholds.reasoning,
            "research": config.thresholds.research,
        },
    }
