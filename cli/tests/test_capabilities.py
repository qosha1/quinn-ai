"""
Unit tests for worker skills to model capabilities mapping.
"""

import pytest

from cli.core.capabilities import (
    ALL_CAPABILITIES,
    SKILL_THRESHOLDS,
    filter_capabilities_by_skills,
    get_capability_threshold,
    get_missing_skills_for_capability,
    get_worker_capabilities,
    worker_can_use_capability,
)


class TestGetWorkerCapabilities:
    """Test get_worker_capabilities function."""

    def test_empty_skills_returns_empty_list(self):
        """Should return empty list when no skills provided."""
        assert get_worker_capabilities({}) == []

    def test_coding_skill_at_threshold(self):
        """Should unlock coding at exactly 60."""
        assert "coding" in get_worker_capabilities({"coding": 60})

    def test_coding_skill_below_threshold(self):
        """Should not unlock coding below 60."""
        assert "coding" not in get_worker_capabilities({"coding": 59})

    def test_coding_skill_above_threshold(self):
        """Should unlock coding above 60."""
        assert "coding" in get_worker_capabilities({"coding": 100})

    def test_reasoning_skill_at_threshold(self):
        """Should unlock reasoning at exactly 50."""
        assert "reasoning" in get_worker_capabilities({"reasoning": 50})

    def test_reasoning_skill_below_threshold(self):
        """Should not unlock reasoning below 50."""
        assert "reasoning" not in get_worker_capabilities({"reasoning": 49})

    def test_research_skill_at_threshold(self):
        """Should unlock research at exactly 40."""
        assert "research" in get_worker_capabilities({"research": 40})

    def test_research_skill_below_threshold(self):
        """Should not unlock research below 40."""
        assert "research" not in get_worker_capabilities({"research": 39})

    def test_tool_use_skill_at_threshold(self):
        """Should unlock tool_use at exactly 30."""
        assert "tool_use" in get_worker_capabilities({"tool_use": 30})

    def test_tool_use_skill_below_threshold(self):
        """Should not unlock tool_use below 30."""
        assert "tool_use" not in get_worker_capabilities({"tool_use": 29})

    def test_multiple_skills_unlock_multiple_capabilities(self):
        """Should unlock multiple capabilities when skills meet thresholds."""
        skills = {"coding": 75, "reasoning": 60, "research": 45, "tool_use": 35}
        capabilities = get_worker_capabilities(skills)

        assert "coding" in capabilities
        assert "reasoning" in capabilities
        assert "research" in capabilities
        assert "tool_use" in capabilities

    def test_partial_skills_unlock_some_capabilities(self):
        """Should only unlock capabilities where skills meet threshold."""
        skills = {"coding": 50, "reasoning": 60, "research": 30, "tool_use": 40}
        capabilities = get_worker_capabilities(skills)

        # Coding requires 60, we have 50
        assert "coding" not in capabilities
        # Reasoning requires 50, we have 60
        assert "reasoning" in capabilities
        # Research requires 40, we have 30
        assert "research" not in capabilities
        # tool_use requires 30, we have 40
        assert "tool_use" in capabilities

    def test_unrelated_skills_ignored(self):
        """Should ignore skills that don't map to capabilities."""
        skills = {"communication": 90, "management": 80, "coding": 70}
        capabilities = get_worker_capabilities(skills)

        # Only coding should be unlocked
        assert capabilities == ["coding"]

    def test_skills_with_zero_values(self):
        """Should handle skills explicitly set to 0."""
        skills = {"coding": 0, "reasoning": 0, "research": 0, "tool_use": 0}
        assert get_worker_capabilities(skills) == []


