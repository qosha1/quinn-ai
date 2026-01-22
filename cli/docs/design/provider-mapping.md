# Provider Mapping System Design

## Overview

The provider mapping system automatically selects the optimal AI provider and model for each worker based on two independent dimensions:

1. **Cost Score (0-100)** - Determines model quality tier
2. **Skill Scores (0-100 per skill)** - Determines required capabilities

This design ensures "No Provider Lock-in" by abstracting provider selection behind a registry pattern, and "No String Dispatch" by using polymorphic provider instances.

## Design Principles

From CLAUDE.md:
- **Skills & Cost Are Relative** - Workers have skills (0-100) and cost (0-100). System maps to providers automatically.
- **No Provider Lock-in** - Swap providers via config without code changes.
- **No String Dispatch** - Registry returns instances, not string-based conditionals.
- **No Magic Values** - All thresholds and tiers in config.
- **Config Injection** - All configuration passed explicitly at startup.

---

## 1. Cost to Model Tier Mapping

### Tier Definitions

Cost scores map to model tiers that represent quality/capability/price tradeoffs:

| Tier | Cost Range | Model Class | Use Cases |
|------|------------|-------------|-----------|
| Budget | 0-30 | Fast, cheap models | Simple tasks, high volume, cost-sensitive |
| Standard | 31-60 | Balanced models | General purpose, most tasks |
| Advanced | 61-80 | High capability | Complex reasoning, code generation |
| Premium | 81-100 | Best available | Strategic decisions, critical tasks |

### Model Mapping by Provider

```yaml
# Example tier mappings (configurable per org)
model_tiers:
  anthropic:
    budget:    # cost 0-30
      model: claude-3-haiku-20240307
      max_tokens: 4096
    standard:  # cost 31-60
      model: claude-3-5-sonnet-20241022
      max_tokens: 8192
    advanced:  # cost 61-80
      model: claude-3-5-sonnet-20241022
      max_tokens: 16384
    premium:   # cost 81-100
      model: claude-3-opus-20240229
      max_tokens: 32768

  openai:
    budget:
      model: gpt-4o-mini
      max_tokens: 4096
    standard:
      model: gpt-4o
      max_tokens: 8192
    advanced:
      model: gpt-4o
      max_tokens: 16384
    premium:
      model: gpt-5
      max_tokens: 32768
      temperature: 1.0  # gpt-5 requires temperature == 1.0
```

### Tier Selection Algorithm

```python
def cost_to_tier(cost: int) -> str:
    """Map cost score to tier name.

    Args:
        cost: Worker cost score (0-100)

    Returns:
        Tier name: 'budget', 'standard', 'advanced', or 'premium'
    """
    if cost <= 30:
        return "budget"
    elif cost <= 60:
        return "standard"
    elif cost <= 80:
        return "advanced"
    else:
        return "premium"
```

---

## 2. Skill to Capability Matrix

### Capability Requirements

Worker skills above threshold unlock capability requirements for model selection:

| Skill | Threshold | Capability | Description |
|-------|-----------|------------|-------------|
| coding | 80 | `coding` | Code generation, analysis, debugging |
| reasoning | 60 | `reasoning` | Complex problem solving, multi-step logic |
| research | 80 | `research` | Information synthesis, web search |
| management | 70 | `tool_use` | Delegation, coordination tools |
| strategy | 90 | `long_context` | Large context for strategic analysis |

### Capability Matrix by Model

```
                    | coding | reasoning | research | tool_use | long_context |
--------------------|--------|-----------|----------|----------|--------------|
claude-3-haiku      |   -    |     -     |    -     |    Y     |      -       |
claude-3.5-sonnet   |   Y    |     Y     |    Y     |    Y     |      -       |
claude-3-opus       |   Y    |     Y     |    Y     |    Y     |      Y       |
gpt-4o-mini         |   -    |     -     |    -     |    Y     |      -       |
gpt-4o              |   Y    |     Y     |    Y     |    Y     |      -       |
gpt-5               |   Y    |     Y     |    Y     |    Y     |      Y       |
```

### Skills to Capabilities Conversion

