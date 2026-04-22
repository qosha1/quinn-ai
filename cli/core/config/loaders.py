"""
YAML loading functions for QuinnAI configuration.

All loaders take explicit paths — no config discovery, no env var magic for paths.
"""

import os
import re
from pathlib import Path

import yaml

from cli.core.constants import (
    COST_PER_1K_TOKENS_BUDGET,
    COST_PER_1K_TOKENS_STANDARD,
    COST_PER_1K_TOKENS_ADVANCED,
    COST_PER_1K_TOKENS_PREMIUM,
    DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
    DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
)
from .models import (
    ProvidersConfig,
    ProviderSettings,
    ThresholdSettings,
    WorkerTemplatesConfig,
    WorkerTemplate,
    BudgetConfig,
    TierTokenCosts,
    WorkflowConfig,
    OKRLinkingConfig,
    AutoAssignConfig,
    OrgConfig,
)


def _expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports ${VAR} syntax.
    """
    if not isinstance(value, str) or "${" not in value:
        return value

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

    thresholds_data = data.get("thresholds", {})
    config.thresholds = ThresholdSettings(
        coding=thresholds_data.get("coding", 80),
        reasoning=thresholds_data.get("reasoning", 60),
        research=thresholds_data.get("research", 80),
    )

    for name, provider_data in data.get("providers", {}).items():
        api_key = provider_data.get("api_key", "")
        base_url = provider_data.get("base_url")

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
        return BudgetConfig.default()

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data:
        return BudgetConfig.default()

    tier_costs: dict[str, TierTokenCosts] = {}
    tier_data = data.get("tier_costs", {})
    for tier_name, costs in tier_data.items():
        if isinstance(costs, dict) and "input" in costs and "output" in costs:
            tier_costs[tier_name.lower()] = TierTokenCosts(
                input=float(costs["input"]),
                output=float(costs["output"]),
            )

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

    okr_data = data.get("okr_linking", {})
    okr_linking = OKRLinkingConfig(
        require_okr_link=okr_data.get("require_okr_link", True),
        strict_mode=okr_data.get("strict_mode", False),
    )

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

    try:
        templates = load_worker_templates_config(templates_path)
    except FileNotFoundError:
        templates = WorkerTemplatesConfig()

    budget = load_budget_config(budget_path)
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
