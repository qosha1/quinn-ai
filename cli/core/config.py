"""
Configuration loading for QuinnAI CLI.

Follows "No Config Discovery" principle - all paths are passed explicitly.
No searching for config files, no environment variable magic for paths.
"""

import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yaml

from shared.exceptions import ConfigurationError


class PlaintextApiKeyWarning(UserWarning):
    """Warning raised when a plaintext API key is detected in config."""
    pass

from .constants import (
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_SKILL_THRESHOLD_CODING,
    DEFAULT_SKILL_THRESHOLD_REASONING,
    DEFAULT_SKILL_THRESHOLD_RESEARCH,
    DEFAULT_WORKER_COST,
)


@dataclass
class ProviderSettings:
    """Settings for a single provider."""
    enabled: bool = True
    api_key: str = ""
    base_url: Optional[str] = None
    timeout: int = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES


@dataclass
class ThresholdSettings:
    """Skill thresholds for capability requirements."""
    coding: int = DEFAULT_SKILL_THRESHOLD_CODING
    reasoning: int = DEFAULT_SKILL_THRESHOLD_REASONING
    research: int = DEFAULT_SKILL_THRESHOLD_RESEARCH


@dataclass
class ProvidersConfig:
    """Configuration from providers.yaml."""
    default: str = "anthropic"
    providers: dict[str, ProviderSettings] = field(default_factory=dict)
    thresholds: ThresholdSettings = field(default_factory=ThresholdSettings)


@dataclass
class WorkerTemplate:
    """Template defining skills and cost for a worker role."""
    description: str = ""
    skills: dict[str, int] = field(default_factory=dict)
    cost: int = DEFAULT_WORKER_COST


@dataclass
class WorkerTemplatesConfig:
    """Configuration from worker-templates.yaml."""
    templates: dict[str, WorkerTemplate] = field(default_factory=dict)


@dataclass
class OrgConfig:
    """Complete configuration for an organization.

    Created by loading from explicit config directory path.
    """
    providers: ProvidersConfig
    worker_templates: WorkerTemplatesConfig
    config_path: Path


def _expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports ${VAR} syntax.
    """
    if not isinstance(value, str) or "${" not in value:
        return value

    import re
    pattern = r'\$\{([^}]+)\}'

    def replace(match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return re.sub(pattern, replace, value)


def load_providers_config(config_path: Path) -> ProvidersConfig:
    """Load providers configuration from explicit path.

    Args:
        config_path: Path to providers.yaml file

    Returns:
        ProvidersConfig with loaded settings

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Providers config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError("Empty providers configuration")

    config = ProvidersConfig(
        default=data.get("default", "anthropic"),
    )

    # Load thresholds
    thresholds_data = data.get("thresholds", {})
    config.thresholds = ThresholdSettings(
        coding=thresholds_data.get("coding", 80),
        reasoning=thresholds_data.get("reasoning", 60),
        research=thresholds_data.get("research", 80),
    )

    # Load providers
    for name, provider_data in data.get("providers", {}).items():
        api_key = provider_data.get("api_key", "")
        base_url = provider_data.get("base_url")

        # Expand environment variables
        api_key = _expand_env_vars(api_key)
        if base_url:
            base_url = _expand_env_vars(base_url)

        config.providers[name] = ProviderSettings(
            enabled=provider_data.get("enabled", True),
            api_key=api_key,
            base_url=base_url if base_url else None,
            timeout=provider_data.get("timeout", 60),
            max_retries=provider_data.get("max_retries", 3),
        )

    return config


def load_worker_templates_config(config_path: Path) -> WorkerTemplatesConfig:
    """Load worker templates configuration from explicit path.

    Args:
        config_path: Path to worker-templates.yaml file

    Returns:
        WorkerTemplatesConfig with loaded templates

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Worker templates config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError("Empty worker templates configuration")

    config = WorkerTemplatesConfig()

    for name, template_data in data.get("templates", {}).items():
        config.templates[name] = WorkerTemplate(
            description=template_data.get("description", ""),
            skills=template_data.get("skills", {}),
            cost=template_data.get("cost", 50),
        )

    return config


def load_org_config(config_dir: Path) -> OrgConfig:
    """Load complete organization configuration from explicit directory.

    This is the main entry point for loading org configuration.
    Follows "No Config Discovery" - the path must be provided explicitly.

    Args:
        config_dir: Path to org's config/ directory

    Returns:
        OrgConfig with all loaded settings

    Raises:
        FileNotFoundError: If config directory or required files don't exist
        ValueError: If config is invalid
    """
    if not config_dir.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    if not config_dir.is_dir():
        raise ValueError(f"Config path is not a directory: {config_dir}")

    providers_path = config_dir / "providers.yaml"
    templates_path = config_dir / "worker-templates.yaml"

    providers = load_providers_config(providers_path)

    # Worker templates are optional
    try:
        templates = load_worker_templates_config(templates_path)
    except FileNotFoundError:
        templates = WorkerTemplatesConfig()

    return OrgConfig(
        providers=providers,
        worker_templates=templates,
        config_path=config_dir,
    )


def get_org_config_path(org_path: Path) -> Path:
    """Get the config directory path for an org folder.

    Args:
        org_path: Path to org folder

    Returns:
        Path to config directory
    """
    return org_path / "config"


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
        # Unknown provider, assume valid
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
        # ValueError: malformed URL, AttributeError: None passed
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

    # Skip validation for disabled providers
    if not settings.enabled:
        return errors

    # Check API key presence
    if require_api_key and not settings.api_key:
        errors.append(ConfigurationError(
            "API key is required but not set. "
            f"Set the environment variable or configure directly.",
            provider=provider_name,
            field="api_key",
        ))
    elif settings.api_key:
        # Check API key format if present
        if not validate_api_key_format(provider_name, settings.api_key):
            errors.append(ConfigurationError(
                f"API key does not match expected format for {provider_name}. "
                "Please verify your API key is correct.",
                provider=provider_name,
                field="api_key",
            ))

    # Check base_url if provided
    if settings.base_url and not validate_url(settings.base_url):
        errors.append(ConfigurationError(
            f"Invalid URL format: {settings.base_url}",
            provider=provider_name,
            field="base_url",
        ))

    # Check timeout is positive
    if settings.timeout <= 0:
        errors.append(ConfigurationError(
            f"Timeout must be positive, got {settings.timeout}",
            provider=provider_name,
            field="timeout",
        ))

    # Check max_retries is non-negative
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

    Raises:
        ConfigurationError: If validation fails and raise_on_error is True
    """
    errors: list[ConfigurationError] = []

    # Check if any providers are configured
    if not config.providers:
        errors.append(ConfigurationError(
            "No providers configured. At least one provider must be defined."
        ))
        return errors

    # Check default provider exists and is enabled
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

    # Validate each provider
    for name, settings in config.providers.items():
        provider_errors = validate_provider_settings(name, settings)
        errors.extend(provider_errors)

    # Check at least one enabled provider
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
        # Raise first error for clear message
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
    # If it contains env var syntax, it's not plaintext
    if ENV_VAR_PATTERN.search(value):
        return False
    # If it matches known API key patterns, it's plaintext
    for pattern in API_KEY_PATTERNS.values():
        if pattern.match(value):
            return True
    # If it looks like a key (starts with sk-, contains hyphens, long enough)
    # but doesn't match known patterns, still consider it potentially plaintext
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
