"""
Unit tests for provider selection algorithm.

Tests the tier-based provider selection system including:
- cost_to_tier() mapping
- skills_to_capabilities() conversion
- select_provider_for_worker() function
- get_model_for_worker() function
- ProviderSelectionError handling
- Model upgrade logic
"""

import pytest

from providers.base import (
    CostTier,
    CompletionResult,
    Message,
    ModelCapabilities,
    ModelInfo,
    Provider,
    ProviderConfig,
)
from core.provider import (
    DEFAULT_THRESHOLDS,
    ProviderRegistry,
    ProviderSelection,
    ProviderSelectionError,
    cost_to_tier,
    get_model_for_worker,
    select_provider_for_worker,
    skills_to_capabilities,
)


class MockTieredProvider(Provider):
    """Mock provider with tier-based models for testing."""

    def __init__(
        self,
        config: ProviderConfig,
        provider_name: str = "mock",
        models: list[ModelInfo] | None = None,
    ):
        super().__init__(config)
        self._name = provider_name
        self._models = models if models is not None else self._default_models()

    def _default_models(self) -> list[ModelInfo]:
        """Return default tiered models."""
        return [
            ModelInfo(
                id="mock-budget",
                name="Mock Budget",
                tier=CostTier.BUDGET,
                cost_tier=(0, 30),
                max_tokens=4096,
                capabilities=ModelCapabilities(tool_use=True),
            ),
            ModelInfo(
                id="mock-standard",
                name="Mock Standard",
                tier=CostTier.STANDARD,
                cost_tier=(31, 60),
                max_tokens=8192,
                capabilities=ModelCapabilities(
                    coding=True, reasoning=True, tool_use=True
                ),
            ),
            ModelInfo(
                id="mock-advanced",
                name="Mock Advanced",
                tier=CostTier.ADVANCED,
                cost_tier=(61, 80),
                max_tokens=16384,
                capabilities=ModelCapabilities(
                    coding=True, reasoning=True, research=True, tool_use=True
                ),
            ),
            ModelInfo(
                id="mock-premium",
                name="Mock Premium",
                tier=CostTier.PREMIUM,
                cost_tier=(81, 100),
                max_tokens=32768,
                capabilities=ModelCapabilities(
                    coding=True,
                    reasoning=True,
                    research=True,
                    tool_use=True,
                    long_context=True,
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
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResult:
        return CompletionResult(
            content="Mock response",
            model=model or "mock-standard",
            usage={"input_tokens": 10, "output_tokens": 5},
            stop_reason="end_turn",
        )

    def supports_streaming(self) -> bool:
        return False


class TestCostToTier:
    """Test cost_to_tier() function."""

    def test_budget_tier_boundaries(self):
        """Budget tier: 0-30."""
        assert cost_to_tier(0) == CostTier.BUDGET
        assert cost_to_tier(15) == CostTier.BUDGET
        assert cost_to_tier(30) == CostTier.BUDGET

    def test_standard_tier_boundaries(self):
        """Standard tier: 31-60."""
        assert cost_to_tier(31) == CostTier.STANDARD
        assert cost_to_tier(45) == CostTier.STANDARD
        assert cost_to_tier(60) == CostTier.STANDARD

    def test_advanced_tier_boundaries(self):
        """Advanced tier: 61-80."""
        assert cost_to_tier(61) == CostTier.ADVANCED
        assert cost_to_tier(70) == CostTier.ADVANCED
        assert cost_to_tier(80) == CostTier.ADVANCED

    def test_premium_tier_boundaries(self):
        """Premium tier: 81-100."""
        assert cost_to_tier(81) == CostTier.PREMIUM
        assert cost_to_tier(90) == CostTier.PREMIUM
        assert cost_to_tier(100) == CostTier.PREMIUM


class TestSkillsToCapabilities:
    """Test skills_to_capabilities() function."""

    def test_empty_skills(self):
        """Empty skills should return empty capabilities."""
        assert skills_to_capabilities({}) == []

    def test_below_threshold_skills(self):
        """Skills below threshold should not trigger capabilities."""
        skills = {
            "coding": 79,  # Below 80
            "reasoning": 59,  # Below 60
            "research": 79,  # Below 80
            "management": 69,  # Below 70
            "strategy": 89,  # Below 90
        }
        assert skills_to_capabilities(skills) == []

    def test_at_threshold_skills(self):
        """Skills at threshold should trigger capabilities."""
        skills = {
            "coding": 80,
            "reasoning": 60,
            "research": 80,
            "management": 70,
            "strategy": 90,
        }
        caps = skills_to_capabilities(skills)
        assert "coding" in caps
        assert "reasoning" in caps
        assert "research" in caps
        assert "tool_use" in caps
        assert "long_context" in caps

    def test_single_skill_above_threshold(self):
        """Single skill above threshold."""
        assert skills_to_capabilities({"coding": 95}) == ["coding"]
        assert skills_to_capabilities({"reasoning": 70}) == ["reasoning"]
        assert skills_to_capabilities({"management": 75}) == ["tool_use"]

    def test_custom_thresholds(self):
        """Custom thresholds should override defaults."""
        skills = {"coding": 50}
        # Default threshold is 80, so this shouldn't trigger
        assert skills_to_capabilities(skills) == []
        # Custom lower threshold should trigger
        assert skills_to_capabilities(skills, {"coding": 40}) == ["coding"]

    def test_unknown_skills_ignored(self):
        """Unknown skills should be ignored."""
        skills = {"coding": 90, "unknown_skill": 100}
        assert skills_to_capabilities(skills) == ["coding"]


class TestModelInfoTier:
    """Test ModelInfo tier-related methods."""

    def test_matches_tier_with_explicit_tier(self):
        """Model with explicit tier should match."""
        model = ModelInfo(
            id="test",
            name="Test",
            tier=CostTier.STANDARD,
        )
        assert model.matches_tier(CostTier.STANDARD)
        assert not model.matches_tier(CostTier.BUDGET)

    def test_matches_tier_with_multiple_tiers(self):
        """Model with multiple tiers should match any."""
        model = ModelInfo(
            id="test",
            name="Test",
            tiers=[CostTier.STANDARD, CostTier.ADVANCED],
        )
        assert model.matches_tier(CostTier.STANDARD)
        assert model.matches_tier(CostTier.ADVANCED)
        assert not model.matches_tier(CostTier.BUDGET)
        assert not model.matches_tier(CostTier.PREMIUM)

    def test_matches_tier_fallback_to_cost_tier(self):
        """Model without explicit tier should derive from cost_tier."""
        model = ModelInfo(
            id="test",
            name="Test",
            cost_tier=(31, 60),  # Standard range
        )
        assert model.matches_tier(CostTier.STANDARD)


class TestProviderRegistryThresholds:
    """Test ProviderRegistry threshold management."""

    def test_default_thresholds(self):
        """Registry should have default thresholds."""
        registry = ProviderRegistry()
        assert registry.thresholds["coding"] == 80
        assert registry.thresholds["reasoning"] == 60
        assert registry.thresholds["research"] == 80
        assert registry.thresholds["management"] == 70
        assert registry.thresholds["strategy"] == 90

    def test_set_thresholds(self):
        """Setting thresholds should update values."""
        registry = ProviderRegistry()
        registry.set_thresholds(coding=70, management=60)
        assert registry.thresholds["coding"] == 70
        assert registry.thresholds["management"] == 60
        # Others unchanged
        assert registry.thresholds["reasoning"] == 60

    def test_thresholds_independent_between_registries(self):
        """Each registry should have independent thresholds."""
        reg1 = ProviderRegistry()
        reg2 = ProviderRegistry()
        reg1.set_thresholds(coding=50)
        assert reg1.thresholds["coding"] == 50
        assert reg2.thresholds["coding"] == 80  # Unchanged


class TestSelectProviderForWorker:
    """Test select_provider_for_worker() function."""

    @pytest.fixture
    def registry(self):
        """Create registry with mock providers."""
        reg = ProviderRegistry()
        config = ProviderConfig(api_key="test")
        reg.register(MockTieredProvider(config, "provider1"))
        reg.register(MockTieredProvider(config, "provider2"))
        reg.set_default("provider1")
        return reg

    def test_basic_selection(self, registry):
        """Should select provider and model based on cost."""
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=50,
            worker_skills={},
        )
        assert selection.provider.name == "provider1"
        assert selection.tier == CostTier.STANDARD
        assert selection.model.tier == CostTier.STANDARD

    def test_budget_tier_selection(self, registry):
        """Low cost should select budget tier."""
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=20,
            worker_skills={},
        )
        assert selection.tier == CostTier.BUDGET
        assert selection.model.id == "mock-budget"

    def test_premium_tier_selection(self, registry):
        """High cost should select premium tier."""
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=95,
            worker_skills={},
        )
        assert selection.tier == CostTier.PREMIUM
        assert selection.model.id == "mock-premium"

    def test_preferred_provider_honored(self, registry):
        """Preferred provider should be tried first."""
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=50,
            worker_skills={},
            preferred_provider="provider2",
        )
        assert selection.provider.name == "provider2"

    def test_capabilities_derived_from_skills(self, registry):
        """Skills should derive required capabilities."""
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=50,
            worker_skills={"coding": 90, "reasoning": 70},
        )
        assert "coding" in selection.required_capabilities
        assert "reasoning" in selection.required_capabilities

    def test_model_upgrade_for_capabilities(self, registry):
        """Should upgrade tier if capabilities require it."""
        # Budget tier doesn't have coding capability
        # So it should upgrade to standard or higher
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=20,  # Budget tier
            worker_skills={"coding": 90},  # Requires coding
        )
        # Should upgrade from budget to at least standard
        assert selection.model.capabilities.coding

    def test_authorized_providers_filter(self, registry):
        """Should only use authorized providers."""
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=50,
            worker_skills={},
            org_authorized_providers=["provider2"],
        )
        assert selection.provider.name == "provider2"

    def test_unauthorized_preferred_skipped(self, registry):
        """Unauthorized preferred provider should be skipped."""
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=50,
            worker_skills={},
            preferred_provider="provider1",
            org_authorized_providers=["provider2"],
        )
        # provider1 preferred but not authorized, should use provider2
        assert selection.provider.name == "provider2"

    def test_selection_returns_metadata(self, registry):
        """Selection should include metadata."""
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=75,
            worker_skills={"research": 85},
        )
        assert isinstance(selection, ProviderSelection)
        assert selection.tier == CostTier.ADVANCED
        assert "research" in selection.required_capabilities
        assert selection.was_fallback is False