```python
def skills_to_capabilities(
    skills: dict[str, int],
    thresholds: dict[str, int]
) -> list[str]:
    """Convert worker skills to required capabilities.

    Args:
        skills: Worker skills dict {skill_name: score}
        thresholds: Configurable thresholds {skill_name: threshold}

    Returns:
        List of required capability names
    """
    capability_mapping = {
        "coding": "coding",
        "reasoning": "reasoning",
        "research": "research",
        "management": "tool_use",
        "strategy": "long_context",
    }

    required = []
    for skill_name, capability_name in capability_mapping.items():
        threshold = thresholds.get(skill_name, 100)  # Default: never required
        if skills.get(skill_name, 0) >= threshold:
            required.append(capability_name)

    return required
```

---

## 3. Provider Selection Algorithm

### Selection Flow

```
                    +------------------+
                    | Worker Profile   |
                    | - cost: 75       |
                    | - skills: {...}  |
                    +--------+---------+
                             |
                    +--------v---------+
                    | Derive Tier      |
                    | cost=75 -> adv.  |
                    +--------+---------+
                             |
                    +--------v---------+
                    | Derive Caps      |
                    | coding >= 80?    |
                    | reasoning >= 60? |
                    +--------+---------+
                             |
               +-------------+-------------+
               |                           |
      +--------v---------+        +--------v---------+
      | Preferred        |        | Fallback Chain   |
      | Provider?        |        | 1. default       |
      +--------+---------+        | 2. all others    |
               |                  +--------+---------+
               |                           |
      +--------v---------+        +--------v---------+
      | Can Satisfy?     |------->| Next Provider    |
      | tier + caps      |   No   +------------------+
      +--------+---------+
               | Yes
      +--------v---------+
      | Return (Provider,|
      |  ModelInfo)      |
      +------------------+
```

### Selection Algorithm Pseudocode

```python
def select_provider_for_worker(
    registry: ProviderRegistry,
    worker_cost: int,
    worker_skills: dict[str, int],
    preferred_provider: Optional[str] = None,
    org_authorized_providers: Optional[list[str]] = None,
) -> tuple[Provider, ModelInfo]:
    """Select optimal provider and model for a worker.

    Selection priority:
    1. Preferred provider (if specified and authorized)
    2. Default provider
    3. Other authorized providers in registration order

    Args:
        registry: Initialized ProviderRegistry
        worker_cost: Worker cost score (0-100)
        worker_skills: Worker skills dict
        preferred_provider: Optional provider preference
        org_authorized_providers: List of authorized provider names (None = all)

    Returns:
        Tuple of (Provider, ModelInfo)

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
    providers_to_try = []

    # Preferred provider first
    if preferred_provider and is_authorized(preferred_provider, org_authorized_providers):
        if registry.has(preferred_provider):
            providers_to_try.append(preferred_provider)

    # Default provider second
    default = registry.default_name
    if default and default not in providers_to_try:
        if is_authorized(default, org_authorized_providers):
            providers_to_try.append(default)

    # Remaining authorized providers
    for name in registry.list_providers():
        if name not in providers_to_try:
            if is_authorized(name, org_authorized_providers):
                providers_to_try.append(name)

    # Step 3: Try each provider
    errors = []
    for provider_name in providers_to_try:
        provider = registry.get(provider_name)
        try:
            model = provider.select_model_for_tier(tier, required_capabilities)
            return provider, model
        except ModelNotAvailableError as e:
            errors.append((provider_name, str(e)))
            continue

    # Step 4: All providers failed
    raise ProviderSelectionError(
        cost=worker_cost,
        capabilities=required_capabilities,
        attempted=providers_to_try,
        errors=errors,
    )


def is_authorized(provider_name: str, authorized: Optional[list[str]]) -> bool:
    """Check if provider is authorized for this org."""
    if authorized is None:
        return True  # No restrictions
    return provider_name in authorized
```

### Model Selection Within Provider

