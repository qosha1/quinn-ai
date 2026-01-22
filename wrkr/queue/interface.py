"""
Queue interface protocol and mock implementation for testing.

Defines the contract that all queue implementations must follow.
The QueueInterface Protocol ensures consistent behavior across
different queue backends (in-memory, SQLite, Redis, etc.).
"""

from typing import Protocol

from ..core.task import Task


class QueueInterface(Protocol):
    """
    Protocol defining the queue interface contract.

    All queue implementations must provide these methods with
    consistent behavior. Tasks are ordered by priority (lower = higher priority).
    """

    def pop_highest_priority(self) -> Task | None:
        """
        Pop and return the highest priority task from the queue.

        Tasks with lower priority numbers are considered higher priority.
        If multiple tasks have the same priority, implementation defines order.

        Returns:
            The highest priority task, or None if queue is empty.
        """
        ...

    def push(self, task: Task) -> None:
        """
        Add a task to the queue.

        The task will be inserted based on its priority level.

        Args:
            task: The task to add to the queue.
        """
        ...

    def peek(self, limit: int = 10) -> list[Task]:
        """
        View tasks without removing them from the queue.

        Returns tasks in priority order (highest priority first).

        Args:
            limit: Maximum number of tasks to return. Defaults to 10.

        Returns:
            List of tasks, up to the specified limit.
        """
        ...

    def mark_done(self, task_id: str) -> None:
        """
        Mark a task as completed.

        The task is removed from the active queue and recorded as done.

        Args:
            task_id: Unique identifier of the task to mark done.
        """
        ...

    def mark_blocked(self, task_id: str, reason: str) -> None:
        """
        Mark a task as blocked.

        Blocked tasks are temporarily removed from the active queue
        until the blocking condition is resolved.

        Args:
            task_id: Unique identifier of the task to mark blocked.
            reason: Description of why the task is blocked.
        """
        ...

    def mark_failed(self, task_id: str, error: str) -> None:
        """
        Mark a task as permanently failed.

        Failed tasks will not be retried and are recorded with the error.

        Args:
            task_id: Unique identifier of the task to mark failed.
            error: Description of the failure.
        """
        ...

    def requeue(self, task_id: str) -> None:
        """
        Return a task to the queue for retry.

        Used for tasks that failed temporarily and should be retried.

        Args:
            task_id: Unique identifier of the task to requeue.
        """
        ...

    def size(self) -> int:
        """
        Get the number of tasks currently in the queue.

        Returns:
            Number of tasks in the queue.
        """
        ...


class MockQueue:
    """
    In-memory queue implementation for testing.

    Stores tasks in a list, sorted by priority. Provides tracking
    of done, blocked, and failed tasks for test assertions.
    """

    def __init__(self) -> None:
        """Initialize empty queue and tracking collections."""
        self._tasks: list[Task] = []
        self._in_progress: dict[str, Task] = {}
        self._done: dict[str, Task] = {}
        self._blocked: dict[str, tuple[Task, str]] = {}
        self._failed: dict[str, tuple[Task, str]] = {}

    def pop_highest_priority(self) -> Task | None:
        """
        Pop and return the highest priority task.

        The task is moved to in-progress tracking until marked done/blocked/failed.

        Returns:
            The highest priority task, or None if queue is empty.
        """
        if not self._tasks:
            return None
        task = self._tasks.pop(0)
        self._in_progress[task.id] = task
        return task

    def push(self, task: Task) -> None:
        """
        Add a task to the queue in priority order.

        Args:
            task: The task to add.
        """
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: t.priority)

    def peek(self, limit: int = 10) -> list[Task]:
        """
        View tasks without removing them.

        Args:
            limit: Maximum number of tasks to return.

        Returns:
            List of tasks up to the limit.
        """
        return self._tasks[:limit]

    def mark_done(self, task_id: str) -> None:
        """
        Mark a task as completed.

        Args:
            task_id: ID of the task to mark done.
        """
        # Check in-progress tasks first (typical case after pop)
        if task_id in self._in_progress:
            self._done[task_id] = self._in_progress.pop(task_id)
            return
        # Also check queued tasks (for flexibility)
        for i, task in enumerate(self._tasks):
            if task.id == task_id:
                self._done[task_id] = self._tasks.pop(i)
                return

    def mark_blocked(self, task_id: str, reason: str) -> None:
        """
        Mark a task as blocked.

        Args:
            task_id: ID of the task to mark blocked.
            reason: Why the task is blocked.
        """
        # Check in-progress tasks first (typical case after pop)
        if task_id in self._in_progress:
            self._blocked[task_id] = (self._in_progress.pop(task_id), reason)
            return
        # Also check queued tasks (for flexibility)
        for i, task in enumerate(self._tasks):
            if task.id == task_id:
                self._blocked[task_id] = (self._tasks.pop(i), reason)
                return

    def mark_failed(self, task_id: str, error: str) -> None:
        """
        Mark a task as permanently failed.

        Args:
            task_id: ID of the task to mark failed.
            error: The error description.
        """
        # Check in-progress tasks first (typical case after pop)
        if task_id in self._in_progress:
            self._failed[task_id] = (self._in_progress.pop(task_id), error)
            return
        # Also check queued tasks (for flexibility)
        for i, task in enumerate(self._tasks):
            if task.id == task_id:
                self._failed[task_id] = (self._tasks.pop(i), error)
                return

    def requeue(self, task_id: str) -> None:
        """
        Return a blocked or failed task to the queue.

        Args:
            task_id: ID of the task to requeue.
        """
        if task_id in self._blocked:
            task, _ = self._blocked.pop(task_id)
            self.push(task)
        elif task_id in self._failed:
            task, _ = self._failed.pop(task_id)
            self.push(task)

    def size(self) -> int:
        """
        Get queue size.

        Returns:
            Number of tasks in the queue.
        """
        return len(self._tasks)
