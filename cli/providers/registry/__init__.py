"""
Provider registry package.

This package contains the provider selection and registry system,
refactored from the monolithic provider.py into focused modules:

- base.py: Base classes, exceptions, and helper functions
- registry.py: ProviderRegistry class for provider management
- selection.py: Provider and model selection algorithms
- config.py: Configuration loading from YAML
- budget.py: Budget enforcement and session creation

All public APIs are re-exported here for backward compatibility.
"""

# Base classes and exceptions
from providers.registry.base import (
    DEFAULT_THRESHOLDS,
    DEFAULT_CODING_THRESHOLD,
    DEFAULT_REASONING_THRESHOLD,
    DEFAULT_RESEARCH_THRESHOLD,
    SKILL_TO_CAPABILITY,
    ProviderSelectionError,
    ProviderSelection,
    cost_to_tier,
    skills_to_capabilities,
)

# Registry
from providers.registry.registry import ProviderRegistry

# Selection functions
from providers.registry.selection import (
    get_model_for_worker,
    select_provider_for_worker,
)

# Configuration
from providers.registry.config import (
    load_providers_from_config,
    create_registry_from_config,
    _expand_env_vars,
)

# Budget and session creation
from providers.registry.budget import (
    create_session_for_worker,
    complete_with_budget,
)

__all__ = [
    # Base
    "DEFAULT_THRESHOLDS",
    "DEFAULT_CODING_THRESHOLD",
    "DEFAULT_REASONING_THRESHOLD",
    "DEFAULT_RESEARCH_THRESHOLD",
    "SKILL_TO_CAPABILITY",
    "ProviderSelectionError",
    "ProviderSelection",
    "cost_to_tier",
    "skills_to_capabilities",
    # Registry
    "ProviderRegistry",
    # Selection
    "get_model_for_worker",
    "select_provider_for_worker",
    # Config
    "load_providers_from_config",
    "create_registry_from_config",
    "_expand_env_vars",
    # Budget
    "create_session_for_worker",
    "complete_with_budget",
]