```python
class Provider(ABC):
    def select_model_for_tier(
        self,
        tier: str,
        required_capabilities: list[str],
    ) -> ModelInfo:
        """Select best model for tier and capabilities.

        Args:
            tier: 'budget', 'standard', 'advanced', or 'premium'
            required_capabilities: Required capability names

        Returns:
            ModelInfo for selected model

        Raises:
            ModelNotAvailableError: If no suitable model
        """
        # Get models for this tier
        tier_models = [m for m in self.models if m.tier == tier]

        if not tier_models:
            raise ModelNotAvailableError(
                f"No {tier} tier models available",
                provider=self.name,
            )

        # Filter by capabilities
        if required_capabilities:
            capable = [
                m for m in tier_models
                if m.capabilities.has_capabilities(required_capabilities)
            ]
            if capable:
                tier_models = capable
            else:
                # Try upgrading tier if capabilities not met
                upgraded = self._try_upgrade_tier(tier, required_capabilities)
                if upgraded:
                    return upgraded
                # Proceed with best available

        # Return first (implementations order by preference)
        return tier_models[0]

    def _try_upgrade_tier(
        self,
        current_tier: str,
        required_capabilities: list[str],
    ) -> Optional[ModelInfo]:
        """Try to find a higher tier model with required capabilities.

        This allows capability requirements to "pull up" the tier
        when necessary (e.g., coding requires sonnet even at budget tier).
        """
        tier_order = ["budget", "standard", "advanced", "premium"]
        current_idx = tier_order.index(current_tier)

        for higher_tier in tier_order[current_idx + 1:]:
            higher_models = [m for m in self.models if m.tier == higher_tier]
            capable = [
                m for m in higher_models
                if m.capabilities.has_capabilities(required_capabilities)
            ]
            if capable:
                return capable[0]

        return None
```

---

## 4. Fallback Chain

### Fallback Strategy

When a provider fails (unavailable, rate-limited, error), the system falls back through a chain:

```
Primary Provider (preferred or default)
    |
    v  [failure]
Next Authorized Provider
    |
    v  [failure]
... (continue through all authorized)
    |
    v  [all failed]
ProviderSelectionError with details
```

### Fallback Triggers

| Trigger | Action | Retry Primary? |
|---------|--------|----------------|
| `RateLimitError` | Try next provider | Yes (after cooldown) |
| `AuthenticationError` | Skip provider entirely | No (needs config fix) |
| `ModelNotAvailableError` | Try next provider | Yes |
| `TimeoutError` | Retry once, then next | Yes |
| Network error | Retry once, then next | Yes |

### Fallback Implementation

