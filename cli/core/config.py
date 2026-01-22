"""
Configuration loading for QuinnAI CLI.

Follows "No Config Discovery" principle - all paths are passed explicitly.
No searching for config files, no environment variable magic for paths.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ProviderSettings:
    """Settings for a single provider."""
    enabled: bool = True
    api_key: str = ""
    base_url: Optional[str] = None
    timeout: int = 60
    max_retries: int = 3


@dataclass
class ThresholdSettings:
    """Skill thresholds for capability requirements."""
    coding: int = 80
    reasoning: int = 60
    research: int = 80


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
    cost: int = 50


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
