"""
Provider registry and selection logic.

Manages registered providers and handles worker-to-model selection
based on cost and skill requirements.

Key components:
- CostTier: Enum mapping cost scores to model quality tiers
- cost_to_tier(): Maps cost score (0-100) to tier name
- skills_to_capabilities(): Derives required capabilities from worker skills
- select_provider_for_worker(): Main selection algorithm
- ProviderRegistry: Registry for managing providers
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from cli.core.session import SessionInterface

from cli.core.constants import (
    COST_TIER_BUDGET_MAX,
    COST_TIER_STANDARD_MAX,
    COST_TIER_ADVANCED_MAX,
)

from cli.providers.base import (
    CostTier,
    ModelInfo,
    ModelNotAvailableError,
    Provider,
    ProviderConfig,
    ProviderError,
    AuthenticationError,
    RateLimitError,
    ProviderConnectionError,
    ProviderTimeoutError,
)


# Import thresholds from constants
from cli.core.constants import DEFAULT_SKILL_THRESHOLDS

# Default thresholds - can be overridden via config
DEFAULT_THRESHOLDS: dict[str, int] = dict(DEFAULT_SKILL_THRESHOLDS)

# Skill to capability mapping
SKILL_TO_CAPABILITY: dict[str, str] = {
    "coding": "coding",
    "reasoning": "reasoning",
    "research": "research",
    "management": "tool_use",
    "strategy": "long_context",
}

# For backward compatibility
DEFAULT_CODING_THRESHOLD = DEFAULT_THRESHOLDS["coding"]
DEFAULT_REASONING_THRESHOLD = DEFAULT_THRESHOLDS["reasoning"]
DEFAULT_RESEARCH_THRESHOLD = DEFAULT_THRESHOLDS["research"]


class ProviderSelectionError(Exception):
    """Raised when no provider can satisfy requirements.

    Contains detailed information about the selection attempt
    to aid debugging and fallback handling.
    """

    def __init__(
        self,
        cost: int,
        capabilities: list[str],
        attempted: list[str],
        errors: list[tuple[str, str]],
    ):
        self.cost = cost
        self.capabilities = capabilities
        self.attempted = attempted
        self.errors = errors

        error_summary = "; ".join(f"{p}: {e}" for p, e in errors) if errors else "none"
        super().__init__(
            f"No provider satisfies cost={cost}, capabilities={capabilities}. "
            f"Tried: {attempted}. Errors: {error_summary}"
        )


@dataclass
class ProviderSelection:
    """Result of provider selection.

    Contains the selected provider and model along with
    metadata about the selection process.
    """

    provider: Provider
    """Selected provider instance."""

    model: ModelInfo
    """Selected model info."""

    tier: CostTier
    """Derived tier from cost score."""

    required_capabilities: list[str]
    """Capabilities derived from worker skills."""

    was_fallback: bool = False
    """True if primary provider failed and fallback was used."""

    fallback_reason: Optional[str] = None
    """Reason for fallback if was_fallback is True."""

    original_provider: Optional[str] = None
    """Original provider name if fallback occurred."""


def cost_to_tier(cost: int) -> CostTier:
    """Map cost score to tier name.

    Tier boundaries (from design):
    - Budget: 0-30
    - Standard: 31-60
    - Advanced: 61-80
    - Premium: 81-100

    Args:
        cost: Worker cost score (0-100)

    Returns:
        CostTier enum value
    """
    if cost <= COST_TIER_BUDGET_MAX:
        return CostTier.BUDGET
    elif cost <= COST_TIER_STANDARD_MAX:
        return CostTier.STANDARD
    elif cost <= COST_TIER_ADVANCED_MAX:
        return CostTier.ADVANCED
    else:
        return CostTier.PREMIUM


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


def skills_to_capabilities(
    skills: dict[str, int],
    thresholds: Optional[dict[str, int]] = None,
) -> list[str]:
    """Convert worker skills to required capabilities.

    Each skill above its threshold unlocks a capability requirement:
    - coding >= 80 -> coding capability
    - reasoning >= 60 -> reasoning capability
    - research >= 80 -> research capability
    - management >= 70 -> tool_use capability
    - strategy >= 90 -> long_context capability

    Args:
        skills: Worker skills dict {skill_name: score}
        thresholds: Optional custom thresholds {skill_name: threshold}

    Returns:
        List of required capability names
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    required = []
    for skill_name, capability_name in SKILL_TO_CAPABILITY.items():
        threshold = thresholds.get(skill_name, 100)  # Default: never required
        if skills.get(skill_name, 0) >= threshold:
            required.append(capability_name)

    return required


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