class TestProviderSelectionError:
    """Test ProviderSelectionError."""

    def test_no_providers_raises_error(self):
        """Should raise error when no providers registered."""
        registry = ProviderRegistry()
        with pytest.raises(ProviderSelectionError) as exc_info:
            select_provider_for_worker(
                registry=registry,
                worker_cost=50,
                worker_skills={},
            )
        assert exc_info.value.cost == 50
        assert exc_info.value.attempted == []

    def test_error_includes_attempted_providers(self):
        """Error should include which providers were tried."""
        registry = ProviderRegistry()
        config = ProviderConfig(api_key="test")
        # Provider with no models
        provider = MockTieredProvider(config, "empty", models=[])
        registry.register(provider)

        with pytest.raises(ProviderSelectionError) as exc_info:
            select_provider_for_worker(
                registry=registry,
                worker_cost=50,
                worker_skills={},
            )
        assert "empty" in exc_info.value.attempted

    def test_error_includes_capabilities(self):
        """Error should include required capabilities."""
        registry = ProviderRegistry()
        config = ProviderConfig(api_key="test")
        # Provider without coding capability
        provider = MockTieredProvider(
            config,
            "limited",
            models=[
                ModelInfo(
                    id="limited-model",
                    name="Limited",
                    tier=CostTier.BUDGET,
                    cost_tier=(0, 100),
                    capabilities=ModelCapabilities(),  # No capabilities
                )
            ],
        )
        registry.register(provider)

        # Request capability that doesn't exist, but budget model has no caps
        # so it should still succeed (caps are preferences, not hard requirements)
        selection = select_provider_for_worker(
            registry=registry,
            worker_cost=20,
            worker_skills={"coding": 90},
        )
        # Should still select, just won't have the capability
        assert selection.provider.name == "limited"


