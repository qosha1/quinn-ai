"""
Configuration loading for QuinnAI CLI.

Follows "No Config Discovery" principle - all paths are passed explicitly.
No searching for config files, no environment variable magic for paths.

This package is split into three modules:
- models: dataclass definitions
- loaders: YAML I/O functions
- validators: validation and masking functions
"""

from .models import (
    PlaintextApiKeyWarning,
    ProviderSettings,
    ThresholdSettings,
    ProvidersConfig,
    WorkerTemplate,
    WorkerTemplatesConfig,
    TierTokenCosts,
    BudgetConfig,
    AutoAssignConfig,
    OKRLinkingConfig,
    WorkflowConfig,
    OrgConfig,
)

from .loaders import (
    _expand_env_vars,
    load_providers_config,
    load_worker_templates_config,
    load_budget_config,
    load_workflow_config,
    load_org_config,
    get_org_config_path,
)

from .validators import (
    API_KEY_PATTERNS,
    ENV_VAR_PATTERN,
    validate_api_key_format,
    validate_url,
    validate_provider_settings,
    validate_providers_config,
    validate_org_config,
    validate_and_raise,
    is_plaintext_api_key,
    check_plaintext_api_keys,
    warn_plaintext_api_keys,
    mask_secret,
    mask_provider_settings,
    mask_providers_config,
)

__all__ = [
    # models
    "PlaintextApiKeyWarning",
    "ProviderSettings",
    "ThresholdSettings",
    "ProvidersConfig",
    "WorkerTemplate",
    "WorkerTemplatesConfig",
    "TierTokenCosts",
    "BudgetConfig",
    "AutoAssignConfig",
    "OKRLinkingConfig",
    "WorkflowConfig",
    "OrgConfig",
    # loaders
    "_expand_env_vars",
    "load_providers_config",
    "load_worker_templates_config",
    "load_budget_config",
    "load_workflow_config",
    "load_org_config",
    "get_org_config_path",
    # validators
    "API_KEY_PATTERNS",
    "ENV_VAR_PATTERN",
    "validate_api_key_format",
    "validate_url",
    "validate_provider_settings",
    "validate_providers_config",
    "validate_org_config",
    "validate_and_raise",
    "is_plaintext_api_key",
    "check_plaintext_api_keys",
    "warn_plaintext_api_keys",
    "mask_secret",
    "mask_provider_settings",
    "mask_providers_config",
]
