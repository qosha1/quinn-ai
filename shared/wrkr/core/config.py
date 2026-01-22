"""Worker configuration for QuinnAI agents.

Defines the WorkerConfig dataclass that captures worker identity,
capabilities (skills), cost tier, and organizational hierarchy.

This module provides a WorkerConfig tailored for the worker execution layer.
It uses different field names and behaviors optimized for the state machine:
- boss_id instead of manager_id (execution context)
- idle_behavior and poll_interval for runtime behavior
- tier property with "cheap/mid/top" naming

For the canonical organizational types, see shared.core.worker.
"""

from dataclasses import dataclass, field
from typing import Literal

# Re-export canonical types for discoverability
from shared.core.worker import (
    WorkerConfig as CoreWorkerConfig,
    WorkerInfo,
    WorkerResult as CoreWorkerResult,
    WorkerNode,
)


@dataclass
class WorkerConfig:
    """Configuration for a QuinnAI worker agent.

    Workers have skills (rated 0-100), a cost tier, and belong to
    an organizational hierarchy with optional manager relationships.

    Note: This is the execution-layer config. For the organizational-layer
    config with team_id, hiring_authority, etc., see shared.core.worker.WorkerConfig.

    Attributes:
        id: Unique identifier for this worker.
        name: Human-readable name for the worker.
        skills: Mapping of skill names to proficiency scores (0-100).
            Expected keys: coding, reasoning, research, management, strategy, creative.
        cost: Relative cost score (0-100).
            - 0-30: cheap tier
            - 31-60: mid tier
            - 61-100: top tier
        role_id: Identifier for the worker's role/position.
        boss_id: ID of the worker's manager. None means reports to human/board.
        is_manager: Whether this worker manages other workers.
        idle_behavior: What to do when no work is available.
            - "wait": Block until work arrives
            - "poll": Periodically check for work
            - "exit": Shut down when idle
        poll_interval: Seconds between polls when idle_behavior is "poll".
    """

    id: str
    name: str
    skills: dict[str, int] = field(default_factory=dict)
    cost: int = 50
    role_id: str = ""
    boss_id: str | None = None
    is_manager: bool = False
    idle_behavior: Literal["wait", "poll", "exit"] = "poll"
    poll_interval: float = 5.0

    @property
    def reports_to_human(self) -> bool:
        """True if this worker reports directly to human/board (no boss)."""
        return self.boss_id is None

    @property
    def tier(self) -> str:
        """Cost tier based on the cost score.

        Returns:
            "cheap" for cost 0-30
            "mid" for cost 31-60
            "top" for cost 61-100
        """
        if self.cost <= 30:
            return "cheap"
        elif self.cost <= 60:
            return "mid"
        else:
            return "top"

    def get_skill(self, name: str) -> int:
        """Get the proficiency score for a skill.

        Args:
            name: The skill name to look up.

        Returns:
            The skill score (0-100), or 0 if the skill is not defined.
        """
        return self.skills.get(name, 0)

    def has_capability(self, skill: str, min_level: int = 50) -> bool:
        """Check if the worker has a skill at or above a minimum level.

        Args:
            skill: The skill name to check.
            min_level: Minimum required proficiency (default 50).

        Returns:
            True if the worker has the skill at or above min_level.
        """
        return self.get_skill(skill) >= min_level


# Aliases for type compatibility between layers
__all__ = [
    "WorkerConfig",
    "CoreWorkerConfig",
    "WorkerInfo",
    "CoreWorkerResult",
    "WorkerNode",
]