class TestModelUpgradeLogic:
    """Test model tier upgrade when capabilities require it."""

    @pytest.fixture
    def limited_registry(self):
        """Registry with provider that has limited capability models."""
        reg = ProviderRegistry()
        config = ProviderConfig(api_key="test")
        # Budget has no coding, standard has coding
        provider = MockTieredProvider(
            config,
            "limited",
            models=[
                ModelInfo(
                    id="budget-no-coding",
                    name="Budget",
                    tier=CostTier.BUDGET,
                    cost_tier=(0, 30),
                    capabilities=ModelCapabilities(tool_use=True),
                ),
                ModelInfo(
                    id="standard-with-coding",
                    name="Standard",
                    tier=CostTier.STANDARD,
                    cost_tier=(31, 60),
                    capabilities=ModelCapabilities(coding=True, tool_use=True),
                ),
            ],
        )
        reg.register(provider)
        reg.set_default("limited")
        return reg

    def test_upgrades_to_meet_capabilities(self, limited_registry):
        """Should upgrade tier to meet capability requirements."""
        selection = select_provider_for_worker(
            registry=limited_registry,
            worker_cost=20,  # Budget tier
            worker_skills={"coding": 90},  # Requires coding
        )
        # Should upgrade from budget to standard
        assert selection.model.id == "standard-with-coding"
        assert selection.model.capabilities.coding

    def test_no_upgrade_if_not_needed(self, limited_registry):
        """Should not upgrade if current tier satisfies capabilities."""
        selection = select_provider_for_worker(
            registry=limited_registry,
            worker_cost=20,  # Budget tier
            worker_skills={},  # No capabilities needed
        )
        assert selection.model.id == "budget-no-coding"