class TestWorkerCanUseCapability:
    """Test worker_can_use_capability function."""

    def test_has_capability_at_threshold(self):
        """Should return True when skill meets threshold."""
        assert worker_can_use_capability({"coding": 60}, "coding") is True
        assert worker_can_use_capability({"reasoning": 50}, "reasoning") is True
        assert worker_can_use_capability({"research": 40}, "research") is True
        assert worker_can_use_capability({"tool_use": 30}, "tool_use") is True

    def test_lacks_capability_below_threshold(self):
        """Should return False when skill is below threshold."""
        assert worker_can_use_capability({"coding": 59}, "coding") is False
        assert worker_can_use_capability({"reasoning": 49}, "reasoning") is False
        assert worker_can_use_capability({"research": 39}, "research") is False
        assert worker_can_use_capability({"tool_use": 29}, "tool_use") is False

    def test_unknown_capability_returns_false(self):
        """Should return False for unknown capabilities."""
        assert worker_can_use_capability({"coding": 100}, "unknown") is False
        assert worker_can_use_capability({}, "flying") is False

    def test_missing_skill_returns_false(self):
        """Should return False when skill is missing from dict."""
        assert worker_can_use_capability({}, "coding") is False
        assert worker_can_use_capability({"reasoning": 80}, "coding") is False

    def test_high_skill_level(self):
        """Should return True for skills well above threshold."""
        assert worker_can_use_capability({"coding": 100}, "coding") is True
        assert worker_can_use_capability({"tool_use": 90}, "tool_use") is True


class TestGetCapabilityThreshold:
    """Test get_capability_threshold function."""

    def test_returns_threshold_for_known_capabilities(self):
        """Should return skill and threshold for known capabilities."""
        assert get_capability_threshold("coding") == ("coding", 60)
        assert get_capability_threshold("reasoning") == ("reasoning", 50)
        assert get_capability_threshold("research") == ("research", 40)
        assert get_capability_threshold("tool_use") == ("tool_use", 30)

    def test_returns_none_for_unknown_capability(self):
        """Should return None for unknown capabilities."""
        assert get_capability_threshold("unknown") is None
        assert get_capability_threshold("flying") is None
        assert get_capability_threshold("") is None


class TestGetMissingSkillsForCapability:
    """Test get_missing_skills_for_capability function."""

    def test_returns_gap_when_below_threshold(self):
        """Should return skill gap when below threshold."""
        assert get_missing_skills_for_capability({"coding": 45}, "coding") == (
            "coding",
            15,
        )
        assert get_missing_skills_for_capability({"reasoning": 30}, "reasoning") == (
            "reasoning",
            20,
        )
        assert get_missing_skills_for_capability({"research": 0}, "research") == (
            "research",
            40,
        )
        assert get_missing_skills_for_capability({"tool_use": 10}, "tool_use") == (
            "tool_use",
            20,
        )

    def test_returns_none_when_at_threshold(self):
        """Should return None when skill meets threshold."""
        assert get_missing_skills_for_capability({"coding": 60}, "coding") is None
        assert get_missing_skills_for_capability({"reasoning": 50}, "reasoning") is None

    def test_returns_none_when_above_threshold(self):
        """Should return None when skill exceeds threshold."""
        assert get_missing_skills_for_capability({"coding": 100}, "coding") is None
        assert get_missing_skills_for_capability({"tool_use": 90}, "tool_use") is None

    def test_returns_none_for_unknown_capability(self):
        """Should return None for unknown capabilities."""
        assert get_missing_skills_for_capability({"coding": 50}, "unknown") is None

    def test_returns_gap_when_skill_missing(self):
        """Should return full gap when skill not in dict."""
        assert get_missing_skills_for_capability({}, "coding") == ("coding", 60)
        assert get_missing_skills_for_capability({}, "tool_use") == ("tool_use", 30)


