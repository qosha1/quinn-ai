"""
BeadsQueue: Queue implementation that sources tasks from beads.

Implements QueueInterface using beads as the backing store.
Tasks are fetched as assigned issues, filtered by status,
and ordered by priority.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from shared.bd import BdClient, BdCommandError
from shared.wrkr.work.types import BeadsStatus, BeadsType
from shared.wrkr.core.task import Task

logger = logging.getLogger(__name__)


class BeadsQueue:
    """
    Queue implementation backed by beads issue tracking.

    Tasks are beads issues assigned to the worker. The queue:
    - Fetches open issues assigned to the worker
    - Filters by type (task, bug, feature, etc.)
    - Orders by priority (P0 highest, P4 lowest)
    - Marks issues done/blocked via bd CLI

    This implements QueueInterface for use with BaseWorker.
    """

    def __init__(
        self,
        worker_id: str,
        bd_command: str = "bd",
        db_path: str | None = None,
        task_types: list[str] | None = None,
        client: BdClient | None = None,
    ):
        """
        Initialize the beads queue.

        Args:
            worker_id: The worker ID to fetch tasks for.
            bd_command: Path to the bd command. Defaults to "bd".
            db_path: Optional database path override.
            task_types: Issue types to include as tasks.
                Defaults to ["task", "bug", "feature"].
            client: Optional BdClient instance (for dependency injection).
        """
        self._worker_id = worker_id
        self._client = client or BdClient(bd_command=bd_command, db_path=db_path)
        self._task_types = task_types or [
            BeadsType.TASK,
            BeadsType.BUG,
            BeadsType.FEATURE,
        ]
        self._in_progress: dict[str, Task] = {}

    @property
    def worker_id(self) -> str:
        """The worker ID this queue serves."""
        return self._worker_id

    def _parse_issue_to_task(self, issue: dict[str, Any]) -> Task:
        """Convert a beads issue to a Task.

        Args:
            issue: Issue data from bd list --json.

        Returns:
            Task instance.
        """
        # Parse priority (P0-P4 -> 0-4)
        priority_str = str(issue.get("priority", "P2"))
        if priority_str.startswith("P"):
            priority = int(priority_str[1])
        else:
            priority = int(priority_str) if priority_str.isdigit() else 2

        # Parse created_at
        created_at_str = issue.get("created_at")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
            except ValueError:
                created_at = datetime.now()
        else:
            created_at = datetime.now()

        # Determine source based on issue type
        issue_type = issue.get("type", "task")
        source_map = {
            "ask": "ask",
            "task": "queue",
            "bug": "queue",
            "feature": "queue",
            "epic": "queue",
        }
        source = source_map.get(issue_type, "beads")

        # Extract blocked_by from dependencies
        blocked_by = []
        for dep in issue.get("dependencies", []):
            if dep.get("type") == "depends-on":
                blocked_by.append(dep.get("target_id", ""))

        return Task(
            id=issue["id"],
            title=issue.get("title", ""),
            description=issue.get("description", ""),
            priority=priority,
            source=source,
            blocked_by=blocked_by,
            metadata={
                "issue_type": issue_type,
                "assignee": issue.get("assignee"),
                "labels": issue.get("labels", []),
                "status": issue.get("status"),
                **issue.get("metadata", {}),
            },
            created_at=created_at,
            ask_id=issue.get("ask_id") or issue.get("spawned_from"),
            okr_id=issue.get("okr_id") or issue.get("serves"),
        )

    def _fetch_issues(self, status: str = "open") -> list[dict[str, Any]]:
        """Fetch issues from beads.

        Args:
            status: Status filter (open, in_progress, closed).

        Returns:
            List of issue dictionaries.
        """
        try:
            issues = self._client.list_issues(
                status=status,
                assignee=self._worker_id,
            )
            # Filter by task types
            return [
                i for i in issues
                if i.get("type", BeadsType.TASK) in self._task_types
            ]
        except BdCommandError as e:
            logger.warning("Failed to fetch issues for %s: %s", self._worker_id, e)
            return []

    def pop_highest_priority(self) -> Task | None:
        """
        Pop and return the highest priority task.

        Fetches open issues from beads, filters to workable tasks
        (not blocked), and returns the highest priority one.

        Returns:
            The highest priority unblocked task, or None if empty.
        """
        issues = self._fetch_issues("open")
        if not issues:
            return None

        # Sort by priority (lower = higher priority)
        issues.sort(key=lambda i: int(str(i.get("priority", "2")).replace("P", "")))

        for issue in issues:
            task = self._parse_issue_to_task(issue)

            # Skip blocked tasks
            if task.is_blocked():
                continue

            # Mark as in progress
            self._in_progress[task.id] = task

            # Update status in beads
            if not self._client.update_issue(task.id, status=BeadsStatus.IN_PROGRESS):
                logger.warning("Failed to update status for task %s", task.id)

            return task

        return None

    def push(self, task: Task) -> None:
        """
        Add a task by creating a beads issue.

        Args:
            task: The task to add.
        """
        kwargs: dict[str, str] = {"assignee": self._worker_id}

        if task.ask_id:
            kwargs["spawned_from"] = task.ask_id
        if task.okr_id:
            kwargs["serves"] = task.okr_id

        issue_id = self._client.create_issue(
            title=task.title,
            type=BeadsType.TASK,
            priority=task.priority,
            description=task.description or None,
            metadata=task.metadata if task.metadata else None,
            **kwargs,
        )
        if not issue_id:
            logger.warning("Failed to create issue for task: %s", task.title)

    def peek(self, limit: int = 10) -> list[Task]:
        """
        View tasks without removing them.

        Args:
            limit: Maximum number of tasks to return.

        Returns:
            List of tasks in priority order.
        """
        issues = self._fetch_issues("open")
        issues.sort(key=lambda i: int(str(i.get("priority", "2")).replace("P", "")))

        tasks = []
        for issue in issues[:limit]:
            task = self._parse_issue_to_task(issue)
            if not task.is_blocked():
                tasks.append(task)

        return tasks

    def mark_done(self, task_id: str) -> None:
        """
        Mark a task as completed by closing the issue.

        Args:
            task_id: ID of the task/issue to close.
        """
        self._in_progress.pop(task_id, None)
        if not self._client.close_issue(task_id, reason="completed"):
            logger.warning("Failed to close task %s", task_id)

    def mark_blocked(self, task_id: str, reason: str) -> None:
        """
        Mark a task as blocked.

        Updates the issue status and adds blocking reason.

        Args:
            task_id: ID of the task to mark blocked.
            reason: Why the task is blocked.
        """
        self._in_progress.pop(task_id, None)
        if not self._client.update_issue(
            task_id,
            status=BeadsStatus.BLOCKED,
            metadata={"blocked_reason": reason},
        ):
            logger.warning("Failed to mark task %s as blocked", task_id)

    def mark_failed(self, task_id: str, error: str) -> None:
        """
        Mark a task as failed.

        Closes the issue with failure status.

        Args:
            task_id: ID of the task to mark failed.
            error: The error description.
        """
        self._in_progress.pop(task_id, None)
        if not self._client.close_issue(task_id, reason=f"failed: {error}"):
            logger.warning("Failed to close task %s as failed", task_id)

    def requeue(self, task_id: str) -> None:
        """
        Return a task to open status for retry.

        Args:
            task_id: ID of the task to requeue.
        """
        if not self._client.update_issue(task_id, status=BeadsStatus.OPEN):
            logger.warning("Failed to requeue task %s", task_id)

    def size(self) -> int:
        """
        Get the number of open tasks assigned to this worker.

        Returns:
            Number of open, unblocked tasks.
        """
        issues = self._fetch_issues("open")
        count = 0
        for issue in issues:
            task = self._parse_issue_to_task(issue)
            if not task.is_blocked():
                count += 1
        return count

    def get_blocked(self) -> list[Task]:
        """
        Get all blocked tasks for this worker.

        Returns:
            List of blocked tasks.
        """
        issues = self._fetch_issues("blocked")
        return [self._parse_issue_to_task(i) for i in issues]

    def get_in_progress(self) -> list[Task]:
        """
        Get all in-progress tasks for this worker.

        Returns:
            List of in-progress tasks.
        """
        issues = self._fetch_issues("in_progress")
        return [self._parse_issue_to_task(i) for i in issues]


class InMemoryBeadsQueue:
    """
    In-memory mock of BeadsQueue for testing.

    Simulates beads behavior without actual bd CLI calls.
    Useful for unit testing workers with beads integration.
    """

    def __init__(self, worker_id: str):
        """Initialize the mock queue.

        Args:
            worker_id: The worker ID this queue serves.
        """
        self._worker_id = worker_id
        self._issues: dict[str, dict[str, Any]] = {}
        self._in_progress: dict[str, Task] = {}

    @property
    def worker_id(self) -> str:
        """The worker ID this queue serves."""
        return self._worker_id

    def add_issue(
        self,
        id: str,
        title: str,
        description: str = "",
        priority: int = 2,
        issue_type: str = "task",
        status: str = "open",
        ask_id: str | None = None,
        okr_id: str | None = None,
        blocked_by: list[str] | None = None,
    ) -> None:
        """Add an issue to the mock store for testing.

        Args:
            id: Issue ID.
            title: Issue title.
            description: Issue description.
            priority: Priority (0-4).
            issue_type: Type of issue.
            status: Status (open, in_progress, blocked, closed).
            ask_id: Optional ask ID.
            okr_id: Optional OKR ID.
            blocked_by: Optional list of blocking issue IDs.
        """
        self._issues[id] = {
            "id": id,
            "title": title,
            "description": description,
            "priority": priority,
            "type": issue_type,
            "status": status,
            "assignee": self._worker_id,
            "ask_id": ask_id,
            "okr_id": okr_id,
            "dependencies": [
                {"type": "depends-on", "target_id": b}
                for b in (blocked_by or [])
            ],
            "created_at": datetime.now().isoformat(),
        }

    def _parse_issue_to_task(self, issue: dict[str, Any]) -> Task:
        """Convert issue dict to Task."""
        blocked_by = [
            d.get("target_id", "")
            for d in issue.get("dependencies", [])
            if d.get("type") == "depends-on"
        ]

        return Task(
            id=issue["id"],
            title=issue.get("title", ""),
            description=issue.get("description", ""),
            priority=issue.get("priority", 2),
            source="beads",
            blocked_by=blocked_by,
            metadata={"issue_type": issue.get("type", "task")},
            ask_id=issue.get("ask_id"),
            okr_id=issue.get("okr_id"),
        )

    def pop_highest_priority(self) -> Task | None:
        """Pop the highest priority open, unblocked task."""
        open_issues = [
            i for i in self._issues.values()
            if i.get("status") == "open"
            and i.get("assignee") == self._worker_id
        ]

        if not open_issues:
            return None

        open_issues.sort(key=lambda i: i.get("priority", 2))

        for issue in open_issues:
            task = self._parse_issue_to_task(issue)
            if not task.is_blocked():
                self._in_progress[task.id] = task
                self._issues[task.id]["status"] = "in_progress"
                return task

        return None

    def push(self, task: Task) -> None:
        """Add a task as an issue."""
        self.add_issue(
            id=task.id,
            title=task.title,
            description=task.description,
            priority=task.priority,
            ask_id=task.ask_id,
            okr_id=task.okr_id,
            blocked_by=task.blocked_by,
        )

    def peek(self, limit: int = 10) -> list[Task]:
        """View tasks without removing them."""
        open_issues = [
            i for i in self._issues.values()
            if i.get("status") == "open"
            and i.get("assignee") == self._worker_id
        ]
        open_issues.sort(key=lambda i: i.get("priority", 2))

        tasks = []
        for issue in open_issues[:limit]:
            task = self._parse_issue_to_task(issue)
            if not task.is_blocked():
                tasks.append(task)

        return tasks

    def mark_done(self, task_id: str) -> None:
        """Mark task as done."""
        self._in_progress.pop(task_id, None)
        if task_id in self._issues:
            self._issues[task_id]["status"] = "closed"

    def mark_blocked(self, task_id: str, reason: str) -> None:
        """Mark task as blocked."""
        self._in_progress.pop(task_id, None)
        if task_id in self._issues:
            self._issues[task_id]["status"] = "blocked"
            self._issues[task_id]["blocked_reason"] = reason

    def mark_failed(self, task_id: str, error: str) -> None:
        """Mark task as failed."""
        self._in_progress.pop(task_id, None)
        if task_id in self._issues:
            self._issues[task_id]["status"] = "closed"
            self._issues[task_id]["failure_reason"] = error

    def requeue(self, task_id: str) -> None:
        """Requeue a task."""
        if task_id in self._issues:
            self._issues[task_id]["status"] = "open"

    def size(self) -> int:
        """Get number of open, unblocked tasks."""
        count = 0
        for issue in self._issues.values():
            if issue.get("status") == "open":
                task = self._parse_issue_to_task(issue)
                if not task.is_blocked():
                    count += 1
        return count
