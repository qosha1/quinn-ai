"""Memory interface protocol for worker task history and context.

This module defines the MemoryInterface Protocol that all memory implementations
must follow. Memory provides workers with access to historical task execution
data, enabling context-aware decision making and pattern recognition.

This is an INTERFACE ONLY - no beads implementation here.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..core.task import Task
from ..core.result import WorkerResult


class MemoryInterface(Protocol):
    """Protocol defining the contract for memory implementations.

    Memory implementations store and retrieve task execution history,
    providing workers with context about past work. This enables:
    - Learning from previous executions
    - Avoiding repeated mistakes
    - Building on successful patterns
    - Contextual awareness for similar tasks

    All memory implementations must provide these four core operations:
    record, recent, get_context, and search.
    """

    def record(self, task: Task, result: WorkerResult) -> None:
        """Record a task execution to memory.

        Stores the task and its execution result for future reference.
        Implementations should capture enough information to reconstruct
        the execution context later.

        Args:
            task: The task that was executed.
            result: The outcome of executing the task.
        """
        ...

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most recent task execution records.

        Returns task execution history in reverse chronological order
        (most recent first).

        Args:
            limit: Maximum number of records to return. Defaults to 10.

        Returns:
            List of task execution records, each containing task and result
            information as a dictionary.
        """
        ...

    def get_context(self, task: Task) -> dict[str, Any]:
        """Get relevant context for a task from memory.

        Analyzes the task and retrieves relevant historical information
        that may help with execution. This could include similar past tasks,
        related outcomes, or learned patterns.

        Args:
            task: The task to get context for.

        Returns:
            Dictionary containing relevant context information. Structure
            is implementation-dependent but should include any helpful
            historical data for the given task.
        """
        ...

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search memory for matching task records.

        Performs a search across stored task history using the provided
        query string. Implementations may use various matching strategies
        (exact, fuzzy, semantic, etc.).

        Args:
            query: Search query string.
            limit: Maximum number of results to return. Defaults to 5.

        Returns:
            List of matching task execution records, ordered by relevance.
        """
        ...


class MockMemory:
    """In-memory implementation of MemoryInterface for testing.

    Stores task execution records in a simple list. Provides basic
    search functionality using substring matching on task titles
    and descriptions.

    This implementation is NOT suitable for production use - it lacks
    persistence, has O(n) search, and stores everything in memory.
    Use only for testing and development.
    """

    def __init__(self) -> None:
        """Initialize an empty mock memory store."""
        self._records: list[dict[str, Any]] = []

    def record(self, task: Task, result: WorkerResult) -> None:
        """Record a task execution to the in-memory store.

        Args:
            task: The task that was executed.
            result: The outcome of executing the task.
        """
        record = {
            "task_id": task.id,
            "task_title": task.title,
            "task_description": task.description,
            "task_priority": task.priority,
            "task_source": task.source,
            "task_created_at": task.created_at.isoformat(),
            "task_ask_id": task.ask_id,
            "task_okr_id": task.okr_id,
            "task_metadata": task.metadata,
            "result_succeeded": result.succeeded,
            "result_output": result.output,
            "result_error": result.error,
            "result_needs_escalation": result.needs_escalation,
            "result_escalation_reason": result.escalation_reason,
            "result_artifacts": result.artifacts,
            "result_metadata": result.metadata,
            "result_duration_ms": result.duration_ms,
        }
        self._records.append(record)

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most recent task execution records.

        Args:
            limit: Maximum number of records to return. Defaults to 10.

        Returns:
            List of the most recent records in reverse chronological order.
        """
        return list(reversed(self._records[-limit:]))

    def get_context(self, task: Task) -> dict[str, Any]:
        """Get relevant context for a task from memory.

        For this mock implementation, returns the most recent records
        with matching source type, plus any records with similar titles.

        Args:
            task: The task to get context for.

        Returns:
            Dictionary with 'similar_tasks' and 'same_source' lists.
        """
        similar_tasks: list[dict[str, Any]] = []
        same_source: list[dict[str, Any]] = []

        # Simple matching: check for shared words in title
        task_words = set(task.title.lower().split())

        for record in self._records:
            # Check for same source type
            if record["task_source"] == task.source:
                same_source.append(record)

            # Check for title word overlap
            record_words = set(record["task_title"].lower().split())
            if task_words & record_words:  # Non-empty intersection
                similar_tasks.append(record)

        return {
            "similar_tasks": similar_tasks[-5:],  # Last 5 similar
            "same_source": same_source[-5:],  # Last 5 from same source
        }

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search memory for matching task records.

        Performs case-insensitive substring matching on task titles
        and descriptions.

        Args:
            query: Search query string.
            limit: Maximum number of results to return. Defaults to 5.

        Returns:
            List of matching records, most recent first.
        """
        query_lower = query.lower()
        matches: list[dict[str, Any]] = []

        for record in reversed(self._records):
            title_match = query_lower in record["task_title"].lower()
            desc_match = query_lower in record["task_description"].lower()

            if title_match or desc_match:
                matches.append(record)
                if len(matches) >= limit:
                    break

        return matches