class ProviderRegistry:
    """Registry for available providers.

    Manages provider registration and provides worker-based selection
    of providers and models based on cost and skill requirements.

    No string dispatch - all behavior is polymorphic through Provider instances.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._providers: dict[str, Provider] = {}
        self._default_provider: Optional[str] = None
        # Configurable thresholds with defaults (copy to avoid mutation)
        self._thresholds: dict[str, int] = dict(DEFAULT_THRESHOLDS)
        # Authorized providers - empty list means all registered are authorized
        self._authorized_providers: list[str] = []

    @property
    def authorized_providers(self) -> list[str]:
        """Get authorized provider names.

        Returns:
            List of authorized provider names (empty = all authorized)
        """
        return self._authorized_providers

    def set_authorized_providers(self, providers: list[str]) -> None:
        """Set list of authorized providers.

        Args:
            providers: List of provider names (empty = all authorized)
        """
        self._authorized_providers = list(providers)

    def is_authorized(self, name: str) -> bool:
        """Check if a provider is authorized.

        Args:
            name: Provider name to check

        Returns:
            True if authorized (or no restrictions set)
        """
        if not self._authorized_providers:
            return True
        return name in self._authorized_providers

    @property
    def thresholds(self) -> dict[str, int]:
        """Get current skill thresholds.

        Returns:
            Dict mapping skill names to threshold values
        """
        return self._thresholds

    def set_thresholds(
        self,
        coding: Optional[int] = None,
        reasoning: Optional[int] = None,
        research: Optional[int] = None,
        management: Optional[int] = None,
        strategy: Optional[int] = None,
    ) -> None:
        """Set skill thresholds from config.

        Args:
            coding: Threshold for coding capability requirement
            reasoning: Threshold for reasoning capability requirement
            research: Threshold for research capability requirement
            management: Threshold for tool_use capability requirement
            strategy: Threshold for long_context capability requirement
        """
        if coding is not None:
            self._thresholds["coding"] = coding
        if reasoning is not None:
            self._thresholds["reasoning"] = reasoning
        if research is not None:
            self._thresholds["research"] = research
        if management is not None:
            self._thresholds["management"] = management
        if strategy is not None:
            self._thresholds["strategy"] = strategy

    def register(self, provider: Provider) -> None:
        """Register a provider.

        Args:
            provider: Provider instance to register
        """
        self._providers[provider.name] = provider

    def unregister(self, name: str) -> None:
        """Unregister a provider.

        Args:
            name: Provider name to unregister
        """
        if name in self._providers:
            del self._providers[name]
            if self._default_provider == name:
                self._default_provider = None

    def get(self, name: str) -> Provider:
        """Get provider by name.

        Args:
            name: Provider name

        Returns:
            Provider instance

        Raises:
            ValueError: If provider not found
        """
        if name not in self._providers:
            raise ValueError(f"Provider not found: {name}")
        return self._providers[name]

    def has(self, name: str) -> bool:
        """Check if provider is registered.

        Args:
            name: Provider name

        Returns:
            True if provider is registered
        """
        return name in self._providers

    def set_default(self, name: str) -> None:
        """Set default provider.

        Args:
            name: Provider name to set as default

        Raises:
            ValueError: If provider not found
        """
        if name not in self._providers:
            raise ValueError(f"Provider not found: {name}")
        self._default_provider = name

    @property
    def default(self) -> Provider:
        """Get default provider.

        Returns:
            Default provider instance

        Raises:
            ValueError: If no default set
        """
        if self._default_provider is None:
            raise ValueError("No default provider set")
        return self._providers[self._default_provider]

    @property
    def default_name(self) -> Optional[str]:
        """Get default provider name.

        Returns:
            Default provider name or None
        """
        return self._default_provider

    def select_for_worker(
        self,
        cost: int,
        skills: dict[str, int],
        preferred_provider: Optional[str] = None,
    ) -> tuple[Provider, ModelInfo]:
        """Select best provider and model for a worker.

        Derives required capabilities from worker skills and finds the
        best matching provider and model. Only considers authorized providers.

        Args:
            cost: Worker cost score (0-100)
            skills: Worker skills dict (skill_name -> score 0-100)
            preferred_provider: Optional preferred provider name

        Returns:
            Tuple of (Provider, ModelInfo)

        Raises:
            ValueError: If no provider can satisfy requirements
        """
        # Derive required capabilities from skills
        required = self._skills_to_capabilities(skills)

        # Try preferred provider first (if authorized)
        if (
            preferred_provider
            and preferred_provider in self._providers
            and self.is_authorized(preferred_provider)
        ):
            provider = self._providers[preferred_provider]
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                pass  # Fall through to other providers

        # Try default provider (if authorized)
        if (
            self._default_provider
            and self._default_provider != preferred_provider
            and self.is_authorized(self._default_provider)
        ):
            provider = self._providers[self._default_provider]
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                pass

        # Try all other authorized providers
        for name, provider in self._providers.items():
            if name == preferred_provider or name == self._default_provider:
                continue
            if not self.is_authorized(name):
                continue
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                continue

        raise ValueError(
            f"No provider can satisfy cost={cost}, capabilities={required}"
        )

    def _skills_to_capabilities(self, skills: dict[str, int]) -> list[str]:
        """Convert worker skills to required capabilities.

        Uses configurable thresholds set via set_thresholds().

        Args:
            skills: Worker skills dict

        Returns:
            List of required capability names
        """
        return skills_to_capabilities(skills, self._thresholds)

    def list_providers(self) -> list[str]:
        """List registered provider names.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    def get_model_for_tier(
        self,
        tier: CostTier,
        required_capabilities: Optional[list[str]] = None,
    ) -> tuple[Provider, ModelInfo]:
        """Get a model for a specific tier from any provider.

        Tries providers in order: default first, then others.
        Returns the first matching model at the requested tier.

        Args:
            tier: Target cost tier
            required_capabilities: Optional capability requirements

        Returns:
            Tuple of (Provider, ModelInfo)

        Raises:
            ValueError: If no model available for tier
        """
        fallback_chain = self._build_fallback_chain(tier, required_capabilities)
        if not fallback_chain:
            raise ValueError(f"No model available for tier {tier.value}")
        return fallback_chain[0]

    def _build_fallback_chain(
        self,
        tier: CostTier,
        required_capabilities: Optional[list[str]] = None,
    ) -> list[tuple[Provider, ModelInfo]]:
        """Build ordered list of provider/model pairs for fallback.

        Builds a list of (provider, model) tuples that can serve
        the requested tier. List is ordered by preference:
        1. Default provider first
        2. Other authorized providers in registration order

        Args:
            tier: Target cost tier
            required_capabilities: Optional capability requirements

        Returns:
            List of (Provider, ModelInfo) tuples in fallback order
        """
        if required_capabilities is None:
            required_capabilities = []

        fallback: list[tuple[Provider, ModelInfo]] = []

        # Build provider order: default first
        provider_order = []
        if self._default_provider and self.is_authorized(self._default_provider):
            provider_order.append(self._default_provider)
        for name in self._providers:
            if name not in provider_order and self.is_authorized(name):
                provider_order.append(name)

        # Try each provider
        for name in provider_order:
            provider = self._providers[name]
            try:
                model = _select_model_for_tier(provider, tier, required_capabilities)
                fallback.append((provider, model))
            except (ValueError, ModelNotAvailableError):
                continue

        return fallback

    def __len__(self) -> int:
        """Number of registered providers."""
        return len(self._providers)


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

    import re
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