class TestMultipleProviderFallback:
    """Test fallback behavior when primary provider fails."""

    @pytest.fixture
    def fallback_registry(self):
        """Registry with one failing and one working provider."""
        reg = ProviderRegistry()
        config = ProviderConfig(api_key="test")

        # First provider has NO models at all
        failing = MockTieredProvider(
            config,
            "failing",
            models=[],  # Empty - will fail for any request
        )
        reg.register(failing)

        # Second provider has standard tier
        working = MockTieredProvider(config, "working")
        reg.register(working)

        reg.set_default("failing")
        return reg

    def test_falls_back_to_next_provider(self, fallback_registry):
        """Should fall back to next provider if primary fails."""
        selection = select_provider_for_worker(
            registry=fallback_registry,
            worker_cost=50,  # Standard tier
            worker_skills={},
        )
        # Default provider "failing" has no models
        # Should fall back to "working"
        assert selection.provider.name == "working"

    def test_upgrade_happens_before_fallback(self):
        """Should try upgrading tier before falling back to another provider."""
        reg = ProviderRegistry()
        config = ProviderConfig(api_key="test")

        # Primary provider has only premium tier
        primary = MockTieredProvider(
            config,
            "primary",
            models=[
                ModelInfo(
                    id="premium-only",
                    name="Premium Only",
                    tier=CostTier.PREMIUM,
                    cost_tier=(81, 100),
                    capabilities=ModelCapabilities(coding=True),
                )
            ],
        )
        reg.register(primary)

        # Secondary provider has standard tier
        secondary = MockTieredProvider(config, "secondary")
        reg.register(secondary)

        reg.set_default("primary")

        # Request standard tier - primary should upgrade to premium
        selection = select_provider_for_worker(
            registry=reg,
            worker_cost=50,  # Standard tier
            worker_skills={},
        )
        # Should stay with primary, upgrading to premium
        assert selection.provider.name == "primary"
        assert selection.model.id == "premium-only"