class TestFilterCapabilitiesBySkills:
    """Test filter_capabilities_by_skills function."""

    def test_all_capabilities_available(self):
        """Should return all as available when skills meet thresholds."""
        skills = {"coding": 60, "reasoning": 50, "research": 40, "tool_use": 30}
        available, missing = filter_capabilities_by_skills(
            skills, ["coding", "reasoning", "research", "tool_use"]
        )

        assert available == ["coding", "reasoning", "research", "tool_use"]
        assert missing == []

    def test_all_capabilities_missing(self):
        """Should return all as missing when skills below thresholds."""
        skills = {"coding": 0, "reasoning": 0, "research": 0, "tool_use": 0}
        available, missing = filter_capabilities_by_skills(
            skills, ["coding", "reasoning", "research", "tool_use"]
        )

        assert available == []
        assert missing == ["coding", "reasoning", "research", "tool_use"]

    def test_mixed_capabilities(self):
        """Should correctly split available and missing capabilities."""
        skills = {"coding": 75, "reasoning": 40}  # coding yes, reasoning no
        available, missing = filter_capabilities_by_skills(
            skills, ["coding", "reasoning", "research"]
        )

        assert available == ["coding"]
        assert "reasoning" in missing
        assert "research" in missing

    def test_empty_required_capabilities(self):
        """Should return empty lists for empty required capabilities."""
        available, missing = filter_capabilities_by_skills({"coding": 100}, [])
        assert available == []
        assert missing == []

    def test_preserves_order(self):
        """Should preserve order of capabilities in output."""
        skills = {"tool_use": 50, "research": 50, "reasoning": 60, "coding": 70}
        available, missing = filter_capabilities_by_skills(
            skills, ["coding", "reasoning", "research", "tool_use"]
        )

        # All should be available in the order requested
        assert available == ["coding", "reasoning", "research", "tool_use"]


class TestSkillThresholdsConsistency:
    """Test that SKILL_THRESHOLDS is consistent and well-formed."""

    def test_all_thresholds_have_skill_and_level(self):
        """Each threshold should have a skill name and level."""
        for capability, (skill_name, level) in SKILL_THRESHOLDS.items():
            assert isinstance(skill_name, str)
            assert isinstance(level, int)
            assert level > 0
            assert level <= 100

    def test_thresholds_match_documented_values(self):
        """Verify thresholds match the documented requirements."""
        assert SKILL_THRESHOLDS["coding"] == ("coding", 60)
        assert SKILL_THRESHOLDS["reasoning"] == ("reasoning", 50)
        assert SKILL_THRESHOLDS["research"] == ("research", 40)
        assert SKILL_THRESHOLDS["tool_use"] == ("tool_use", 30)

    def test_required_capabilities_exist(self):
        """Verify all required capabilities are defined."""
        required = ["coding", "reasoning", "research", "tool_use"]
        for cap in required:
            assert cap in SKILL_THRESHOLDS


class TestIntegrationWithWorkerConfig:
    """Integration tests showing capabilities work with WorkerConfig.skills format."""

    def test_senior_engineer_capabilities(self):
        """Senior engineer should have coding and reasoning capabilities."""
        # Typical senior engineer skills
        skills = {"coding": 85, "reasoning": 70, "research": 50, "tool_use": 60}
        capabilities = get_worker_capabilities(skills)

        assert "coding" in capabilities
        assert "reasoning" in capabilities
        assert "research" in capabilities
        assert "tool_use" in capabilities

    def test_junior_engineer_capabilities(self):
        """Junior engineer should have limited capabilities."""
        # Typical junior engineer skills
        skills = {"coding": 45, "reasoning": 40, "research": 30, "tool_use": 35}
        capabilities = get_worker_capabilities(skills)

        # Junior doesn't meet coding threshold
        assert "coding" not in capabilities
        # Junior doesn't meet reasoning threshold
        assert "reasoning" not in capabilities
        # Junior doesn't meet research threshold
        assert "research" not in capabilities
        # Junior meets tool_use threshold
        assert "tool_use" in capabilities

    def test_researcher_capabilities(self):
        """Researcher should have research but maybe not coding capabilities."""
        skills = {"coding": 30, "reasoning": 65, "research": 80, "tool_use": 50}
        capabilities = get_worker_capabilities(skills)

        assert "coding" not in capabilities
        assert "reasoning" in capabilities
        assert "research" in capabilities
        assert "tool_use" in capabilities

    def test_manager_capabilities(self):
        """Manager may have reasoning but not necessarily coding capabilities."""
        skills = {"coding": 40, "reasoning": 75, "research": 60, "tool_use": 45}
        capabilities = get_worker_capabilities(skills)

        assert "coding" not in capabilities
        assert "reasoning" in capabilities
        assert "research" in capabilities
        assert "tool_use" in capabilities