def create_session_for_worker(
    registry: "ProviderRegistry",
    worker_id: str,
    worker_cost: int,
    worker_skills: dict[str, int],
    working_directory: Optional[Path] = None,
    preferred_provider: Optional[str] = None,
    org_authorized_providers: Optional[list[str]] = None,
) -> "SessionInterface":
    """Create an appropriate session for a worker based on their profile.

    Uses provider selection to determine the right provider and model,
    then uses the SessionRegistry to create the appropriate session type.

    Args:
        registry: Initialized ProviderRegistry
        worker_id: Worker ID for session binding
        worker_cost: Worker cost score (0-100)
        worker_skills: Worker skills dict
        working_directory: Working directory for session
        preferred_provider: Optional provider preference
        org_authorized_providers: List of authorized provider names (None = all)

    Returns:
        Configured SessionInterface instance (not yet started)

    Raises:
        ProviderSelectionError: If no provider can satisfy requirements
        AdapterNotFoundError: If no session adapter for the provider
    """
    # Import here to avoid circular imports
    from cli.core.session import SessionConfig
    from cli.core.sessions.registry import get_default_registry

    # Select provider
    selection = select_provider_for_worker(
        registry=registry,
        worker_cost=worker_cost,
        worker_skills=worker_skills,
        preferred_provider=preferred_provider,
        org_authorized_providers=org_authorized_providers,
    )

    # Get CLI command from provider (no string dispatch)
    command = selection.provider.cli_command

    # Build session config
    config = SessionConfig(
        worker_id=worker_id,
        provider=selection.provider.name,
        command=command,
        args=["--dangerously-skip-permissions"],
        working_directory=working_directory,
        env_vars={
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        },
    )

    # Use SessionRegistry to create appropriate session type (no hardcoding)
    session_registry = get_default_registry()
    return session_registry.create(selection.provider.name, config)


