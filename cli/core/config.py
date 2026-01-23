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
    # Budget constants
    COST_PER_1K_TOKENS_BUDGET,
    COST_PER_1K_TOKENS_STANDARD,
    COST_PER_1K_TOKENS_ADVANCED,
    COST_PER_1K_TOKENS_PREMIUM,
    DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
    DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
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
    authorized_providers: list[str] = field(default_factory=list)
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

    def get_template(self, role: str) -> Optional["WorkerTemplate"]:
        """Get template for a role.

        Performs case-insensitive matching and normalizes role names
        (e.g., 'CEO' -> 'ceo', 'Senior Engineer' -> 'senior_engineer').

        Args:
            role: Role name to look up

        Returns:
            WorkerTemplate if found, None otherwise
        """
        # Normalize role name: lowercase, replace spaces with underscores
        normalized = role.lower().replace(" ", "_").replace("-", "_")
        return self.templates.get(normalized)

    def get_skills_and_cost(
        self,
        role: str,
        skill_overrides: Optional[dict[str, int]] = None,
        cost_override: Optional[int] = None,
    ) -> tuple[dict[str, int], int]:
        """Get skills and cost for a role from template with optional overrides.

        Args:
            role: Role name to look up
            skill_overrides: Optional skill values to override template
            cost_override: Optional cost to override template

        Returns:
            Tuple of (skills dict, cost int)

        Raises:
            KeyError: If role template not found
        """
        template = self.get_template(role)
        if template is None:
            raise KeyError(f"No template found for role: {role}")

        # Start with template values
        skills = dict(template.skills)
        cost = template.cost

        # Apply overrides
        if skill_overrides:
            skills.update(skill_overrides)
        if cost_override is not None:
            cost = cost_override

        return skills, cost


@dataclass
class TierTokenCosts:
    """Token costs for a single tier (per 1K tokens in USD)."""

    input: float
    output: float

    def to_dict(self) -> dict[str, float]:
        """Convert to dict format for budget calculations."""
        return {"input": self.input, "output": self.output}


@dataclass
class BudgetConfig:
    """Configuration for budget and cost estimation.

    All values are injectable via config. Falls back to constants when not set.
    """

    # Token costs per tier (cost per 1K tokens in USD)
    tier_costs: dict[str, TierTokenCosts] = field(default_factory=dict)

    # Session spawn estimates (initial context setup)
    session_spawn_tokens_input: int = DEFAULT_SESSION_SPAWN_TOKENS_INPUT
    session_spawn_tokens_output: int = DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT

    def get_tier_costs(self, tier: str) -> dict[str, float]:
        """Get token costs for a tier, falling back to defaults.

        Args:
            tier: Cost tier name ('budget', 'standard', 'advanced', 'premium')

        Returns:
            Dict with 'input' and 'output' costs per 1K tokens
        """
        tier_lower = tier.lower()
        if tier_lower in self.tier_costs:
            return self.tier_costs[tier_lower].to_dict()

        # Fall back to constants
        defaults = {
            "budget": COST_PER_1K_TOKENS_BUDGET,
            "standard": COST_PER_1K_TOKENS_STANDARD,
            "advanced": COST_PER_1K_TOKENS_ADVANCED,
            "premium": COST_PER_1K_TOKENS_PREMIUM,
        }
        return defaults.get(tier_lower, defaults["standard"])

    @classmethod
    def default(cls) -> "BudgetConfig":
        """Create BudgetConfig with all default values from constants."""
        return cls(
            tier_costs={
                "budget": TierTokenCosts(**COST_PER_1K_TOKENS_BUDGET),
                "standard": TierTokenCosts(**COST_PER_1K_TOKENS_STANDARD),
                "advanced": TierTokenCosts(**COST_PER_1K_TOKENS_ADVANCED),
                "premium": TierTokenCosts(**COST_PER_1K_TOKENS_PREMIUM),
            },
            session_spawn_tokens_input=DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
            session_spawn_tokens_output=DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
        )


@dataclass
class AutoAssignConfig:
    """Configuration for automatic work assignment."""
    enabled: bool = True
    match_skills: bool = True
    prefer_least_loaded: bool = True
    strategy: str = "least_loaded"  # least_loaded | round_robin | skill_match


@dataclass
class OKRLinkingConfig:
    """Configuration for OKR linking requirements."""
    require_okr_link: bool = True
    strict_mode: bool = False


