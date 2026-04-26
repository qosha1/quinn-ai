"""
Base classes, exceptions, and helpers for provider selection.

This module contains:
- Exceptions for provider selection failures
- Data classes for selection results
- Helper functions for tier mapping and capability derivation
"""

from dataclasses import dataclass
from typing import Optional

from cli.core.constants import (
    COST_TIER_BUDGET_MAX,
    COST_TIER_STANDARD_MAX,
    COST_TIER_ADVANCED_MAX,
    DEFAULT_SKILL_THRESHOLDS,
)

from cli.providers.base import (
    CostTier,
    ModelInfo,
    Provider,
)


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
