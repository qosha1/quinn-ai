"""
Provider and model selection logic.

This module handles the core logic of selecting the best provider
and model for a worker based on cost and capability requirements.
"""

from typing import Optional, TYPE_CHECKING

from cli.providers.base import (
    CostTier,
    ModelInfo,
    ModelNotAvailableError,
    Provider,
)

from cli.providers.registry.base import (
    cost_to_tier,
    skills_to_capabilities,
    ProviderSelection,
    ProviderSelectionError,
)

if TYPE_CHECKING:
    from cli.providers.registry.registry import ProviderRegistry


def get_model_for_worker(
    registry: "ProviderRegistry",
    worker_cost: int,
    required_capabilities: Optional[list[str]] = None,
    preferred_provider: Optional[str] = None,
    org_authorized_providers: Optional[list[str]] = None,
) -> ModelInfo:
    """Get best model for a worker based on cost and capabilities.

    Simplified interface that returns just the ModelInfo, abstracting
    away provider selection. Use select_provider_for_worker() if you
    need the full ProviderSelection with provider reference.

    Fallback Algorithm:
    1. Map worker_cost (0-100) to CostTier:
       - 0-30 → BUDGET (fast, cheap models)
       - 31-60 → STANDARD (balanced models)
       - 61-80 → ADVANCED (high capability)
       - 81-100 → PREMIUM (best available)

    2. Build provider attempt order:
       a. preferred_provider (if specified and authorized)
       b. registry.default_provider
       c. remaining authorized providers in registration order

    3. For each provider, try to find a model that:
       - Matches the tier (or can be upgraded if capabilities require)
       - Has all required_capabilities

    4. Return first matching model, or raise ProviderSelectionError

    Args:
        registry: Initialized ProviderRegistry with available providers
        worker_cost: Worker cost score (0-100)
        required_capabilities: Capability names required (e.g., ["coding"])
        preferred_provider: Try this provider first if authorized
        org_authorized_providers: Restrict to these providers (None = all)

    Returns:
        ModelInfo for the best matching model

    Raises:
        ProviderSelectionError: If no model satisfies requirements
    """
    capabilities = required_capabilities or []
    tier = cost_to_tier(worker_cost)

    # Build ordered list of providers to try
    providers_to_try = _build_provider_order(
        registry, preferred_provider, org_authorized_providers
    )

    # Try each provider until one succeeds
    errors: list[tuple[str, str]] = []
    for provider_name in providers_to_try:
        provider = registry.get(provider_name)
        try:
            return _select_model_for_tier(provider, tier, capabilities)
        except (ValueError, ModelNotAvailableError) as e:
            errors.append((provider_name, str(e)))

    raise ProviderSelectionError(
        cost=worker_cost,
        capabilities=capabilities,
        attempted=providers_to_try,
        errors=errors,
    )


def select_provider_for_worker(
    registry: "ProviderRegistry",
    worker_cost: int,
    worker_skills: dict[str, int],
    preferred_provider: Optional[str] = None,
    org_authorized_providers: Optional[list[str]] = None,
) -> ProviderSelection:
    """Select optimal provider and model for a worker.

    Selection priority:
    1. Preferred provider (if specified and authorized)
    2. Default provider
    3. Other authorized providers in registration order

    The algorithm:
    1. Derives tier from worker cost score
    2. Derives required capabilities from worker skills
    3. Tries providers in priority order
    4. For each provider, attempts to select a model matching tier + capabilities
    5. If capabilities cannot be met at current tier, tries upgrading

    Args:
        registry: Initialized ProviderRegistry
        worker_cost: Worker cost score (0-100)
        worker_skills: Worker skills dict
        preferred_provider: Optional provider preference
        org_authorized_providers: List of authorized provider names (None = all)

    Returns:
        ProviderSelection with provider, model, and metadata

    Raises:
        ProviderSelectionError: If no provider can satisfy requirements
    """
    # Step 1: Derive requirements from worker profile
    tier = cost_to_tier(worker_cost)
    required_capabilities = skills_to_capabilities(
        worker_skills,
        registry.thresholds
    )

    # Step 2: Build provider attempt order
    providers_to_try: list[str] = []

    # Preferred provider first
    if preferred_provider and _is_authorized(preferred_provider, org_authorized_providers):
        if registry.has(preferred_provider):
            providers_to_try.append(preferred_provider)

    # Default provider second
    default = registry.default_name
    if default and default not in providers_to_try:
        if _is_authorized(default, org_authorized_providers):
            providers_to_try.append(default)

    # Remaining authorized providers
    for name in registry.list_providers():
        if name not in providers_to_try:
            if _is_authorized(name, org_authorized_providers):
                providers_to_try.append(name)

    # Step 3: Try each provider
    errors: list[tuple[str, str]] = []
    for provider_name in providers_to_try:
        provider = registry.get(provider_name)
        try:
            model = _select_model_for_tier(provider, tier, required_capabilities)
            return ProviderSelection(
                provider=provider,
                model=model,
                tier=tier,
                required_capabilities=required_capabilities,
            )
        except (ValueError, ModelNotAvailableError) as e:
            errors.append((provider_name, str(e)))
            continue

    # Step 4: All providers failed
    raise ProviderSelectionError(
        cost=worker_cost,
        capabilities=required_capabilities,
        attempted=providers_to_try,
        errors=errors,
    )


