"""Tests for the WorkerConfig dataclass.

Tests configuration creation, tier property, reports_to_human, skill methods, and capabilities.
"""

import pytest

from wrkr.core.config import WorkerConfig


class TestWorkerConfigCreation:
    """Tests for creating WorkerConfig instances."""

    def test_minimal_creation(self) -> None:
        """WorkerConfig can be created with only required fields."""
        config = WorkerConfig(id="worker-1", name="Worker One")
        assert config.id == "worker-1"
        assert config.name == "Worker One"

    def test_default_skills(self) -> None:
        """Default skills is an empty dict."""
        config = WorkerConfig(id="w1", name="Worker")
        assert config.skills == {}
        assert isinstance(config.skills, dict)

    def test_default_cost(self) -> None:
        """Default cost is 50 (mid-tier)."""
        config = WorkerConfig(id="w1", name="Worker")
        assert config.cost == 50

    def test_default_role_id(self) -> None:
        """Default role_id is empty string."""
        config = WorkerConfig(id="w1", name="Worker")
        assert config.role_id == ""

    def test_default_boss_id(self) -> None:
        """Default boss_id is None (reports to human)."""
        config = WorkerConfig(id="w1", name="Worker")
        assert config.boss_id is None

    def test_default_is_manager(self) -> None:
        """Default is_manager is False."""
        config = WorkerConfig(id="w1", name="Worker")
        assert config.is_manager is False

    def test_default_idle_behavior(self) -> None:
        """Default idle_behavior is 'poll'."""
        config = WorkerConfig(id="w1", name="Worker")
        assert config.idle_behavior == "poll"

    def test_default_poll_interval(self) -> None:
        """Default poll_interval is 5.0 seconds."""
        config = WorkerConfig(id="w1", name="Worker")
        assert config.poll_interval == 5.0

    def test_full_creation(self) -> None:
        """WorkerConfig can be created with all fields specified."""
        config = WorkerConfig(
            id="worker-full",
            name="Full Worker",
            skills={"coding": 90, "reasoning": 80},
            cost=75,
            role_id="senior-dev",
            boss_id="manager-1",
            is_manager=True,
            idle_behavior="wait",
            poll_interval=15.0,
        )

        assert config.id == "worker-full"
        assert config.name == "Full Worker"
        assert config.skills == {"coding": 90, "reasoning": 80}
        assert config.cost == 75
        assert config.role_id == "senior-dev"
        assert config.boss_id == "manager-1"
        assert config.is_manager is True
        assert config.idle_behavior == "wait"
        assert config.poll_interval == 15.0


class TestTierProperty:
    """Tests for the tier property based on cost score."""

    def test_tier_cost_0(self) -> None:
        """Cost 0 is cheap tier."""
        config = WorkerConfig(id="w1", name="Worker", cost=0)
        assert config.tier == "cheap"

    def test_tier_cost_15(self) -> None:
        """Cost 15 is cheap tier."""
        config = WorkerConfig(id="w1", name="Worker", cost=15)
        assert config.tier == "cheap"

    def test_tier_cost_30(self) -> None:
        """Cost 30 is cheap tier (boundary)."""
        config = WorkerConfig(id="w1", name="Worker", cost=30)
        assert config.tier == "cheap"

    def test_tier_cost_31(self) -> None:
        """Cost 31 is mid tier (boundary)."""
        config = WorkerConfig(id="w1", name="Worker", cost=31)
        assert config.tier == "mid"

    def test_tier_cost_45(self) -> None:
        """Cost 45 is mid tier."""
        config = WorkerConfig(id="w1", name="Worker", cost=45)
        assert config.tier == "mid"

    def test_tier_cost_60(self) -> None:
        """Cost 60 is mid tier (boundary)."""
        config = WorkerConfig(id="w1", name="Worker", cost=60)
        assert config.tier == "mid"

    def test_tier_cost_61(self) -> None:
        """Cost 61 is top tier (boundary)."""
        config = WorkerConfig(id="w1", name="Worker", cost=61)
        assert config.tier == "top"

    def test_tier_cost_80(self) -> None:
        """Cost 80 is top tier."""
        config = WorkerConfig(id="w1", name="Worker", cost=80)
        assert config.tier == "top"

    def test_tier_cost_100(self) -> None:
        """Cost 100 is top tier."""
        config = WorkerConfig(id="w1", name="Worker", cost=100)
        assert config.tier == "top"


class TestReportsToHuman:
    """Tests for the reports_to_human property."""

    def test_reports_to_human_none_boss(self) -> None:
        """Worker with no boss reports to human."""
        config = WorkerConfig(id="w1", name="Worker", boss_id=None)
        assert config.reports_to_human is True

    def test_reports_to_human_with_boss(self) -> None:
        """Worker with a boss does not report to human."""
        config = WorkerConfig(id="w1", name="Worker", boss_id="manager-1")
        assert config.reports_to_human is False

    def test_reports_to_human_empty_string_boss(self) -> None:
        """Worker with empty string boss_id does not report to human."""
        config = WorkerConfig(id="w1", name="Worker", boss_id="")
        assert config.reports_to_human is False


