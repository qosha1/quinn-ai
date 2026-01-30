"""
Provider registry and selection logic.

DEPRECATED: This module is now a facade for backward compatibility.
Import from providers.registry instead.

Manages registered providers and handles worker-to-model selection
based on cost and skill requirements.

Key components:
- CostTier: Enum mapping cost scores to model quality tiers
- cost_to_tier(): Maps cost score (0-100) to tier name
- skills_to_capabilities(): Derives required capabilities from worker skills
- select_provider_for_worker(): Main selection algorithm
- ProviderRegistry: Registry for managing providers
"""

# Re-export everything from the refactored registry package
# This maintains backward compatibility for existing imports

from providers.registry import (
    # Base
    DEFAULT_THRESHOLDS,
    DEFAULT_CODING_THRESHOLD,
    DEFAULT_REASONING_THRESHOLD,
    DEFAULT_RESEARCH_THRESHOLD,
    SKILL_TO_CAPABILITY,
    ProviderSelectionError,
    ProviderSelection,
    cost_to_tier,
    skills_to_capabilities,
    # Registry
    ProviderRegistry,
    # Selection
    get_model_for_worker,
    select_provider_for_worker,
    # Config
    load_providers_from_config,
    create_registry_from_config,
    _expand_env_vars,
    # Budget
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