def complete_with_budget(
    registry: "ProviderRegistry",
    db: "Database",
    worker_id: str,
    worker_cost: int,
    worker_skills: dict[str, int],
    messages: list[dict],
    max_tokens: int = 4096,
    preferred_provider: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
) -> dict:
    """Execute a completion request with budget enforcement.

    This is the main entry point for budget-controlled LLM calls.
    It:
    1. Selects the appropriate provider/model for the worker
    2. Estimates the cost and checks budget
    3. Makes the API call
    4. Records actual spend

    Args:
        registry: Initialized ProviderRegistry
        db: Database instance for budget operations
        worker_id: Worker making the request
        worker_cost: Worker cost score (0-100)
        worker_skills: Worker skills dict
        messages: List of message dicts for the completion
        max_tokens: Maximum output tokens
        preferred_provider: Optional provider preference
        reference_type: Optional reference type for transaction (e.g., 'task', 'message')
        reference_id: Optional reference ID for transaction

    Returns:
        Dict with completion result including:
        - content: The completion text
        - model: Model used
        - input_tokens: Actual input tokens
        - output_tokens: Actual output tokens
        - cost: Actual cost in credits
        - budget_remaining: Remaining budget after this call

    Raises:
        BudgetExhaustedError: If insufficient budget
        NoBudgetAllocationError: If no budget allocation exists
        ProviderSelectionError: If no provider can satisfy requirements
        AuthenticationError: If provider authentication fails
        RateLimitError: If provider rate limit is exceeded
        ProviderTimeoutError: If provider request times out
        ProviderConnectionError: If connection to provider fails
        ProviderError: For other provider errors (wraps unexpected exceptions)
    """
    # Import here to avoid circular imports
    from cli.core.budget import (
        BudgetEnforcer,
        estimate_cost,
        get_remaining_budget,
    )
    from cli.core.db import Database

    # Step 1: Select provider and model
    selection = select_provider_for_worker(
        registry=registry,
        worker_cost=worker_cost,
        worker_skills=worker_skills,
        preferred_provider=preferred_provider,
    )

    # Step 2: Estimate input tokens (rough approximation)
    # Count characters and estimate ~4 chars per token
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    estimated_input_tokens = total_chars // 4

    # Step 3: Estimate cost
    model_tier = selection.tier.value  # budget, standard, advanced, premium
    estimated_cost = estimate_cost(
        model_tier=model_tier,
        input_tokens=estimated_input_tokens,
        output_tokens=max_tokens,
    )

    # Step 4: Enforce budget and make completion
    with BudgetEnforcer(db, worker_id, estimated_cost) as enforcer:
        # Make the actual provider call with proper exception handling
        try:
            result = selection.provider.complete(
                messages=messages,
                model=selection.model.id,
                max_tokens=max_tokens,
            )
        except AuthenticationError:
            # Re-raise auth errors as-is - caller should handle credential issues
            raise
        except RateLimitError:
            # Re-raise rate limit errors - caller can implement retry logic
            raise
        except ProviderTimeoutError:
            # Re-raise timeout errors - caller can retry with longer timeout
            raise
        except ProviderConnectionError:
            # Re-raise connection errors - caller can retry after delay
            raise
        except ProviderError:
            # Re-raise other provider errors (APIError, ModelNotAvailableError, etc.)
            raise
        except Exception as e:
            # Wrap unexpected exceptions in ProviderError for consistent handling
            # This prevents raw exceptions from leaking through and ensures
            # the caller always gets a domain-specific exception
            raise ProviderError(
                message=f"Unexpected error during completion: {e}",
                provider=selection.provider.name,
                cause=e,
            ) from e

        # Get actual token counts from result
        actual_input = result.get("usage", {}).get("input_tokens", estimated_input_tokens)
        actual_output = result.get("usage", {}).get("output_tokens", 0)

        # Calculate actual cost
        actual_cost = estimate_cost(
            model_tier=model_tier,
            input_tokens=actual_input,
            output_tokens=actual_output,
        )

        # Record the spend
        enforcer.record(
            actual_cost=actual_cost,
            provider=selection.provider.name,
            model=selection.model.id,
            input_tokens=actual_input,
            output_tokens=actual_output,
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Completion via {selection.provider.name}/{selection.model.id}",
        )

    # Return enhanced result
    return {
        "content": result.get("content", ""),
        "model": selection.model.id,
        "provider": selection.provider.name,
        "input_tokens": actual_input,
        "output_tokens": actual_output,
        "cost": actual_cost,
        "budget_remaining": get_remaining_budget(db, worker_id),
    }


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
