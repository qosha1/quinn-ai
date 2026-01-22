"""
Canonical worker types for QuinnAI.

Per CLAUDE.md: "Every Agent Is A Worker. CEO, manager, junior - same base unit.
Differ by role, team, hierarchy, authority. No special classes for 'important' agents."

This module provides the canonical worker-related types:
    - WorkerConfig: Static configuration for a worker
    - WorkerInfo: Runtime information about a worker
    - WorkerResult: Result from a worker operation

The WorkerState enum is in shared/core/state.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# =============================================================================
# Worker Configuration
# =============================================================================


@dataclass
class WorkerConfig:
    """Static configuration for a worker.

    Per CLAUDE.md: "Code = Physics, Config = Behavior"
    This is the behavioral configuration - what makes this worker unique.
    """

    # Identity
    id: str
    """Unique worker identifier."""

    name: str
    """Human-readable worker name."""

    role: str
    """Worker's role (e.g., 'engineer', 'manager', 'ceo')."""

    # Organization
    team_id: str
    """Team this worker belongs to."""

    manager_id: Optional[str] = None
    """Manager's worker ID (None for CEO)."""

    # Skills & Cost (per CLAUDE.md principle)
    skills: dict[str, int] = field(default_factory=dict)
    """Skills mapped to scores 0-100 (e.g., {'coding': 80, 'research': 60})."""

    cost: int = 50
    """Cost score 0-100 (maps to model tier: 0-30=budget, 31-60=standard, etc.)."""

    # Authority
    hiring_authority: bool = False
    """Whether this worker can hire other workers."""

    budget_authority: float = 0.0
    """Budget this worker can allocate to reports."""

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional configuration metadata."""

    @property
    def cost_tier(self) -> str:
        """Map cost score to tier name."""
        if self.cost <= 30:
            return "budget"
        elif self.cost <= 60:
            return "standard"
        elif self.cost <= 80:
            return "advanced"
        else:
            return "premium"

    def has_skill(self, skill: str, min_level: int = 1) -> bool:
        """Check if worker has a skill at minimum level."""
        return self.skills.get(skill, 0) >= min_level

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "team_id": self.team_id,
            "manager_id": self.manager_id,
            "skills": self.skills,
            "cost": self.cost,
            "cost_tier": self.cost_tier,
            "hiring_authority": self.hiring_authority,
            "budget_authority": self.budget_authority,
            "metadata": self.metadata,
        }


# =============================================================================
# Worker Runtime Info
# =============================================================================


@dataclass
class WorkerInfo:
    """Runtime information about a worker.

    Combines static config with runtime state for display/queries.
    This is what you get from get_worker() queries.
    """

    # From config
    id: str
    name: str
    role: str
    team_id: str
    manager_id: Optional[str]
    skills: dict[str, int]
    cost: int

    # Runtime state
    status: str
    """Current status (WorkerState.value)."""

    created_at: datetime
    """When worker was created."""

    updated_at: datetime
    """When worker was last updated."""

    # Session info
    session_id: Optional[str] = None
    """Current session ID if active."""

    current_task_id: Optional[str] = None
    """Current task being worked on."""

    # Metrics
    tasks_completed: int = 0
    """Total tasks completed."""

    tasks_failed: int = 0
    """Total tasks failed."""

    last_activity: Optional[datetime] = None
    """Last activity timestamp."""

    @property
    def cost_tier(self) -> str:
        """Map cost score to tier name."""
        if self.cost <= 30:
            return "budget"
        elif self.cost <= 60:
            return "standard"
        elif self.cost <= 80:
            return "advanced"
        else:
            return "premium"

    @property
    def is_active(self) -> bool:
        """Whether worker is in an active state."""
        return self.status in ("active", "working")

    @property
    def is_available(self) -> bool:
        """Whether worker is available for new work."""
        return self.status == "active" and self.current_task_id is None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "team_id": self.team_id,
            "manager_id": self.manager_id,
            "skills": self.skills,
            "cost": self.cost,
            "cost_tier": self.cost_tier,
            "status": self.status,
            "session_id": self.session_id,
            "current_task_id": self.current_task_id,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# =============================================================================
# Worker Result
# =============================================================================


@dataclass
class WorkerResult:
    """Result from a worker operation.

    Standard result type for operations that workers perform.
    """

    success: bool
    """Whether operation succeeded."""

    worker_id: str
    """Worker that performed the operation."""

    operation: str
    """Operation name (e.g., 'task_complete', 'escalation')."""

    # Result data
    data: dict[str, Any] = field(default_factory=dict)
    """Operation-specific result data."""

    error: Optional[str] = None
    """Error message if failed."""

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    """When operation started."""

    completed_at: Optional[datetime] = None
    """When operation completed."""

    # Resource usage
    tokens_used: int = 0
    """Tokens consumed by this operation."""

    cost: float = 0.0
    """Cost in dollars for this operation."""

    @property
    def duration_ms(self) -> int | None:
        """Duration in milliseconds."""
        if not self.completed_at:
            return None
        return int((self.completed_at - self.started_at).total_seconds() * 1000)

    def complete(self, data: dict[str, Any] | None = None) -> WorkerResult:
        """Mark result as complete with success."""
        self.success = True
        self.completed_at = datetime.now()
        if data:
            self.data.update(data)
        return self

    def fail(self, error: str) -> WorkerResult:
        """Mark result as failed with error."""
        self.success = False
        self.error = error
        self.completed_at = datetime.now()
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "worker_id": self.worker_id,
            "operation": self.operation,
            "data": self.data,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
        }


# =============================================================================
# Worker Node (for org chart traversal)
# =============================================================================


@dataclass
class WorkerNode:
    """Worker in an organizational hierarchy.

    Used for org-chart traversal and hierarchical operations.
    """

    worker_id: str
    """Worker ID."""

    name: str
    """Worker name."""

    role: str
    """Worker role."""

    manager_id: Optional[str] = None
    """Manager's worker ID."""

    direct_reports: list[str] = field(default_factory=list)
    """IDs of direct reports."""

    team_id: str = ""
    """Team ID."""

    depth: int = 0
    """Depth in hierarchy (0 = CEO)."""

    @property
    def is_manager(self) -> bool:
        """Whether this worker manages others."""
        return len(self.direct_reports) > 0

    @property
    def is_ceo(self) -> bool:
        """Whether this is the CEO (no manager)."""
        return self.manager_id is None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "role": self.role,
            "manager_id": self.manager_id,
            "direct_reports": self.direct_reports,
            "team_id": self.team_id,
            "depth": self.depth,
            "is_manager": self.is_manager,
            "is_ceo": self.is_ceo,
        }
