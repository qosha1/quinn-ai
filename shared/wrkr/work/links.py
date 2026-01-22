"""
Ask/OKR linking for wrkr-beads integration.

Handles the work dimension relationships:
- Task.ask_id → spawned-from dependency (source Ask)
- Task.okr_id → serves dependency (strategic OKR alignment)

These links enable:
- Tracing work back to original requests (Asks)
- Measuring progress toward strategic goals (OKRs)
- Dependency tracking and reporting
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.bd import BdClient

logger = logging.getLogger(__name__)


@dataclass
class WorkLink:
    """
    A link between work items in the beads system.

    Represents a dependency relationship between issues.

    Attributes:
        source_id: The issue that has the dependency.
        target_id: The issue being depended on.
        link_type: Type of dependency (spawned-from, serves, etc.).
        metadata: Additional link metadata.
        created_at: When the link was created.
    """

    source_id: str
    target_id: str
    link_type: Literal[
        "spawned-from",  # Work spawned from an Ask
        "serves",        # Work serves an OKR
        "depends-on",    # Blocking dependency
        "relates-to",    # Non-blocking relationship
        "caused-by",     # Triggered by (audit trail)
    ]
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "link_type": self.link_type,
            "metadata": self.metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class Ask:
    """
    An Ask represents a request/question that spawned work.

    Asks are the "who requested, what, why" dimension of work.
    Tasks link to Asks via spawned-from dependency.

    Attributes:
        id: Ask ID (beads issue ID).
        title: What was asked.
        requester: Who asked.
        status: Current status (open, closed).
        spawned_tasks: IDs of tasks spawned from this ask.
        created_at: When the ask was created.
    """

    id: str
    title: str
    requester: str | None = None
    status: str = "open"
    spawned_tasks: list[str] | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "requester": self.requester,
            "status": self.status,
            "spawned_tasks": self.spawned_tasks or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class OKR:
    """
    An OKR represents a strategic objective and its key results.

    Tasks link to OKRs via serves dependency to track strategic alignment.

    Attributes:
        id: OKR ID (beads issue ID).
        objective: The objective statement.
        key_results: Measurable key results.
        progress: Current progress (0.0 to 1.0).
        status: Current status.
        serving_tasks: IDs of tasks serving this OKR.
        created_at: When the OKR was created.
    """

    id: str
    objective: str
    key_results: list[str] | None = None
    progress: float = 0.0
    status: str = "open"
    serving_tasks: list[str] | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "objective": self.objective,
            "key_results": self.key_results or [],
            "progress": self.progress,
            "status": self.status,
            "serving_tasks": self.serving_tasks or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LinkManager:
    """
    Manages work links (Ask/OKR relationships) in beads.

    Provides methods to:
    - Create links between work items
    - Query links for a given task
    - Retrieve Ask/OKR details
    - Calculate OKR progress
    """

    def __init__(
        self,
        bd_command: str = "bd",
        db_path: str | None = None,
        client: "BdClient | None" = None,
    ):
        """
        Initialize the link manager.

        Args:
            bd_command: Path to the bd command.
            db_path: Optional database path override.
            client: Optional BdClient instance (for dependency injection).
        """
        # Lazy import to avoid circular dependency
        from shared.bd import BdClient
        from shared.wrkr.work.types import BeadsDependency, BeadsType

        self._client = client or BdClient(bd_command=bd_command, db_path=db_path)
        self._BeadsDependency = BeadsDependency
        self._BeadsType = BeadsType

    def link_to_ask(self, task_id: str, ask_id: str) -> WorkLink:
        """
        Link a task to its source Ask.

        Creates a spawned-from dependency.

        Args:
            task_id: The task being linked.
            ask_id: The Ask that spawned this task.

        Returns:
            The created WorkLink.
        """
        if not self._client.add_dependency(
            task_id, ask_id, dep_type=self._BeadsDependency.SPAWNED_FROM
        ):
            logger.warning("Failed to link task %s to ask %s", task_id, ask_id)

        return WorkLink(
            source_id=task_id,
            target_id=ask_id,
            link_type="spawned-from",
            created_at=datetime.now(),
        )

    def link_to_okr(self, task_id: str, okr_id: str) -> WorkLink:
        """
        Link a task to its serving OKR.

        Creates a serves dependency.

        Args:
            task_id: The task being linked.
            okr_id: The OKR this task serves.

        Returns:
            The created WorkLink.
        """
        if not self._client.add_dependency(
            task_id, okr_id, dep_type=self._BeadsDependency.SERVES
        ):
            logger.warning("Failed to link task %s to okr %s", task_id, okr_id)

        return WorkLink(
            source_id=task_id,
            target_id=okr_id,
            link_type="serves",
            created_at=datetime.now(),
        )

    def get_ask(self, ask_id: str) -> Ask | None:
        """
        Retrieve an Ask by ID.

        Args:
            ask_id: The Ask ID to retrieve.

        Returns:
            The Ask, or None if not found.
        """
        data = self._client.get_issue(ask_id)
        if not data:
            return None

        if data.get("type") != self._BeadsType.ASK:
            return None

        # Get spawned tasks
        spawned = []
        spawned_issues = self._client.list_issues(spawned_from=ask_id)
        spawned = [d["id"] for d in spawned_issues]

        return Ask(
            id=data["id"],
            title=data.get("title", ""),
            requester=data.get("metadata", {}).get("requester"),
            status=data.get("status", "open"),
            spawned_tasks=spawned,
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
        )

    def get_okr(self, okr_id: str) -> OKR | None:
        """
        Retrieve an OKR by ID.

        Args:
            okr_id: The OKR ID to retrieve.

        Returns:
            The OKR, or None if not found.
        """
        data = self._client.get_issue(okr_id)
        if not data:
            return None

        if data.get("type") != self._BeadsType.OKR:
            return None

        metadata = data.get("metadata", {})

        # Get serving tasks
        serving_issues = self._client.list_issues(serves=okr_id)
        serving = [d["id"] for d in serving_issues]

        return OKR(
            id=data["id"],
            objective=data.get("title", ""),
            key_results=metadata.get("key_results", []),
            progress=metadata.get("progress", 0.0),
            status=data.get("status", "open"),
            serving_tasks=serving,
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
        )

    def get_task_ask(self, task_id: str) -> Ask | None:
        """
        Get the Ask that spawned a task.

        Args:
            task_id: The task ID.

        Returns:
            The source Ask, or None if not linked.
        """
        data = self._client.get_issue(task_id)
        if not data:
            return None

        ask_id = data.get("spawned_from") or data.get("ask_id")
        if not ask_id:
            return None

        return self.get_ask(ask_id)

    def get_task_okr(self, task_id: str) -> OKR | None:
        """
        Get the OKR a task serves.

        Args:
            task_id: The task ID.

        Returns:
            The served OKR, or None if not linked.
        """
        data = self._client.get_issue(task_id)
        if not data:
            return None

        okr_id = data.get("serves") or data.get("okr_id")
        if not okr_id:
            return None

        return self.get_okr(okr_id)

    def calculate_okr_progress(self, okr_id: str) -> float:
        """
        Calculate OKR progress based on completed serving tasks.

        Args:
            okr_id: The OKR ID.

        Returns:
            Progress as float (0.0 to 1.0).
        """
        from shared.wrkr.work.types import BeadsStatus

        okr = self.get_okr(okr_id)
        if not okr or not okr.serving_tasks:
            return 0.0

        completed = 0
        total = len(okr.serving_tasks)

        for task_id in okr.serving_tasks:
            data = self._client.get_issue(task_id)
            if data and data.get("status") == BeadsStatus.CLOSED:
                completed += 1

        return completed / total if total > 0 else 0.0

    def update_okr_progress(self, okr_id: str) -> float:
        """
        Calculate and update OKR progress in beads.

        Args:
            okr_id: The OKR ID to update.

        Returns:
            The new progress value.
        """
        progress = self.calculate_okr_progress(okr_id)

        if not self._client.update_issue(okr_id, metadata={"progress": progress}):
            logger.warning("Failed to update OKR progress for %s", okr_id)

        return progress


class InMemoryLinkManager:
    """
    In-memory mock of LinkManager for testing.
    """

    def __init__(self):
        """Initialize the mock link manager."""
        self._links: list[WorkLink] = []
        self._asks: dict[str, Ask] = {}
        self._okrs: dict[str, OKR] = {}
        self._task_status: dict[str, str] = {}

    def add_ask(self, ask: Ask) -> None:
        """Add an Ask to the store."""
        self._asks[ask.id] = ask

    def add_okr(self, okr: OKR) -> None:
        """Add an OKR to the store."""
        self._okrs[okr.id] = okr

    def set_task_status(self, task_id: str, status: str) -> None:
        """Set a task's status for progress calculation."""
        self._task_status[task_id] = status

    def link_to_ask(self, task_id: str, ask_id: str) -> WorkLink:
        """Link a task to an Ask."""
        link = WorkLink(
            source_id=task_id,
            target_id=ask_id,
            link_type="spawned-from",
            created_at=datetime.now(),
        )
        self._links.append(link)

        # Update ask's spawned_tasks
        if ask_id in self._asks:
            ask = self._asks[ask_id]
            if ask.spawned_tasks is None:
                ask.spawned_tasks = []
            if task_id not in ask.spawned_tasks:
                ask.spawned_tasks.append(task_id)

        return link

    def link_to_okr(self, task_id: str, okr_id: str) -> WorkLink:
        """Link a task to an OKR."""
        link = WorkLink(
            source_id=task_id,
            target_id=okr_id,
            link_type="serves",
            created_at=datetime.now(),
        )
        self._links.append(link)

        # Update OKR's serving_tasks
        if okr_id in self._okrs:
            okr = self._okrs[okr_id]
            if okr.serving_tasks is None:
                okr.serving_tasks = []
            if task_id not in okr.serving_tasks:
                okr.serving_tasks.append(task_id)

        return link

    def get_ask(self, ask_id: str) -> Ask | None:
        """Get an Ask by ID."""
        return self._asks.get(ask_id)

    def get_okr(self, okr_id: str) -> OKR | None:
        """Get an OKR by ID."""
        return self._okrs.get(okr_id)

    def get_task_ask(self, task_id: str) -> Ask | None:
        """Get the Ask that spawned a task."""
        for link in self._links:
            if link.source_id == task_id and link.link_type == "spawned-from":
                return self.get_ask(link.target_id)
        return None

    def get_task_okr(self, task_id: str) -> OKR | None:
        """Get the OKR a task serves."""
        for link in self._links:
            if link.source_id == task_id and link.link_type == "serves":
                return self.get_okr(link.target_id)
        return None

    def calculate_okr_progress(self, okr_id: str) -> float:
        """Calculate OKR progress."""
        okr = self.get_okr(okr_id)
        if not okr or not okr.serving_tasks:
            return 0.0

        completed = sum(
            1 for task_id in okr.serving_tasks
            if self._task_status.get(task_id) == "closed"
        )

        return completed / len(okr.serving_tasks)

    def update_okr_progress(self, okr_id: str) -> float:
        """Calculate and store OKR progress."""
        progress = self.calculate_okr_progress(okr_id)
        if okr_id in self._okrs:
            self._okrs[okr_id].progress = progress
        return progress