def _build_provider_order(
    registry: "ProviderRegistry",
    preferred_provider: Optional[str],
    org_authorized_providers: Optional[list[str]],
) -> list[str]:
    """Build ordered list of providers to attempt.

    Order: preferred → default → remaining authorized.

    Args:
        registry: Provider registry
        preferred_provider: Optional preferred provider name
        org_authorized_providers: List of authorized providers (None = all)

    Returns:
        List of provider names in attempt order
    """
    providers: list[str] = []

    # Preferred provider first
    if preferred_provider and _is_authorized(preferred_provider, org_authorized_providers):
        if registry.has(preferred_provider):
            providers.append(preferred_provider)

    # Default provider second
    default = registry.default_name
    if default and default not in providers:
        if _is_authorized(default, org_authorized_providers):
            providers.append(default)

    # Remaining authorized providers
    for name in registry.list_providers():
        if name not in providers and _is_authorized(name, org_authorized_providers):
            providers.append(name)

    return providers


def _is_authorized(provider_name: str, authorized: Optional[list[str]]) -> bool:
    """Check if provider is authorized for this org.

    Args:
        provider_name: Name of provider to check
        authorized: List of authorized provider names (None = all authorized)

    Returns:
        True if provider is authorized
    """
    if authorized is None:
        return True  # No restrictions
    return provider_name in authorized


def _select_model_for_tier(
    provider: Provider,
    tier: CostTier,
    required_capabilities: list[str],
) -> ModelInfo:
    """Select best model for tier and capabilities from a provider.

    If no model at the requested tier satisfies capabilities,
    attempts to upgrade to a higher tier.

    Args:
        provider: Provider to select from
        tier: Target tier
        required_capabilities: Required capability names

    Returns:
        ModelInfo for selected model

    Raises:
        ValueError: If no suitable model available
    """
    # Get models for this tier
    tier_models = [m for m in provider.models if m.matches_tier(tier)]

    if not tier_models:
        # Try upgrading if no models at this tier
        upgraded = _try_upgrade_tier(provider, tier, required_capabilities)
        if upgraded:
            return upgraded
        raise ValueError(
            f"No {tier.value} tier models available from {provider.name}"
        )

    # Filter by capabilities if required
    if required_capabilities:
        capable = [
            m for m in tier_models
            if m.capabilities.has_capabilities(required_capabilities)
        ]
        if capable:
            return capable[0]
        else:
            # Try upgrading tier if capabilities not met
            upgraded = _try_upgrade_tier(provider, tier, required_capabilities)
            if upgraded:
                return upgraded
            # Proceed with best available at current tier
            return tier_models[0]

    return tier_models[0]


def _try_upgrade_tier(
    provider: Provider,
    current_tier: CostTier,
    required_capabilities: list[str],
) -> Optional[ModelInfo]:
    """Try to find a higher tier model with required capabilities.

    This allows capability requirements to "pull up" the tier
    when necessary (e.g., coding requires sonnet even at budget tier).

    Args:
        provider: Provider to search
        current_tier: Starting tier
        required_capabilities: Required capability names

    Returns:
        ModelInfo if found, None otherwise
    """
    tier_order = [CostTier.BUDGET, CostTier.STANDARD, CostTier.ADVANCED, CostTier.PREMIUM]
    current_idx = tier_order.index(current_tier)

    for higher_tier in tier_order[current_idx + 1:]:
        higher_models = [m for m in provider.models if m.matches_tier(higher_tier)]
        capable = [
            m for m in higher_models
            if m.capabilities.has_capabilities(required_capabilities)
        ]
        if capable:
            return capable[0]

    return None