@dataclass
class WorkflowConfig:
    """Configuration for work lifecycle and automation.

    Loaded from workflow.yaml. Defines valid states, transitions,
    and automation rules for work items.
    """
    # Work states and transitions
    work_states: list[str] = field(default_factory=lambda: [
        "draft", "open", "in_progress", "review", "blocked", "closed"
    ])
    transitions: dict[str, list[str]] = field(default_factory=dict)
    terminal_states: list[str] = field(default_factory=lambda: ["closed"])

    # OKR linking
    okr_linking: OKRLinkingConfig = field(default_factory=OKRLinkingConfig)

    # Automation
    auto_assign: AutoAssignConfig = field(default_factory=AutoAssignConfig)

    def is_valid_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a state transition is valid.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if transition is allowed
        """
        allowed = self.transitions.get(from_state, [])
        return to_state in allowed

    def is_terminal(self, state: str) -> bool:
        """Check if a state is terminal (no further transitions)."""
        return state in self.terminal_states

    @classmethod
    def default(cls) -> "WorkflowConfig":
        """Create default workflow config."""
        return cls(
            transitions={
                "draft": ["open", "closed"],
                "open": ["in_progress", "blocked", "closed"],
                "in_progress": ["review", "blocked", "closed"],
                "review": ["in_progress", "closed"],
                "blocked": ["open", "in_progress", "closed"],
                "closed": [],
            }
        )


@dataclass
class OrgConfig:
    """Complete configuration for an organization.

    Created by loading from explicit config directory path.
    """

    providers: ProvidersConfig
    worker_templates: WorkerTemplatesConfig
    budget: BudgetConfig
    workflow: WorkflowConfig
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
        authorized_providers=data.get("authorized_providers", []),
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


def load_budget_config(config_path: Path) -> BudgetConfig:
    """Load budget configuration from explicit path.

    Args:
        config_path: Path to budget.yaml file

    Returns:
        BudgetConfig with loaded settings (or defaults if file missing)
    """
    if not config_path.exists():
        # Budget config is optional - return defaults
        return BudgetConfig.default()

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        return BudgetConfig.default()

    # Parse tier costs
    tier_costs: dict[str, TierTokenCosts] = {}
    tier_data = data.get("tier_costs", {})
    for tier_name, costs in tier_data.items():
        if isinstance(costs, dict) and "input" in costs and "output" in costs:
            tier_costs[tier_name.lower()] = TierTokenCosts(
                input=float(costs["input"]),
                output=float(costs["output"]),
            )

    # Use defaults for missing tiers
    if not tier_costs:
        tier_costs = {
            "budget": TierTokenCosts(**COST_PER_1K_TOKENS_BUDGET),
            "standard": TierTokenCosts(**COST_PER_1K_TOKENS_STANDARD),
            "advanced": TierTokenCosts(**COST_PER_1K_TOKENS_ADVANCED),
            "premium": TierTokenCosts(**COST_PER_1K_TOKENS_PREMIUM),
        }

    return BudgetConfig(
        tier_costs=tier_costs,
        session_spawn_tokens_input=data.get(
            "session_spawn_tokens_input", DEFAULT_SESSION_SPAWN_TOKENS_INPUT
        ),
        session_spawn_tokens_output=data.get(
            "session_spawn_tokens_output", DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT
        ),
    )


def load_workflow_config(config_path: Path) -> WorkflowConfig:
    """Load workflow configuration from explicit path.

    Args:
        config_path: Path to workflow.yaml file

    Returns:
        WorkflowConfig with loaded settings, or defaults if file doesn't exist
    """
    if not config_path.exists():
        return WorkflowConfig.default()

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        return WorkflowConfig.default()

    # Parse OKR linking config
    okr_data = data.get("okr_linking", {})
    okr_linking = OKRLinkingConfig(
        require_okr_link=okr_data.get("require_okr_link", True),
        strict_mode=okr_data.get("strict_mode", False),
    )

    # Parse auto-assign config
    auto_data = data.get("automation", {}).get("auto_assign", {})
    auto_assign = AutoAssignConfig(
        enabled=auto_data.get("enabled", True),
        match_skills=auto_data.get("match_skills", True),
        prefer_least_loaded=auto_data.get("prefer_least_loaded", True),
        strategy=auto_data.get("strategy", "least_loaded"),
    )

    return WorkflowConfig(
        work_states=data.get("work_states", WorkflowConfig.default().work_states),
        transitions=data.get("transitions", WorkflowConfig.default().transitions),
        terminal_states=data.get("terminal_states", ["closed"]),
        okr_linking=okr_linking,
        auto_assign=auto_assign,
    )


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
    budget_path = config_dir / "budget.yaml"
    workflow_path = config_dir / "workflow.yaml"

    providers = load_providers_config(providers_path)

    # Worker templates are optional
    try:
        templates = load_worker_templates_config(templates_path)
    except FileNotFoundError:
        templates = WorkerTemplatesConfig()

    # Budget config is optional (defaults to constants)
    budget = load_budget_config(budget_path)

    # Workflow config is optional (defaults to standard work lifecycle)
    workflow = load_workflow_config(workflow_path)

    return OrgConfig(
        providers=providers,
        worker_templates=templates,
        budget=budget,
        workflow=workflow,
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