class TestGetModelForWorker:
    """Test get_model_for_worker() function.

    This tests the simplified interface that returns just ModelInfo
    based on worker cost and required capabilities.
    """

    @pytest.fixture
    def registry(self):
        """Create registry with mock providers."""
        reg = ProviderRegistry()
        config = ProviderConfig(api_key="test")
        reg.register(MockTieredProvider(config, "provider1"))
        reg.register(MockTieredProvider(config, "provider2"))
        reg.set_default("provider1")
        return reg

    def test_basic_model_selection(self, registry):
        """Should return ModelInfo for the given cost tier."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=50,
        )
        assert isinstance(model, ModelInfo)
        assert model.tier == CostTier.STANDARD

    def test_budget_tier_model(self, registry):
        """Cost 0-30 should return budget tier model."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=20,
        )
        assert model.id == "mock-budget"
        assert model.tier == CostTier.BUDGET

    def test_standard_tier_model(self, registry):
        """Cost 31-60 should return standard tier model."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=45,
        )
        assert model.id == "mock-standard"
        assert model.tier == CostTier.STANDARD

    def test_advanced_tier_model(self, registry):
        """Cost 61-80 should return advanced tier model."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=70,
        )
        assert model.id == "mock-advanced"
        assert model.tier == CostTier.ADVANCED

    def test_premium_tier_model(self, registry):
        """Cost 81-100 should return premium tier model."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=95,
        )
        assert model.id == "mock-premium"
        assert model.tier == CostTier.PREMIUM

    def test_tier_boundary_at_30(self, registry):
        """Cost 30 should be budget, 31 should be standard."""
        budget_model = get_model_for_worker(registry=registry, worker_cost=30)
        standard_model = get_model_for_worker(registry=registry, worker_cost=31)
        assert budget_model.tier == CostTier.BUDGET
        assert standard_model.tier == CostTier.STANDARD

    def test_tier_boundary_at_60(self, registry):
        """Cost 60 should be standard, 61 should be advanced."""
        standard_model = get_model_for_worker(registry=registry, worker_cost=60)
        advanced_model = get_model_for_worker(registry=registry, worker_cost=61)
        assert standard_model.tier == CostTier.STANDARD
        assert advanced_model.tier == CostTier.ADVANCED

    def test_tier_boundary_at_80(self, registry):
        """Cost 80 should be advanced, 81 should be premium."""
        advanced_model = get_model_for_worker(registry=registry, worker_cost=80)
        premium_model = get_model_for_worker(registry=registry, worker_cost=81)
        assert advanced_model.tier == CostTier.ADVANCED
        assert premium_model.tier == CostTier.PREMIUM

    def test_with_required_capabilities(self, registry):
        """Should filter models by required capabilities."""
        # Request coding capability at budget tier
        # Budget model doesn't have coding, should upgrade
        model = get_model_for_worker(
            registry=registry,
            worker_cost=20,
            required_capabilities=["coding"],
        )
        # Should get a model that has coding capability
        assert model.capabilities.coding

    def test_multiple_capabilities(self, registry):
        """Should handle multiple required capabilities."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=70,
            required_capabilities=["coding", "reasoning"],
        )
        assert model.capabilities.coding
        assert model.capabilities.reasoning

    def test_preferred_provider(self, registry):
        """Should use preferred provider when available."""
        # Both providers have the same models, but we should get from provider2
        model = get_model_for_worker(
            registry=registry,
            worker_cost=50,
            preferred_provider="provider2",
        )
        assert isinstance(model, ModelInfo)
        assert model.tier == CostTier.STANDARD

    def test_authorized_providers_filter(self, registry):
        """Should only use authorized providers."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=50,
            org_authorized_providers=["provider2"],
        )
        assert isinstance(model, ModelInfo)

    def test_no_providers_raises_error(self):
        """Should raise ProviderSelectionError when no providers available."""
        empty_registry = ProviderRegistry()
        with pytest.raises(ProviderSelectionError) as exc_info:
            get_model_for_worker(
                registry=empty_registry,
                worker_cost=50,
            )
        assert exc_info.value.cost == 50
        assert exc_info.value.attempted == []

    def test_empty_capabilities_list(self, registry):
        """Empty capabilities list should work like None."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=50,
            required_capabilities=[],
        )
        assert model.tier == CostTier.STANDARD

    def test_none_capabilities(self, registry):
        """None capabilities should work like empty list."""
        model = get_model_for_worker(
            registry=registry,
            worker_cost=50,
            required_capabilities=None,
        )
        assert model.tier == CostTier.STANDARD

    def test_model_upgrade_preserves_capability_match(self):
        """When upgrading tier for capabilities, result should have those capabilities."""
        reg = ProviderRegistry()
        config = ProviderConfig(api_key="test")
        # Provider with budget (no coding) and advanced (has coding)
        provider = MockTieredProvider(
            config,
            "limited",
            models=[
                ModelInfo(
                    id="budget-basic",
                    name="Budget Basic",
                    tier=CostTier.BUDGET,
                    cost_tier=(0, 30),
                    capabilities=ModelCapabilities(tool_use=True),
                ),
                ModelInfo(
                    id="advanced-coding",
                    name="Advanced Coding",
                    tier=CostTier.ADVANCED,
                    cost_tier=(61, 80),
                    capabilities=ModelCapabilities(coding=True, reasoning=True),
                ),
            ],
        )
        reg.register(provider)
        reg.set_default("limited")

        # Request coding at budget cost - should upgrade to advanced
        model = get_model_for_worker(
            registry=reg,
            worker_cost=20,  # Budget tier
            required_capabilities=["coding"],
        )
        assert model.id == "advanced-coding"
        assert model.capabilities.coding