```python
class FallbackChain:
    """Manages provider fallback with health tracking."""

    def __init__(
        self,
        registry: ProviderRegistry,
        authorized_providers: list[str],
        cooldown_seconds: int = 60,
    ):
        self.registry = registry
        self.authorized = authorized_providers
        self.cooldown_seconds = cooldown_seconds
        self._health: dict[str, ProviderHealth] = {}

    def execute_with_fallback(
        self,
        operation: Callable[[Provider, ModelInfo], T],
        worker_cost: int,
        worker_skills: dict[str, int],
        preferred_provider: Optional[str] = None,
    ) -> T:
        """Execute operation with automatic fallback.

        Args:
            operation: Function taking (provider, model) and returning result
            worker_cost: Worker cost score
            worker_skills: Worker skills dict
            preferred_provider: Optional provider preference

        Returns:
            Result from operation

        Raises:
            AllProvidersFailedError: If all providers fail
        """
        tier = cost_to_tier(worker_cost)
        capabilities = skills_to_capabilities(worker_skills, self.registry.thresholds)

        providers = self._get_provider_order(preferred_provider)
        errors = []

        for provider_name in providers:
            if self._is_in_cooldown(provider_name):
                continue

            provider = self.registry.get(provider_name)

            try:
                model = provider.select_model_for_tier(tier, capabilities)
                result = operation(provider, model)
                self._mark_healthy(provider_name)
                return result

            except RateLimitError as e:
                self._mark_rate_limited(provider_name, e.retry_after)
                errors.append((provider_name, "rate_limited", str(e)))

            except AuthenticationError as e:
                self._mark_auth_failed(provider_name)
                errors.append((provider_name, "auth_failed", str(e)))

            except (TimeoutError, ConnectionError) as e:
                # Retry once
                try:
                    result = operation(provider, model)
                    self._mark_healthy(provider_name)
                    return result
                except Exception as retry_e:
                    errors.append((provider_name, "network_error", str(retry_e)))

            except ModelNotAvailableError as e:
                errors.append((provider_name, "model_unavailable", str(e)))

        raise AllProvidersFailedError(
            attempted=providers,
            errors=errors,
            tier=tier,
            capabilities=capabilities,
        )

    def _get_provider_order(self, preferred: Optional[str]) -> list[str]:
        """Get provider attempt order."""
        order = []

        if preferred and preferred in self.authorized:
            order.append(preferred)

        if self.registry.default_name:
            if self.registry.default_name not in order:
                if self.registry.default_name in self.authorized:
                    order.append(self.registry.default_name)

        for name in self.authorized:
            if name not in order and self.registry.has(name):
                order.append(name)

        return order

    def _is_in_cooldown(self, provider_name: str) -> bool:
        """Check if provider is in cooldown."""
        health = self._health.get(provider_name)
        if not health:
            return False
        return health.is_in_cooldown()

    def _mark_rate_limited(self, provider_name: str, retry_after: int) -> None:
        """Mark provider as rate limited."""
        self._health[provider_name] = ProviderHealth(
            status="rate_limited",
            cooldown_until=datetime.now() + timedelta(seconds=retry_after),
        )

    def _mark_healthy(self, provider_name: str) -> None:
        """Mark provider as healthy."""
        self._health[provider_name] = ProviderHealth(status="healthy")


@dataclass
class ProviderHealth:
    """Health status for a provider."""
    status: str  # 'healthy', 'rate_limited', 'auth_failed', 'unhealthy'
    cooldown_until: Optional[datetime] = None
    failure_count: int = 0

    def is_in_cooldown(self) -> bool:
        if self.cooldown_until is None:
            return False
        return datetime.now() < self.cooldown_until
```

---

## 5. Configuration Schema

### Complete providers.yaml Schema

```yaml
# Provider Configuration
# Environment variables: ${VAR_NAME} syntax

# Default provider (used when no preference specified)
default: anthropic

# Skill thresholds for capability requirements
thresholds:
  coding: 80      # Skill >= threshold triggers capability requirement
  reasoning: 60
  research: 80
  management: 70
  strategy: 90

# Cost tier boundaries
cost_tiers:
  budget: [0, 30]
  standard: [31, 60]
  advanced: [61, 80]
  premium: [81, 100]

# Provider definitions
providers:
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    base_url: null  # Use default
    timeout: 60
    max_retries: 3

    # Model definitions with tier and capability mapping
    models:
      - id: claude-3-haiku-20240307
        name: Claude 3 Haiku
        tier: budget
        max_tokens: 4096
        capabilities:
          tool_use: true

      - id: claude-3-5-sonnet-20241022
        name: Claude 3.5 Sonnet
        tier: standard  # Also serves advanced
        tiers: [standard, advanced]
        max_tokens: 8192
        capabilities:
          coding: true
          reasoning: true
          research: true
          tool_use: true

      - id: claude-3-opus-20240229
        name: Claude 3 Opus
        tier: premium
        max_tokens: 32768
        capabilities:
          coding: true
          reasoning: true
          research: true
          tool_use: true
          long_context: true

  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    timeout: 60
    max_retries: 3

    models:
      - id: gpt-4o-mini
        name: GPT-4o Mini
        tier: budget
        max_tokens: 4096
        capabilities:
          tool_use: true

      - id: gpt-4o
        name: GPT-4o
        tiers: [standard, advanced]
        max_tokens: 16384
        capabilities:
          coding: true
          reasoning: true
          research: true
          tool_use: true

      - id: gpt-5
        name: GPT-5
        tier: premium
        max_tokens: 32768
        temperature: 1.0  # gpt-5 requires temperature == 1.0
        capabilities:
          coding: true
          reasoning: true
          research: true
          tool_use: true
          long_context: true

# Fallback configuration
fallback:
  enabled: true
  cooldown_seconds: 60
  max_retries_per_provider: 2
```

### Organization-Level Authorization

Organizations can restrict which providers workers may use:

