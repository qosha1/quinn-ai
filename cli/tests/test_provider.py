"""
Unit tests for provider interface.
"""

import tempfile
from pathlib import Path
from typing import Optional

import pytest

from providers.base import (
    CompletionResult,
    Message,
    ModelCapabilities,
    ModelInfo,
    Provider,
    ProviderConfig,
    ProviderError,
)
from core.provider import (
    ProviderRegistry,
    load_providers_from_config,
    _expand_env_vars,
)


class MockProvider(Provider):
    """Mock provider for testing."""

    def __init__(self, config: ProviderConfig, provider_name: str = "mock"):
        super().__init__(config)
        self._name = provider_name
        self._models = [
            ModelInfo(
                id="mock-cheap",
                name="Mock Cheap",
                cost_tier=(0, 30),
                capabilities=ModelCapabilities(reasoning=True),
            ),
            ModelInfo(
                id="mock-mid",
                name="Mock Mid",
                cost_tier=(31, 60),
                capabilities=ModelCapabilities(coding=True, reasoning=True),
            ),
            ModelInfo(
                id="mock-premium",
                name="Mock Premium",
                cost_tier=(61, 100),
                capabilities=ModelCapabilities(
                    coding=True, reasoning=True, research=True, tool_use=True
                ),
            ),
        ]

    @property
    def name(self) -> str:
        return self._name

    @property
    def models(self) -> list[ModelInfo]:
        return self._models

    def complete(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResult:
        return CompletionResult(
            content="Mock response",
            model=model or "mock-mid",
            usage={"input_tokens": 10, "output_tokens": 5},
            stop_reason="end_turn",
        )

    def supports_streaming(self) -> bool:
        return False


class TestModelCapabilities:
    """Test ModelCapabilities."""

    def test_default_capabilities(self):
        """All capabilities should be False by default."""
        caps = ModelCapabilities()
        assert not caps.coding
        assert not caps.reasoning
        assert not caps.research
        assert not caps.tool_use
        assert not caps.long_context

    def test_has_capabilities_empty(self):
        """Empty required list should always match."""
        caps = ModelCapabilities()
        assert caps.has_capabilities([])

    def test_has_capabilities_single(self):
        """Single capability check."""
        caps = ModelCapabilities(coding=True)
        assert caps.has_capabilities(["coding"])
        assert not caps.has_capabilities(["reasoning"])

    def test_has_capabilities_multiple(self):
        """Multiple capability check."""
        caps = ModelCapabilities(coding=True, reasoning=True)
        assert caps.has_capabilities(["coding", "reasoning"])
        assert not caps.has_capabilities(["coding", "research"])


class TestModelInfo:
    """Test ModelInfo."""

    def test_matches_cost_in_tier(self):
        """Cost within tier should match."""
        model = ModelInfo(id="test", name="Test", cost_tier=(31, 60))
        assert model.matches_cost(31)
        assert model.matches_cost(45)
        assert model.matches_cost(60)

    def test_matches_cost_outside_tier(self):
        """Cost outside tier should not match."""
        model = ModelInfo(id="test", name="Test", cost_tier=(31, 60))
        assert not model.matches_cost(30)
        assert not model.matches_cost(61)


class TestProviderConfig:
    """Test ProviderConfig."""

    def test_config_defaults(self):
        """Config should have sensible defaults."""
        config = ProviderConfig(api_key="test-key")
        assert config.api_key == "test-key"
        assert config.base_url is None
        assert config.timeout == 30
        assert config.max_retries == 3


class TestMessage:
    """Test Message."""

    def test_message_creation(self):
        """Message should store role and content."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"


class TestCompletionResult:
    """Test CompletionResult."""

    def test_completion_result(self):
        """CompletionResult should store all fields."""
        result = CompletionResult(
            content="Response",
            model="test-model",
            usage={"input_tokens": 10, "output_tokens": 20},
            stop_reason="end_turn",
        )
        assert result.content == "Response"
        assert result.model == "test-model"
        assert result.usage["input_tokens"] == 10
        assert result.stop_reason == "end_turn"


class TestProviderBase:
    """Test Provider base class."""

    @pytest.fixture
    def provider(self):
        """Create a mock provider."""
        config = ProviderConfig(api_key="test-key")
        return MockProvider(config)

    def test_provider_name(self, provider):
        """Provider should have a name."""
        assert provider.name == "mock"

    def test_provider_models(self, provider):
        """Provider should list models."""
        models = provider.models
        assert len(models) == 3

    def test_select_model_by_cost(self, provider):
        """Should select model by cost tier."""
        model = provider.select_model(25)
        assert model.id == "mock-cheap"

        model = provider.select_model(50)
        assert model.id == "mock-mid"

        model = provider.select_model(80)
        assert model.id == "mock-premium"

    def test_select_model_with_capabilities(self, provider):
        """Should filter by capabilities."""
        # Cheap model doesn't have coding
        model = provider.select_model(25, ["reasoning"])
        assert model.id == "mock-cheap"

        # Mid model has coding
        model = provider.select_model(50, ["coding"])
        assert model.id == "mock-mid"

    def test_select_model_no_match(self, provider):
        """Should raise if no model matches cost."""
        with pytest.raises(ValueError):
            provider.select_model(101)  # Out of range

    def test_complete(self, provider):
        """Should return completion result."""
        messages = [Message(role="user", content="Hello")]
        result = provider.complete(messages)
        assert result.content == "Mock response"

    def test_supports_streaming(self, provider):
        """Should indicate streaming support."""
        assert not provider.supports_streaming()


class TestProviderRegistry:
    """Test ProviderRegistry."""

    @pytest.fixture
    def registry(self):
        """Create registry with mock provider."""
        reg = ProviderRegistry()
        config = ProviderConfig(api_key="test")
        reg.register(MockProvider(config, "mock1"))
        reg.register(MockProvider(config, "mock2"))
        return reg

    def test_register_and_get(self, registry):
        """Should register and retrieve providers."""
        provider = registry.get("mock1")
        assert provider.name == "mock1"

    def test_get_missing_raises(self, registry):
        """Should raise for missing provider."""
        with pytest.raises(ValueError):
            registry.get("nonexistent")

    def test_has_provider(self, registry):
        """Should check if provider exists."""
        assert registry.has("mock1")
        assert not registry.has("nonexistent")

    def test_unregister(self, registry):
        """Should unregister provider."""
        registry.unregister("mock1")
        assert not registry.has("mock1")

    def test_set_default(self, registry):
        """Should set and get default provider."""
        registry.set_default("mock1")
        assert registry.default.name == "mock1"
        assert registry.default_name == "mock1"

    def test_default_not_set_raises(self):
        """Should raise if no default."""
        reg = ProviderRegistry()
        with pytest.raises(ValueError):
            _ = reg.default

    def test_list_providers(self, registry):
        """Should list all provider names."""
        names = registry.list_providers()
        assert "mock1" in names
        assert "mock2" in names

    def test_len(self, registry):
        """Should return provider count."""
        assert len(registry) == 2

    def test_select_for_worker_basic(self, registry):
        """Should select provider and model for worker."""
        registry.set_default("mock1")
        provider, model = registry.select_for_worker(cost=50, skills={})
        assert provider.name == "mock1"
        assert model.cost_tier[0] <= 50 <= model.cost_tier[1]

    def test_select_for_worker_with_skills(self, registry):
        """Should derive capabilities from skills."""
        registry.set_default("mock1")
        # Coding skill >= 80 requires coding capability
        provider, model = registry.select_for_worker(
            cost=50,
            skills={"coding": 85, "reasoning": 70}
        )
        assert model.capabilities.coding

    def test_select_for_worker_preferred(self, registry):
        """Should use preferred provider first."""
        registry.set_default("mock1")
        provider, model = registry.select_for_worker(
            cost=50,
            skills={},
            preferred_provider="mock2"
        )
        assert provider.name == "mock2"

    def test_select_for_worker_no_match(self):
        """Should raise if no provider matches."""
        reg = ProviderRegistry()
        with pytest.raises(ValueError):
            reg.select_for_worker(cost=50, skills={})


class TestEnvVarExpansion:
    """Test environment variable expansion."""

    def test_no_vars(self):
        """Should return unchanged if no vars."""
        assert _expand_env_vars("plain text") == "plain text"

    def test_expand_var(self, monkeypatch):
        """Should expand ${VAR}."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        assert _expand_env_vars("${TEST_VAR}") == "test_value"

    def test_expand_missing_var(self, monkeypatch):
        """Should expand to empty for missing var."""
        monkeypatch.delenv("MISSING_VAR", raising=False)
        assert _expand_env_vars("${MISSING_VAR}") == ""

    def test_expand_in_string(self, monkeypatch):
        """Should expand var within string."""
        monkeypatch.setenv("API_KEY", "sk-123")
        assert _expand_env_vars("Bearer ${API_KEY}") == "Bearer sk-123"


class TestLoadProvidersFromConfig:
    """Test config-based provider loading."""

    @pytest.fixture
    def config_file(self):
        """Create temporary config file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("""
default: mock1
providers:
  mock1:
    enabled: true
    api_key: test-key-1
  mock2:
    enabled: true
    api_key: test-key-2
  disabled:
    enabled: false
    api_key: should-not-load
""")
            f.flush()
            path = Path(f.name)
        yield path

    def test_load_enabled_providers(self, config_file):
        """Should load enabled providers."""
        registry = load_providers_from_config(
            config_file,
            provider_classes={
                "mock1": lambda c: MockProvider(c, "mock1"),
                "mock2": lambda c: MockProvider(c, "mock2"),
                "disabled": lambda c: MockProvider(c, "disabled"),
            }
        )
        assert registry.has("mock1")
        assert registry.has("mock2")
        assert not registry.has("disabled")

    def test_set_default_from_config(self, config_file):
        """Should set default from config."""
        registry = load_providers_from_config(
            config_file,
            provider_classes={
                "mock1": lambda c: MockProvider(c, "mock1"),
                "mock2": lambda c: MockProvider(c, "mock2"),
            }
        )
        assert registry.default_name == "mock1"

    def test_missing_config_raises(self):
        """Should raise for missing config file."""
        with pytest.raises(FileNotFoundError):
            load_providers_from_config(Path("/nonexistent/config.yaml"))


class TestProviderError:
    """Test ProviderError."""

    def test_provider_error(self):
        """Should store provider and cause."""
        cause = ValueError("original")
        error = ProviderError("Failed", "mock", cause)
        assert str(error) == "Failed"
        assert error.provider == "mock"
        assert error.cause is cause
