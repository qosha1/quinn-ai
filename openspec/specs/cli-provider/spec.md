# CLI Provider Interface Specification

## Overview

The provider interface abstracts AI model providers (Anthropic, OpenAI, etc.) behind a unified contract. This enables provider-agnostic worker operation with cost-based model selection.

## Requirements

### Requirement: Provider Abstract Interface
The system SHALL define an abstract Provider base class that all provider implementations MUST inherit from.

#### Scenario: Provider interface contract
- **WHEN** a provider implementation is created
- **THEN** it MUST implement all abstract methods defined in the Provider base class

#### Scenario: Provider name property
- **WHEN** a provider is registered
- **THEN** it SHALL expose a `name` property returning its identifier (e.g., "anthropic", "openai")

#### Scenario: Provider models listing
- **WHEN** a provider is queried for available models
- **THEN** it SHALL return a list of ModelInfo objects describing each available model

### Requirement: Model Information
The system SHALL represent model information through a ModelInfo data class.

#### Scenario: ModelInfo structure
- **WHEN** a ModelInfo is created
- **THEN** it SHALL contain:
  - `id` (str): Model identifier for API calls
  - `name` (str): Human-readable model name
  - `cost_tier` (tuple[int, int]): Min and max cost scores (0-100)
  - `capabilities` (ModelCapabilities): What the model can do
  - `max_tokens` (int): Maximum context/output tokens

#### Scenario: Cost tier mapping
- **WHEN** a model's cost_tier is (0, 30)
- **THEN** workers with cost 0-30 MAY use this model
- **WHEN** a model's cost_tier is (31, 60)
- **THEN** workers with cost 31-60 MAY use this model
- **WHEN** a model's cost_tier is (61, 100)
- **THEN** workers with cost 61-100 MAY use this model

### Requirement: Model Capabilities
The system SHALL represent model capabilities through a ModelCapabilities data class.

#### Scenario: Capability flags
- **WHEN** a ModelCapabilities is created
- **THEN** it SHALL support boolean flags for:
  - `coding`: Code generation and analysis
  - `reasoning`: Complex reasoning tasks
  - `research`: Information retrieval and synthesis
  - `tool_use`: Function/tool calling
  - `long_context`: Extended context window

### Requirement: Cost-Based Model Selection
Providers SHALL implement cost-based model selection.

#### Scenario: Model selection by cost
- **WHEN** `select_model(cost=25, required_capabilities=[])` is called
- **THEN** a model with cost_tier containing 25 SHALL be returned

#### Scenario: Model selection with capabilities
- **WHEN** `select_model(cost=50, required_capabilities=["coding"])` is called
- **THEN** a model with cost_tier containing 50 AND coding=True SHALL be returned

#### Scenario: No suitable model available
- **WHEN** no model matches the cost and capability requirements
- **THEN** ValueError SHALL be raised with descriptive message

### Requirement: Message Completion
Providers SHALL implement message completion functionality.

#### Scenario: Completion request structure
- **WHEN** `complete()` is called
- **THEN** it SHALL accept:
  - `messages`: List of Message objects (role, content)
  - `model`: Optional specific model ID
  - `max_tokens`: Maximum tokens to generate
  - `temperature`: Sampling temperature

#### Scenario: Completion response structure
- **WHEN** a completion succeeds
- **THEN** it SHALL return a CompletionResult containing:
  - `content`: Generated text
  - `model`: Model ID used
  - `usage`: Token usage dict
  - `stop_reason`: Why generation stopped

### Requirement: Provider Registry
The system SHALL provide a ProviderRegistry for managing multiple providers.

#### Scenario: Provider registration
- **WHEN** a provider is registered via `register(provider)`
- **THEN** it SHALL be retrievable by name via `get(name)`

#### Scenario: Default provider
- **WHEN** `set_default(name)` is called
- **THEN** `default` property SHALL return that provider
- **WHEN** no default is set and `default` is accessed
- **THEN** ValueError SHALL be raised

#### Scenario: Provider listing
- **WHEN** `list_providers()` is called
- **THEN** all registered provider names SHALL be returned

### Requirement: Worker-Based Selection
The registry SHALL support worker-based provider and model selection.

#### Scenario: Selection from worker attributes
- **WHEN** `select_for_worker(cost, skills)` is called
- **THEN** it SHALL:
  1. Derive required capabilities from skills (skill >= 80 → capability required)
  2. Try preferred provider if specified
  3. Fall back to other providers if needed
  4. Return tuple of (Provider, ModelInfo)

#### Scenario: Skills to capabilities mapping
- **WHEN** skills contain `coding >= 80`
- **THEN** "coding" capability SHALL be required
- **WHEN** skills contain `reasoning >= 60`
- **THEN** "reasoning" capability SHALL be required
- **WHEN** skills contain `research >= 80`
- **THEN** "research" capability SHALL be required

#### Scenario: No satisfying provider
- **WHEN** no provider can satisfy cost and capability requirements
- **THEN** ValueError SHALL be raised

### Requirement: Configuration-Driven Initialization
The system SHALL support loading providers from YAML configuration.

#### Scenario: Config file structure
- **WHEN** providers.yaml is loaded
- **THEN** it SHALL support:
  - `default`: Default provider name
  - `providers`: Dict of provider configurations
  - Each provider: `enabled`, `api_key`, `base_url`, `timeout`, `max_retries`

#### Scenario: Disabled providers
- **WHEN** a provider has `enabled: false`
- **THEN** it SHALL NOT be registered

#### Scenario: Environment variable expansion
- **WHEN** config contains `${ENV_VAR}`
- **THEN** it SHALL be expanded from environment

### Requirement: No String Dispatch
Provider implementations SHALL NOT use string-based dispatch.

#### Scenario: Polymorphic behavior
- **WHEN** provider-specific behavior is needed
- **THEN** it SHALL be achieved through inheritance/polymorphism
- **THEN** it SHALL NOT use patterns like `if provider == "openai"`

### Requirement: Explicit Initialization
Providers SHALL NOT have module-level side effects.

#### Scenario: Import safety
- **WHEN** a provider module is imported
- **THEN** no network calls, file I/O, or state mutations SHALL occur

#### Scenario: Explicit configuration
- **WHEN** a provider is instantiated
- **THEN** all configuration SHALL be passed explicitly via constructor

### Requirement: Provider Configuration
Each provider SHALL accept configuration through a ProviderConfig data class.

#### Scenario: ProviderConfig structure
- **WHEN** a ProviderConfig is created
- **THEN** it SHALL contain:
  - `api_key` (str): API key for authentication
  - `base_url` (Optional[str]): Custom API endpoint
  - `timeout` (int): Request timeout in seconds
  - `max_retries` (int): Maximum retry attempts

### Requirement: Streaming Support Detection
Providers SHALL indicate streaming support.

#### Scenario: Streaming capability
- **WHEN** `supports_streaming()` is called
- **THEN** it SHALL return True if streaming is supported, False otherwise