```yaml
# org-config.yaml (per organization)
name: Acme Corp
id: acme-001

# Provider authorization (subset of system providers)
authorized_providers:
  - anthropic
  - openai

# Provider preferences by worker role
provider_preferences:
  ceo: anthropic       # Executives use Anthropic
  director: anthropic
  engineer: openai     # Engineers use OpenAI
  researcher: anthropic

# Cost overrides (org can limit max cost)
cost_limits:
  max_cost: 80  # No premium tier
  role_limits:
    junior_engineer: 40  # Juniors limited to budget/standard
```

### Multi-Provider Setup Example

```yaml
# Advanced setup with multiple providers and routing rules
default: anthropic

providers:
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    # Full configuration...

  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    # Full configuration...

  azure_openai:
    enabled: true
    api_key: ${AZURE_OPENAI_API_KEY}
    base_url: ${AZURE_OPENAI_ENDPOINT}
    # Enterprise Azure deployment
    models:
      - id: gpt-4o-enterprise
        tiers: [standard, advanced, premium]
        # Enterprise models serve all higher tiers

# Routing rules (evaluated in order)
routing_rules:
  - name: compliance_workloads
    condition:
      worker_role: [compliance_officer, legal_analyst]
    provider: azure_openai
    reason: "Compliance workloads must use Azure for data residency"

  - name: research_tasks
    condition:
      skill_research: ">= 80"
    provider: anthropic
    reason: "Research tasks prefer Anthropic for quality"

  - name: high_volume_coding
    condition:
      skill_coding: ">= 70"
      cost: "<= 50"
    provider: openai
    reason: "High volume coding uses OpenAI for cost efficiency"
```

---

## 6. Data Structures

### Core Types

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class CostTier(str, Enum):
    """Model cost/quality tiers."""
    BUDGET = "budget"
    STANDARD = "standard"
    ADVANCED = "advanced"
    PREMIUM = "premium"

@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    id: str
    name: str
    tiers: list[CostTier]
    max_tokens: int
    capabilities: ModelCapabilities
    temperature: Optional[float] = None  # Override default

@dataclass
class ProviderSelection:
    """Result of provider selection."""
    provider: Provider
    model: ModelInfo
    tier: CostTier
    required_capabilities: list[str]

    # Selection metadata
    was_fallback: bool = False
    fallback_reason: Optional[str] = None
    original_provider: Optional[str] = None

@dataclass
class SelectionContext:
    """Context for provider selection."""
    worker_id: str
    worker_cost: int
    worker_skills: dict[str, int]
    worker_role: str
    org_id: str
    preferred_provider: Optional[str] = None

    # Derived (computed)
    tier: Optional[CostTier] = field(default=None, init=False)
    required_capabilities: list[str] = field(default_factory=list, init=False)

class ProviderSelectionError(Exception):
    """Raised when no provider can satisfy requirements."""
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

        error_summary = "; ".join(f"{p}: {e}" for p, e in errors)
        super().__init__(
            f"No provider satisfies cost={cost}, capabilities={capabilities}. "
            f"Tried: {attempted}. Errors: {error_summary}"
        )
```

---

## 7. Integration Points

### Worker Session Integration

```python
class WorkerSession:
    """Worker session with provider selection."""

    def __init__(
        self,
        worker: Worker,
        registry: ProviderRegistry,
        org_config: OrgConfig,
    ):
        self.worker = worker
        self.registry = registry
        self.org_config = org_config
        self._provider: Optional[Provider] = None
        self._model: Optional[ModelInfo] = None

    def initialize(self) -> ProviderSelection:
        """Initialize session with provider selection."""
        selection = select_provider_for_worker(
            registry=self.registry,
            worker_cost=self.worker.cost,
            worker_skills=self.worker.skills,
            preferred_provider=self.org_config.get_preference(self.worker.role),
            org_authorized_providers=self.org_config.authorized_providers,
        )

        self._provider = selection.provider
        self._model = selection.model

        return selection

    def complete(self, messages: list[Message]) -> CompletionResult:
        """Execute completion with automatic fallback."""
        chain = FallbackChain(
            self.registry,
            self.org_config.authorized_providers,
        )

        def do_complete(provider: Provider, model: ModelInfo) -> CompletionResult:
            return provider.complete(
                messages=messages,
                model=model.id,
                max_tokens=model.max_tokens,
                temperature=model.temperature or 0.7,
            )

        return chain.execute_with_fallback(
            do_complete,
            self.worker.cost,
            self.worker.skills,
            self.org_config.get_preference(self.worker.role),
        )
