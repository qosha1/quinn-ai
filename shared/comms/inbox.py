"""
Worker inbox for receiving messages.

InboxInterface: Protocol for message retrieval
BeadsInbox: Implementation that fetches from beads via bd commands

Workers poll their inbox during idle state or can be interrupted
by urgent messages (TimeSensitivity.IMMEDIATE).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from shared.comms.types import (
    MessageType,
    Notification,
    TimeSensitivity,
    WorkerMessage,
)


class InboxInterface(Protocol):
    """Protocol for worker message inbox.

    Inbox provides message retrieval for a specific worker,
    filtering by status (read/unread) and urgency.
    """

    def poll(self) -> list[WorkerMessage]:
        """Get all unread messages for this worker.

        Returns:
            List of unread messages, ordered by time_sensitivity then created_at.
        """
        ...

    def get_urgent(self) -> list[WorkerMessage]:
        """Get only urgent (IMMEDIATE) messages.

        Returns:
            List of messages with time_sensitivity == IMMEDIATE.
        """
        ...

    def mark_read(self, message_id: str) -> None:
        """Mark a message as read.

        Args:
            message_id: The message ID to mark as read.
        """
        ...

    def get_thread(self, thread_id: str) -> list[WorkerMessage]:
        """Get all messages in a conversation thread.

        Args:
            thread_id: The thread ID to retrieve.

        Returns:
            List of messages in the thread, ordered chronologically.
        """
        ...

    def count_unread(self) -> int:
        """Get count of unread messages.

        Returns:
            Number of unread messages in inbox.
        """
        ...


class BaseInbox(ABC):
    """Base class for inbox implementations.

    Provides common filtering and sorting logic.
    Subclasses implement storage-specific fetch methods.
    """

    def __init__(self, worker_id: str):
        """Initialize inbox for a specific worker.

        Args:
            worker_id: The worker ID this inbox belongs to.
        """
        self._worker_id = worker_id

    @property
    def worker_id(self) -> str:
        """The worker ID this inbox belongs to."""
        return self._worker_id

    @abstractmethod
    def _fetch_messages(
        self,
        unread_only: bool = True,
        time_sensitivity: TimeSensitivity | None = None,
    ) -> list[WorkerMessage]:
        """Fetch messages from storage.

        Subclasses implement this to retrieve from their storage backend.

        Args:
            unread_only: If True, only return unread messages.
            time_sensitivity: If set, filter by this urgency level.

        Returns:
            List of matching messages.
        """
        pass

    @abstractmethod
    def _mark_read(self, message_id: str) -> None:
        """Mark message as read in storage.

        Args:
            message_id: The message to mark read.
        """
        pass

    @abstractmethod
    def _fetch_thread(self, thread_id: str) -> list[WorkerMessage]:
        """Fetch all messages in a thread from storage.

        Args:
            thread_id: The thread to fetch.

        Returns:
            List of messages in the thread.
        """
        pass

    def poll(self) -> list[WorkerMessage]:
        """Get all unread messages, sorted by urgency.

        Returns:
            List of unread messages, urgent first, then by created_at.
        """
        messages = self._fetch_messages(unread_only=True)
        return self._sort_by_urgency(messages)

    def get_urgent(self) -> list[WorkerMessage]:
        """Get only urgent messages requiring immediate attention.

        Returns:
            List of IMMEDIATE time_sensitivity messages.
        """
        return self._fetch_messages(
            unread_only=True,
            time_sensitivity=TimeSensitivity.IMMEDIATE,
        )

    def mark_read(self, message_id: str) -> None:
        """Mark a message as read.

        Args:
            message_id: The message ID to mark.
        """
        self._mark_read(message_id)

    def get_thread(self, thread_id: str) -> list[WorkerMessage]:
        """Get conversation thread.

        Args:
            thread_id: The thread to retrieve.

        Returns:
            Messages in chronological order.
        """
        messages = self._fetch_thread(thread_id)
        return sorted(messages, key=lambda m: m.created_at)

    def count_unread(self) -> int:
        """Count unread messages.

        Returns:
            Number of unread messages.
        """
        return len(self._fetch_messages(unread_only=True))

    def _sort_by_urgency(self, messages: list[WorkerMessage]) -> list[WorkerMessage]:
        """Sort messages by urgency (immediate first), then by created_at.

        Args:
            messages: List of messages to sort.

        Returns:
            Sorted list with urgent messages first.
        """
        # Define urgency order (lower = more urgent)
        urgency_order = {
            TimeSensitivity.IMMEDIATE: 0,
            TimeSensitivity.HOURS: 1,
            TimeSensitivity.DAYS: 2,
            TimeSensitivity.WEEKS: 3,
            TimeSensitivity.WHENEVER: 4,
        }
        return sorted(
            messages,
            key=lambda m: (urgency_order[m.time_sensitivity], m.created_at),
        )


class InMemoryInbox(BaseInbox):
    """In-memory inbox for testing.

    Stores messages in a list without persistence.
    """

    def __init__(self, worker_id: str):
        super().__init__(worker_id)
        self._messages: list[WorkerMessage] = []
        self._read_ids: set[str] = set()

    def add_message(self, message: WorkerMessage) -> None:
        """Add a message to the inbox (for testing).

        Args:
            message: The message to add.
        """
        if self._worker_id in message.recipients:
            self._messages.append(message)

    def _fetch_messages(
        self,
        unread_only: bool = True,
        time_sensitivity: TimeSensitivity | None = None,
    ) -> list[WorkerMessage]:
        """Fetch messages from memory."""
        result = []
        for msg in self._messages:
            # Filter by read status
            if unread_only and msg.id in self._read_ids:
                continue
            # Filter by time sensitivity
            if time_sensitivity and msg.time_sensitivity != time_sensitivity:
                continue
            result.append(msg)
        return result

    def _mark_read(self, message_id: str) -> None:
        """Mark message as read."""
        self._read_ids.add(message_id)

    def _fetch_thread(self, thread_id: str) -> list[WorkerMessage]:
        """Fetch thread messages."""
        return [m for m in self._messages if m.thread_id == thread_id]


class BeadsInbox(BaseInbox):
    """Inbox implementation that fetches from beads.

    Uses bd commands to query messages stored as Issues in the beads system.
    Messages are filtered by:
    - recipient matching worker_id (assignee field)
    - sender != worker_id (not sent by self)
    - open status (unread = open, read = closed)
    """

    def __init__(
        self,
        worker_id: str,
        bd_command: str = "bd",
        db_path: str | None = None,
        bd_client: Any | None = None,
    ):
        """Initialize beads inbox.

        Args:
            worker_id: The worker ID this inbox belongs to.
            bd_command: Path to bd command (default: "bd").
            db_path: Optional database path override.
            bd_client: Optional BdClient instance (preferred over bd_command/db_path).
        """
        super().__init__(worker_id)
        if bd_client is not None:
            self._bd_client = bd_client
        else:
            from shared.bd import BdClient

            self._bd_client = BdClient(bd_command=bd_command, db_path=db_path)

    def _run_bd(self, *args: str) -> str:
        """Run a bd command and return output.

        Args:
            *args: Command arguments after "bd".

        Returns:
            Command stdout.

        Raises:
            RuntimeError: If command fails.
        """
        from shared.bd import BdClientError

        try:
            return self._bd_client.run(*args)
        except BdClientError as e:
            raise RuntimeError(str(e)) from e

    def _parse_message(self, issue_data: dict[str, Any]) -> WorkerMessage:
        """Convert beads issue data to WorkerMessage.

        Args:
            issue_data: Dictionary from bd list --json output.

        Returns:
            WorkerMessage instance.
        """
        from datetime import datetime

        # Map beads fields to WorkerMessage
        time_sens_map = {
            "immediate": TimeSensitivity.IMMEDIATE,
            "hours": TimeSensitivity.HOURS,
            "days": TimeSensitivity.DAYS,
            "weeks": TimeSensitivity.WEEKS,
            "whenever": TimeSensitivity.WHENEVER,
        }

        type_map = {
            "request": MessageType.REQUEST,
            "response": MessageType.RESPONSE,
            "inform": MessageType.INFORM,
            "escalation": MessageType.ESCALATION,
            "delegation": MessageType.DELEGATION,
            "broadcast": MessageType.BROADCAST,
        }

        return WorkerMessage(
            id=issue_data["id"],
            sender=issue_data.get("sender", ""),
            recipients=[issue_data.get("assignee", "")] if issue_data.get("assignee") else [],
            subject=issue_data.get("title", ""),
            body=issue_data.get("description", ""),
            message_type=type_map.get(
                issue_data.get("metadata", {}).get("message_type", "inform"),
                MessageType.INFORM,
            ),
            time_sensitivity=time_sens_map.get(
                issue_data.get("time_sensitivity", "whenever"),
                TimeSensitivity.WHENEVER,
            ),
            thread_id=issue_data.get("thread_id"),
            reply_to=issue_data.get("reply_to"),
            ask_id=issue_data.get("ask_id"),
            okr_id=issue_data.get("okr_id"),
            ephemeral=issue_data.get("ephemeral", False),
            metadata=issue_data.get("metadata", {}),
            created_at=datetime.fromisoformat(issue_data["created_at"])
            if issue_data.get("created_at")
            else datetime.now(),
        )

    def _fetch_messages(
        self,
        unread_only: bool = True,
        time_sensitivity: TimeSensitivity | None = None,
    ) -> list[WorkerMessage]:
        """Fetch messages from beads.

        Uses bd list to query issues assigned to this worker.
        """
        import json

        args = ["list", "--json", f"--assignee={self._worker_id}"]
        if unread_only:
            args.append("--status=open")
        if time_sensitivity:
            args.append(f"--time-sensitivity={time_sensitivity.value}")

        try:
            output = self._run_bd(*args)
            issues = json.loads(output) if output.strip() else []
        except (RuntimeError, json.JSONDecodeError):
            return []

        # Filter out messages sent by self
        messages = []
        for issue in issues:
            if issue.get("sender") != self._worker_id:
                messages.append(self._parse_message(issue))

        return messages

    def _mark_read(self, message_id: str) -> None:
        """Mark message as read by closing the issue."""
        try:
            self._run_bd("close", message_id, "--reason=read")
        except RuntimeError:
            pass  # Best effort

    def _fetch_thread(self, thread_id: str) -> list[WorkerMessage]:
        """Fetch all messages in a thread."""
        import json

        try:
            output = self._run_bd("list", "--json", f"--thread={thread_id}")
            issues = json.loads(output) if output.strip() else []
        except (RuntimeError, json.JSONDecodeError):
            return []

        return [self._parse_message(issue) for issue in issues]
