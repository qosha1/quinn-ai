# Provider Interface Design

## Research Summary

### Patterns from QuinnAI Principles
- **No Provider Lock-in**: Our Interface → Provider Adapter → [OpenAI, Anthropic, etc.]
- **Interface-First**: Design for 10 providers even with 1
- **No String Dispatch**: Use polymorphism, not `if provider == "x"`
- **No Magic Values**: All values in config
- **Explicit Initialization**: No module side effects, config passed at startup

### Cost → Model Mapping
User specifies relative cost (0-100), system maps to concrete models:
- 0-30: cheap models (claude-haiku, gpt-4o-mini)
- 31-60: mid-tier (claude-sonnet, gpt-4o)
- 61-100: top-tier (claude-opus, best available)

### Skills → Capabilities
Workers have skills (0-100 scores). High skills unlock capabilities:
- `coding: 90+` → gets git, terminal, code-exec tools
- `research: 80+` → gets web search tools
- Skills: coding, reasoning, research, management, strategy, creative

## Design

### Base Provider Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class ModelCapabilities:
    """Capabilities available for a model."""
    coding: bool = False
    reasoning: bool = False
    research: bool = False
    tool_use: bool = False
    long_context: bool = False

@dataclass
class ModelInfo:
    """Information about a specific model."""
    id: str
    name: str
    cost_tier: tuple[int, int]  # (min_cost, max_cost)
    capabilities: ModelCapabilities
    max_tokens: int = 4096

@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    api_key: str
    base_url: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3

@dataclass
class Message:
    """A message in a conversation."""
    role: str  # "user", "assistant", "system"
    content: str

@dataclass
class CompletionResult:
    """Result from a completion call."""
    content: str
    model: str
    usage: dict[str, int]  # tokens consumed
    stop_reason: Optional[str] = None

class Provider(ABC):
    """Abstract base for AI providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'anthropic', 'openai')."""
        pass

    @property
    @abstractmethod
    def models(self) -> list[ModelInfo]:
        """Available models from this provider."""
        pass

    @abstractmethod
    def select_model(self, cost: int, required_capabilities: list[str]) -> ModelInfo:
        """Select best model for cost and capabilities.

        Args:
            cost: Worker cost score (0-100)
            required_capabilities: Required capability names

        Returns:
            Best matching ModelInfo

        Raises:
            ValueError: If no suitable model available
        """
        pass

    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResult:
        """Generate completion from messages.

        Args:
            messages: Conversation messages
            model: Specific model ID (optional, uses cost-selected if not provided)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            CompletionResult with generated content
        """
        pass

    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming responses."""
        pass
```

### Provider Registry

```python
class ProviderRegistry:
    """Registry for available providers."""

    def __init__(self):
        self._providers: dict[str, Provider] = {}
        self._default_provider: Optional[str] = None

    def register(self, provider: Provider) -> None:
        """Register a provider."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> Provider:
        """Get provider by name."""
        if name not in self._providers:
            raise ValueError(f"Provider not found: {name}")
        return self._providers[name]

    def set_default(self, name: str) -> None:
        """Set default provider."""
        if name not in self._providers:
            raise ValueError(f"Provider not found: {name}")
        self._default_provider = name

    @property
    def default(self) -> Provider:
        """Get default provider."""
        if self._default_provider is None:
            raise ValueError("No default provider set")
        return self._providers[self._default_provider]

    def select_for_worker(
        self,
        cost: int,
        skills: dict[str, int],
        preferred_provider: Optional[str] = None,
    ) -> tuple[Provider, ModelInfo]:
        """Select best provider and model for a worker.

        Args:
            cost: Worker cost score (0-100)
            skills: Worker skills dict
            preferred_provider: Optional preferred provider name

        Returns:
            Tuple of (Provider, ModelInfo)
        """
        # Determine required capabilities from skills
        required = []
        if skills.get("coding", 0) >= 80:
            required.append("coding")
        if skills.get("reasoning", 0) >= 60:
            required.append("reasoning")
        if skills.get("research", 0) >= 80:
            required.append("research")

        # Try preferred provider first
        if preferred_provider and preferred_provider in self._providers:
            provider = self._providers[preferred_provider]
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                pass  # Fall through to other providers

        # Try all providers
        for provider in self._providers.values():
            try:
                model = provider.select_model(cost, required)
                return provider, model
            except ValueError:
                continue

        raise ValueError(f"No provider can satisfy cost={cost}, capabilities={required}")

    def list_providers(self) -> list[str]:
        """List registered provider names."""
        return list(self._providers.keys())
```

### Config-Driven Initialization

```python
def load_providers_from_config(config_path: Path) -> ProviderRegistry:
    """Load providers from YAML configuration.

    Args:
        config_path: Path to providers.yaml

    Returns:
        Initialized ProviderRegistry
    """
    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f)

    registry = ProviderRegistry()

    for name, provider_config in config.get("providers", {}).items():
        if not provider_config.get("enabled", True):
            continue

        # Get provider class (implementation-specific)
        provider_class = get_provider_class(name)

        # Create config
        pconfig = ProviderConfig(
            api_key=provider_config["api_key"],
            base_url=provider_config.get("base_url"),
            timeout=provider_config.get("timeout", 30),
            max_retries=provider_config.get("max_retries", 3),
        )

        # Initialize and register
        provider = provider_class(pconfig)
        registry.register(provider)

    # Set default
    if "default" in config:
        registry.set_default(config["default"])

    return registry
```

### Example providers.yaml

```yaml
default: anthropic

providers:
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    models:
      - id: claude-3-haiku-20240307
        cost_tier: [0, 30]
      - id: claude-3-5-sonnet-20241022
        cost_tier: [31, 60]
      - id: claude-3-opus-20240229
        cost_tier: [61, 100]

  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    models:
      - id: gpt-4o-mini
        cost_tier: [0, 30]
      - id: gpt-4o
        cost_tier: [31, 60]
      - id: gpt-5
        cost_tier: [61, 100]
```

## Key Decisions

1. **Abstract Provider Base**: Pure interface, no implementation details
2. **Registry Pattern**: Explicit registration, no string dispatch
3. **Cost-Based Selection**: System maps worker cost to model tier
4. **Capability Matching**: Skills determine required model capabilities
5. **Config Injection**: All config passed explicitly, no discovery
6. **Fallback Chain**: If preferred unavailable, try others in registry

## Relationships

```
ProviderRegistry
    ├── register(Provider)
    └── select_for_worker(cost, skills) → (Provider, ModelInfo)

Provider (abstract)
    ├── name
    ├── models → list[ModelInfo]
    ├── select_model(cost, capabilities) → ModelInfo
    └── complete(messages) → CompletionResult

Worker (from queries.py)
    ├── cost (0-100)
    └── skills (JSON dict)
```

## Implementation Order

1. Create `providers/base.py` - Provider ABC, data classes
2. Create `core/provider.py` - ProviderRegistry
3. Create `providers/anthropic.py` - Claude implementation
4. Create `providers/openai.py` - OpenAI implementation
5. Create default `config/providers.yaml`
