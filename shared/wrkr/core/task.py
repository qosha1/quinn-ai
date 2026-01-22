"""
Task dataclass representing a unit of work in the worker system.

Tasks are the fundamental work units that workers process. They can originate
from various sources (queue, beads, escalations, or asks) and may have
dependencies on other tasks.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


SourceType = Literal["queue", "beads", "escalation", "ask"]


@dataclass
class Task:
    """
    A unit of work to be processed by a worker.

    Attributes:
        id: Unique identifier for this task.
        title: Short descriptive title of the task.
        description: Detailed description of what needs to be done.
        priority: Priority level from 0-4, where lower numbers indicate
            higher priority. Default is 2 (normal priority).
        source: Origin of the task. One of:
            - "queue": Standard queue-based task
            - "beads": Task from the beads planning system
            - "escalation": Task escalated from another worker
            - "ask": Task spawned from an ask/question
        blocked_by: List of task IDs that must complete before this task
            can be processed.
        metadata: Arbitrary key-value data associated with the task.
        created_at: Timestamp when the task was created.
        ask_id: Optional ID of the ask that spawned this task
            (QuinnAI: spawned-from relationship).
        okr_id: Optional ID of the OKR this task serves
            (QuinnAI: serves relationship).
    """

    id: str
    title: str
    description: str
    priority: int = 2
    source: SourceType = "queue"
    blocked_by: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    ask_id: str | None = None
    okr_id: str | None = None

    def __post_init__(self) -> None:
        """Validate task fields after initialization."""
        if not 0 <= self.priority <= 4:
            raise ValueError(f"Priority must be between 0 and 4, got {self.priority}")

    def is_blocked(self) -> bool:
        """
        Check if this task is blocked by dependencies.

        Returns:
            True if the task has unresolved dependencies, False otherwise.
        """
        return len(self.blocked_by) > 0
