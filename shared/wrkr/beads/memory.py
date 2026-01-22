"""
BeadsMemory: Memory implementation that persists to beads/quinn.db.

Implements MemoryInterface for storing task execution history,
enabling context-aware task execution and learning from past work.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import json
import subprocess

from shared.wrkr.core.task import Task
from shared.wrkr.core.result import WorkerResult


class BeadsMemory:
    """
    Memory implementation backed by beads storage.

    Stores task execution records as beads issues with type "execution".
    Records are linked to source tasks via dependencies, enabling:
    - Historical lookup by task
    - Context retrieval for similar tasks
    - Search across execution history

    This implements MemoryInterface for use with BaseWorker.
    """

    def __init__(
        self,
        worker_id: str,
        bd_command: str = "bd",
        db_path: str | None = None,
    ):
        """
        Initialize beads memory.

        Args:
            worker_id: The worker ID this memory belongs to.
            bd_command: Path to the bd command. Defaults to "bd".
            db_path: Optional database path override.
        """
        self._worker_id = worker_id
        self._bd_command = bd_command
        self._db_path = db_path

    @property
    def worker_id(self) -> str:
        """The worker ID this memory belongs to."""
        return self._worker_id

    def _run_bd(self, *args: str) -> str:
        """Run a bd command and return output.

        Args:
            *args: Command arguments after "bd".

        Returns:
            Command stdout.

        Raises:
            RuntimeError: If command fails.
        """
        cmd = [self._bd_command] + list(args)
        if self._db_path:
            cmd.extend(["--db", self._db_path])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"bd command failed: {result.stderr}")
        return result.stdout

    def record(self, task: Task, result: WorkerResult) -> None:
        """
        Record a task execution to beads.

        Creates an execution record issue linked to the source task.

        Args:
            task: The task that was executed.
            result: The outcome of executing the task.
        """
        # Build execution record metadata
        record_data = {
            "task_id": task.id,
            "task_title": task.title,
            "task_priority": task.priority,
            "task_source": task.source,
            "worker_id": self._worker_id,
            "succeeded": result.succeeded,
            "output_preview": result.output[:500] if result.output else "",
            "error": result.error,
            "needs_escalation": result.needs_escalation,
            "escalation_reason": result.escalation_reason,
            "duration_ms": result.duration_ms,
            "artifacts_count": len(result.artifacts),
            "recorded_at": datetime.now().isoformat(),
        }

        # Create title for the execution record
        status = "success" if result.succeeded else "failure"
        if result.needs_escalation:
            status = "escalated"
        title = f"Execution: {task.title[:50]} [{status}]"

        # Create execution record as ephemeral issue
        args = [
            "create",
            f"--title={title}",
            "--type=execution",
            "--priority=4",  # Low priority (historical record)
            "--ephemeral",  # Auto-cleanup after some time
            f"--metadata={json.dumps(record_data)}",
        ]

        if task.id:
            args.append(f"--caused-by={task.id}")

        if task.ask_id:
            args.append(f"--spawned-from={task.ask_id}")

        if task.okr_id:
            args.append(f"--serves={task.okr_id}")

        try:
            self._run_bd(*args)
        except RuntimeError:
            pass  # Best effort recording

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get the most recent task execution records.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of execution records, most recent first.
        """
        try:
            output = self._run_bd(
                "list",
                "--json",
                "--type=execution",
                f"--limit={limit}",
            )
            issues = json.loads(output) if output.strip() else []
        except (RuntimeError, json.JSONDecodeError):
            return []

        records = []
        for issue in issues:
            metadata = issue.get("metadata", {})
            # Filter to this worker's records
            if metadata.get("worker_id") != self._worker_id:
                continue

            records.append({
                "record_id": issue["id"],
                "task_id": metadata.get("task_id"),
                "task_title": metadata.get("task_title"),
                "task_priority": metadata.get("task_priority"),
                "task_source": metadata.get("task_source"),
                "result_succeeded": metadata.get("succeeded"),
                "result_output": metadata.get("output_preview"),
                "result_error": metadata.get("error"),
                "result_needs_escalation": metadata.get("needs_escalation"),
                "result_escalation_reason": metadata.get("escalation_reason"),
                "result_duration_ms": metadata.get("duration_ms"),
                "recorded_at": metadata.get("recorded_at"),
            })

        # Sort by recorded_at descending
        records.sort(
            key=lambda r: r.get("recorded_at", ""),
            reverse=True,
        )

        return records[:limit]

    def get_context(self, task: Task) -> dict[str, Any]:
        """
        Get relevant context for a task from memory.

        Retrieves similar past tasks and guidance based on:
        - Tasks with matching source
        - Tasks with similar titles
        - Recent escalations for guidance

        Args:
            task: The task to get context for.

        Returns:
            Dictionary with 'similar_tasks', 'same_source', and 'guidance'.
        """
        recent_records = self.recent(limit=50)

        similar_tasks = []
        same_source = []
        escalations = []

        # Extract words from task title for matching
        task_words = set(task.title.lower().split())

        for record in recent_records:
            # Check source match
            if record.get("task_source") == task.source:
                same_source.append(record)

            # Check title similarity (word overlap)
            record_title = record.get("task_title", "")
            record_words = set(record_title.lower().split())
            if task_words & record_words:  # Non-empty intersection
                similar_tasks.append(record)

            # Collect escalations for guidance
            if record.get("result_needs_escalation"):
                escalations.append(record)

        # Build guidance from escalations
        guidance = ""
        if escalations:
            guidance_parts = []
            for esc in escalations[:3]:
                reason = esc.get("result_escalation_reason", "")
                if reason:
                    guidance_parts.append(f"- Previous escalation: {reason[:100]}")
            if guidance_parts:
                guidance = "Watch out for:\n" + "\n".join(guidance_parts)

        return {
            "similar_tasks": similar_tasks[:5],
            "same_source": same_source[:5],
            "guidance": guidance or "No specific guidance from history.",
        }

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Search memory for matching task records.

        Performs substring matching on task titles.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching records.
        """
        recent_records = self.recent(limit=100)
        query_lower = query.lower()

        matches = []
        for record in recent_records:
            title = record.get("task_title", "").lower()
            if query_lower in title:
                matches.append(record)
                if len(matches) >= limit:
                    break

        return matches

    def get_task_history(self, task_id: str) -> list[dict[str, Any]]:
        """
        Get all execution records for a specific task.

        Args:
            task_id: The task ID to get history for.

        Returns:
            List of execution records for the task.
        """
        recent_records = self.recent(limit=100)
        return [r for r in recent_records if r.get("task_id") == task_id]

    def get_success_rate(self, task_source: str | None = None) -> float:
        """
        Calculate success rate from recent history.

        Args:
            task_source: Optional source to filter by.

        Returns:
            Success rate as a float (0.0 to 1.0).
        """
        records = self.recent(limit=100)

        if task_source:
            records = [r for r in records if r.get("task_source") == task_source]

        if not records:
            return 1.0  # Assume success if no history

        successes = sum(1 for r in records if r.get("result_succeeded"))
        return successes / len(records)


class InMemoryBeadsMemory:
    """
    In-memory mock of BeadsMemory for testing.

    Simulates beads memory behavior without actual bd CLI calls.
    """

    def __init__(self, worker_id: str):
        """Initialize the mock memory.

        Args:
            worker_id: The worker ID this memory belongs to.
        """
        self._worker_id = worker_id
        self._records: list[dict[str, Any]] = []

    @property
    def worker_id(self) -> str:
        """The worker ID this memory belongs to."""
        return self._worker_id

    def record(self, task: Task, result: WorkerResult) -> None:
        """Record a task execution."""
        record = {
            "record_id": f"exec-{len(self._records) + 1}",
            "task_id": task.id,
            "task_title": task.title,
            "task_description": task.description,
            "task_priority": task.priority,
            "task_source": task.source,
            "task_ask_id": task.ask_id,
            "task_okr_id": task.okr_id,
            "worker_id": self._worker_id,
            "result_succeeded": result.succeeded,
            "result_output": result.output,
            "result_error": result.error,
            "result_needs_escalation": result.needs_escalation,
            "result_escalation_reason": result.escalation_reason,
            "result_duration_ms": result.duration_ms,
            "result_artifacts": result.artifacts,
            "recorded_at": datetime.now().isoformat(),
        }
        self._records.append(record)

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most recent records."""
        return list(reversed(self._records[-limit:]))

    def get_context(self, task: Task) -> dict[str, Any]:
        """Get relevant context for a task."""
        similar_tasks = []
        same_source = []
        escalations = []

        task_words = set(task.title.lower().split())

        for record in self._records:
            # Check source match
            if record.get("task_source") == task.source:
                same_source.append(record)

            # Check title similarity
            record_words = set(record.get("task_title", "").lower().split())
            if task_words & record_words:
                similar_tasks.append(record)

            # Collect escalations
            if record.get("result_needs_escalation"):
                escalations.append(record)

        guidance = ""
        if escalations:
            reasons = [
                e.get("result_escalation_reason", "")
                for e in escalations[-3:]
                if e.get("result_escalation_reason")
            ]
            if reasons:
                guidance = "Watch out for:\n" + "\n".join(f"- {r}" for r in reasons)

        return {
            "similar_tasks": similar_tasks[-5:],
            "same_source": same_source[-5:],
            "guidance": guidance or "No specific guidance from history.",
        }

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search memory for matching records."""
        query_lower = query.lower()
        matches = []

        for record in reversed(self._records):
            title = record.get("task_title", "").lower()
            desc = record.get("task_description", "").lower()
            if query_lower in title or query_lower in desc:
                matches.append(record)
                if len(matches) >= limit:
                    break

        return matches

    def get_task_history(self, task_id: str) -> list[dict[str, Any]]:
        """Get all records for a specific task."""
        return [r for r in self._records if r.get("task_id") == task_id]

    def get_success_rate(self, task_source: str | None = None) -> float:
        """Calculate success rate."""
        records = self._records

        if task_source:
            records = [r for r in records if r.get("task_source") == task_source]

        if not records:
            return 1.0

        successes = sum(1 for r in records if r.get("result_succeeded"))
        return successes / len(records)
