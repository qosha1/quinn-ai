"""
Dataclasses for QuinnAI configuration.

All configuration structures are defined here. No I/O or validation logic.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cli.core.constants import (
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
    DEFAULT_SKILL_THRESHOLD_CODING,
    DEFAULT_SKILL_THRESHOLD_REASONING,
    DEFAULT_SKILL_THRESHOLD_RESEARCH,
    DEFAULT_WORKER_COST,
    COST_PER_1K_TOKENS_BUDGET,
    COST_PER_1K_TOKENS_STANDARD,
    COST_PER_1K_TOKENS_ADVANCED,
    COST_PER_1K_TOKENS_PREMIUM,
    DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
    DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
)


class PlaintextApiKeyWarning(UserWarning):
    """Warning raised when a plaintext API key is detected in config."""
    pass


@dataclass
class ProviderSettings:
    """Settings for a single provider."""
    enabled: bool = True
    api_key: str = ""
    base_url: Optional[str] = None
    timeout: int = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES


@dataclass
class ThresholdSettings:
    """Skill thresholds for capability requirements."""
    coding: int = DEFAULT_SKILL_THRESHOLD_CODING
    reasoning: int = DEFAULT_SKILL_THRESHOLD_REASONING
    research: int = DEFAULT_SKILL_THRESHOLD_RESEARCH


@dataclass
class ProvidersConfig:
    """Configuration from providers.yaml."""
    default: str = "anthropic"
    authorized_providers: list[str] = field(default_factory=list)
    providers: dict[str, ProviderSettings] = field(default_factory=dict)
    thresholds: ThresholdSettings = field(default_factory=ThresholdSettings)


@dataclass
class WorkerTemplate:
    """Template defining skills and cost for a worker role."""
    description: str = ""
    skills: dict[str, int] = field(default_factory=dict)
    cost: int = DEFAULT_WORKER_COST


@dataclass
class WorkerTemplatesConfig:
    """Configuration from worker-templates.yaml."""
    templates: dict[str, WorkerTemplate] = field(default_factory=dict)

    def get_template(self, role: str) -> Optional["WorkerTemplate"]:
        """Get template for a role.

        Performs case-insensitive matching and normalizes role names
        (e.g., 'CEO' -> 'ceo', 'Senior Engineer' -> 'senior_engineer').

        Args:
            role: Role name to look up

        Returns:
            WorkerTemplate if found, None otherwise
        """
        normalized = role.lower().replace(" ", "_").replace("-", "_")
        return self.templates.get(normalized)

    def get_skills_and_cost(
        self,
        role: str,
        skill_overrides: Optional[dict[str, int]] = None,
        cost_override: Optional[int] = None,
    ) -> tuple[dict[str, int], int]:
        """Get skills and cost for a role from template with optional overrides.

        Args:
            role: Role name to look up
            skill_overrides: Optional skill values to override template
            cost_override: Optional cost to override template

        Returns:
            Tuple of (skills dict, cost int)

        Raises:
            KeyError: If role template not found
        """
        template = self.get_template(role)
        if template is None:
            raise KeyError(f"No template found for role: {role}")

        skills = dict(template.skills)
        cost = template.cost

        if skill_overrides:
            skills.update(skill_overrides)
        if cost_override is not None:
            cost = cost_override

        return skills, cost


@dataclass
class TierTokenCosts:
    """Token costs for a single tier (per 1K tokens in USD)."""

    input: float
    output: float

    def to_dict(self) -> dict[str, float]:
        """Convert to dict format for budget calculations."""
        return {"input": self.input, "output": self.output}


@dataclass
class BudgetConfig:
    """Configuration for budget and cost estimation.

    All values are injectable via config. Falls back to constants when not set.
    """

    tier_costs: dict[str, TierTokenCosts] = field(default_factory=dict)
    session_spawn_tokens_input: int = DEFAULT_SESSION_SPAWN_TOKENS_INPUT
    session_spawn_tokens_output: int = DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT

    def get_tier_costs(self, tier: str) -> dict[str, float]:
        """Get token costs for a tier, falling back to defaults.

        Args:
            tier: Cost tier name ('budget', 'standard', 'advanced', 'premium')

        Returns:
            Dict with 'input' and 'output' costs per 1K tokens
        """
        tier_lower = tier.lower()
        if tier_lower in self.tier_costs:
            return self.tier_costs[tier_lower].to_dict()

        defaults = {
            "budget": COST_PER_1K_TOKENS_BUDGET,
            "standard": COST_PER_1K_TOKENS_STANDARD,
            "advanced": COST_PER_1K_TOKENS_ADVANCED,
            "premium": COST_PER_1K_TOKENS_PREMIUM,
        }
        return defaults.get(tier_lower, defaults["standard"])

    @classmethod
    def default(cls) -> "BudgetConfig":
        """Create BudgetConfig with all default values from constants."""
        return cls(
            tier_costs={
                "budget": TierTokenCosts(**COST_PER_1K_TOKENS_BUDGET),
                "standard": TierTokenCosts(**COST_PER_1K_TOKENS_STANDARD),
                "advanced": TierTokenCosts(**COST_PER_1K_TOKENS_ADVANCED),
                "premium": TierTokenCosts(**COST_PER_1K_TOKENS_PREMIUM),
            },
            session_spawn_tokens_input=DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
            session_spawn_tokens_output=DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
        )


@dataclass
class AutoAssignConfig:
    """Configuration for automatic work assignment."""
    enabled: bool = True
    match_skills: bool = True
    prefer_least_loaded: bool = True
    strategy: str = "least_loaded"  # least_loaded | round_robin | skill_match


@dataclass
class OKRLinkingConfig:
    """Configuration for OKR linking requirements."""
    require_okr_link: bool = True
    strict_mode: bool = False


@dataclass
class WorkflowConfig:
    """Configuration for work lifecycle and automation.

    Loaded from workflow.yaml. Defines valid states, transitions,
    and automation rules for work items.
    """
    work_states: list[str] = field(default_factory=lambda: [
        "draft", "open", "in_progress", "review", "blocked", "closed"
    ])
    transitions: dict[str, list[str]] = field(default_factory=dict)
    terminal_states: list[str] = field(default_factory=lambda: ["closed"])

    okr_linking: OKRLinkingConfig = field(default_factory=OKRLinkingConfig)
    auto_assign: AutoAssignConfig = field(default_factory=AutoAssignConfig)

    def is_valid_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a state transition is valid.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if transition is allowed
        """
        allowed = self.transitions.get(from_state, [])
        return to_state in allowed

    def is_terminal(self, state: str) -> bool:
        """Check if a state is terminal (no further transitions)."""
        return state in self.terminal_states

    @classmethod
    def default(cls) -> "WorkflowConfig":
        """Create default workflow config."""
        return cls(
            transitions={
                "draft": ["open", "closed"],
                "open": ["in_progress", "blocked", "closed"],
                "in_progress": ["review", "blocked", "closed"],
                "review": ["in_progress", "closed"],
                "blocked": ["open", "in_progress", "closed"],
                "closed": [],
            }
        )


@dataclass
class OrgConfig:
    """Complete configuration for an organization.

    Created by loading from explicit config directory path.
    """

    providers: ProvidersConfig
    worker_templates: WorkerTemplatesConfig
    budget: BudgetConfig
    workflow: WorkflowConfig
    config_path: Path