```

### CLI Integration

```bash
# View provider mapping for a worker
qn wrkr provider-info --worker-id w-001

# Output:
# Worker: w-001 (Senior Engineer)
# Cost: 70 -> Tier: advanced
# Skills: coding=95, reasoning=85, research=80
# Required Capabilities: coding, reasoning, research
# Selected: anthropic / claude-3-5-sonnet-20241022
# Fallback Chain: anthropic -> openai

# Test provider selection
qn org test-provider --cost 75 --skills "coding:90,reasoning:80"

# List authorized providers
qn org providers --org-id acme-001
```

---

## 8. Observability

### Metrics to Track

```python
@dataclass
class ProviderMetrics:
    """Metrics for provider selection and usage."""

    # Selection metrics
    selections_total: Counter  # by provider, tier
    selection_failures: Counter  # by provider, reason
    fallback_used: Counter  # by original_provider, fallback_provider

    # Performance metrics
    selection_latency: Histogram  # time to select provider
    completion_latency: Histogram  # by provider, model, tier

    # Cost metrics
    tokens_used: Counter  # by provider, model, direction (input/output)
    estimated_cost: Counter  # by provider, model

    # Health metrics
    provider_health: Gauge  # by provider (0=unhealthy, 1=healthy)
    cooldown_active: Gauge  # by provider
```

### Logging

```python
# Selection logging
logger.info(
    "provider_selected",
    worker_id=worker.id,
    cost=worker.cost,
    tier=tier,
    capabilities=capabilities,
    provider=selection.provider.name,
    model=selection.model.id,
    was_fallback=selection.was_fallback,
)

# Fallback logging
logger.warning(
    "provider_fallback",
    worker_id=worker.id,
    original_provider=original,
    fallback_provider=fallback,
    reason=reason,
)

# Error logging
logger.error(
    "provider_selection_failed",
    worker_id=worker.id,
    cost=cost,
    capabilities=capabilities,
    attempted=attempted,
    errors=errors,
)
```

---

## 9. Migration Path

### From Current Implementation

The current `provider.py` has basic selection logic. Migration steps:

1. **Add tier support to ModelInfo**
   - Add `tier` field to existing `ModelInfo` dataclass
   - Update existing model definitions with tier assignments

2. **Extend ProviderRegistry**
   - Add `select_for_tier()` method alongside existing `select_for_worker()`
   - Keep backward compatibility with existing API

3. **Add fallback chain**
   - Create `FallbackChain` class as wrapper around existing selection
   - Integrate health tracking

4. **Update config schema**
   - Extend `providers.yaml` with tier definitions
   - Add model capability specifications
   - Support both old and new config formats during transition

### Backward Compatibility

```python
# Support old cost_tier tuple format
@dataclass
class ModelInfo:
    # ... existing fields ...

    # New: explicit tier
    tier: Optional[CostTier] = None

    # Old: cost range (deprecated but supported)
    cost_tier: Optional[tuple[int, int]] = None

    def get_tier(self, cost: int) -> Optional[CostTier]:
        """Get tier, supporting both old and new format."""
        if self.tier:
            return self.tier
        if self.cost_tier:
            # Convert old format
            min_cost, max_cost = self.cost_tier
            if min_cost <= cost <= max_cost:
                return cost_to_tier(cost)
        return None
```

---

## Summary

This design provides:

1. **Clear cost-to-tier mapping** with four tiers (budget, standard, advanced, premium)
2. **Skill-to-capability conversion** with configurable thresholds
3. **Deterministic provider selection** with preference, default, and fallback ordering
4. **Robust fallback chain** with health tracking and cooldown
5. **Flexible configuration** supporting single and multi-provider setups
6. **No string dispatch** - all behavior through polymorphic provider instances
7. **No magic values** - all thresholds and mappings in config