class TestGetSkill:
    """Tests for the get_skill() method."""

    def test_get_skill_exists(self) -> None:
        """get_skill returns correct value for existing skill."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 85, "reasoning": 70},
        )
        assert config.get_skill("coding") == 85
        assert config.get_skill("reasoning") == 70

    def test_get_skill_not_exists(self) -> None:
        """get_skill returns 0 for non-existent skill."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 85},
        )
        assert config.get_skill("management") == 0

    def test_get_skill_empty_skills(self) -> None:
        """get_skill returns 0 when skills dict is empty."""
        config = WorkerConfig(id="w1", name="Worker", skills={})
        assert config.get_skill("coding") == 0

    def test_get_skill_zero_value(self) -> None:
        """get_skill returns 0 for skill explicitly set to 0."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 0},
        )
        assert config.get_skill("coding") == 0


class TestHasCapability:
    """Tests for the has_capability() method."""

    def test_has_capability_above_default_threshold(self) -> None:
        """has_capability returns True when skill >= 50 (default)."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 80},
        )
        assert config.has_capability("coding") is True

    def test_has_capability_at_default_threshold(self) -> None:
        """has_capability returns True when skill == 50 (default)."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 50},
        )
        assert config.has_capability("coding") is True

    def test_has_capability_below_default_threshold(self) -> None:
        """has_capability returns False when skill < 50 (default)."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 49},
        )
        assert config.has_capability("coding") is False

    def test_has_capability_custom_threshold_above(self) -> None:
        """has_capability returns True when skill >= custom threshold."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 75},
        )
        assert config.has_capability("coding", min_level=70) is True

    def test_has_capability_custom_threshold_at(self) -> None:
        """has_capability returns True when skill == custom threshold."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 70},
        )
        assert config.has_capability("coding", min_level=70) is True

    def test_has_capability_custom_threshold_below(self) -> None:
        """has_capability returns False when skill < custom threshold."""
        config = WorkerConfig(
            id="w1",
            name="Worker",
            skills={"coding": 69},
        )
        assert config.has_capability("coding", min_level=70) is False

    def test_has_capability_missing_skill(self) -> None:
        """has_capability returns False for missing skill (treated as 0)."""
        config = WorkerConfig(id="w1", name="Worker", skills={})
        assert config.has_capability("coding") is False
        assert config.has_capability("coding", min_level=1) is False

    def test_has_capability_zero_threshold(self) -> None:
        """has_capability with min_level=0 always True for missing skills."""
        config = WorkerConfig(id="w1", name="Worker", skills={})
        assert config.has_capability("coding", min_level=0) is True


class TestIdleBehaviors:
    """Tests for the idle_behavior field."""

    def test_idle_behavior_wait(self) -> None:
        """idle_behavior can be 'wait'."""
        config = WorkerConfig(id="w1", name="Worker", idle_behavior="wait")
        assert config.idle_behavior == "wait"

    def test_idle_behavior_poll(self) -> None:
        """idle_behavior can be 'poll'."""
        config = WorkerConfig(id="w1", name="Worker", idle_behavior="poll")
        assert config.idle_behavior == "poll"

    def test_idle_behavior_exit(self) -> None:
        """idle_behavior can be 'exit'."""
        config = WorkerConfig(id="w1", name="Worker", idle_behavior="exit")
        assert config.idle_behavior == "exit"


class TestConfigWithFixtures:
    """Tests using fixtures from conftest."""

    def test_sample_config_fixture(self, sample_config: WorkerConfig) -> None:
        """sample_config fixture has expected values."""
        assert sample_config.id == "worker-001"
        assert sample_config.name == "Test Worker"
        assert sample_config.cost == 50
        assert sample_config.tier == "mid"
        assert sample_config.boss_id == "manager-001"
        assert sample_config.reports_to_human is False
        assert sample_config.is_manager is False
        assert sample_config.idle_behavior == "exit"

    def test_manager_config_fixture(self, manager_config: WorkerConfig) -> None:
        """manager_config fixture has expected values."""
        assert manager_config.id == "manager-001"
        assert manager_config.boss_id is None
        assert manager_config.reports_to_human is True
        assert manager_config.is_manager is True
        assert manager_config.cost == 75
        assert manager_config.tier == "top"
        assert manager_config.idle_behavior == "poll"

    def test_cheap_config_fixture(self, cheap_config: WorkerConfig) -> None:
        """cheap_config fixture is cheap tier."""
        assert cheap_config.cost == 15
        assert cheap_config.tier == "cheap"

    def test_top_config_fixture(self, top_config: WorkerConfig) -> None:
        """top_config fixture is top tier."""
        assert top_config.cost == 95
        assert top_config.tier == "top"
        assert top_config.reports_to_human is True

    def test_sample_config_skills(self, sample_config: WorkerConfig) -> None:
        """sample_config has expected skills."""
        assert sample_config.get_skill("coding") == 80
        assert sample_config.get_skill("reasoning") == 70
        assert sample_config.get_skill("research") == 60
        assert sample_config.get_skill("management") == 30
        assert sample_config.get_skill("strategy") == 20
        assert sample_config.get_skill("creative") == 50

    def test_sample_config_capabilities(self, sample_config: WorkerConfig) -> None:
        """sample_config has expected capabilities."""
        assert sample_config.has_capability("coding") is True
        assert sample_config.has_capability("reasoning") is True
        assert sample_config.has_capability("research") is True
        assert sample_config.has_capability("management") is False
        assert sample_config.has_capability("strategy") is False
        assert sample_config.has_capability("creative") is True


class TestConfigMutability:
    """Tests for config field mutability."""

    def test_skills_mutable(self) -> None:
        """skills dict can be modified after creation."""
        config = WorkerConfig(id="w1", name="Worker", skills={})
        config.skills["coding"] = 90
        assert config.get_skill("coding") == 90

    def test_separate_instances_have_separate_skills(self) -> None:
        """Each config instance has its own skills dict."""
        config1 = WorkerConfig(id="w1", name="Worker1")
        config2 = WorkerConfig(id="w2", name="Worker2")

        config1.skills["coding"] = 90

        assert config1.get_skill("coding") == 90
        assert config2.get_skill("coding") == 0
