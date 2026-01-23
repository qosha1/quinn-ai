"""
Notification handling for workers.

NotificationHandler: Converts notifications to tasks, handles interrupts
UrgentInterrupt: Exception raised to interrupt current work for urgent messages

Notifications are ephemeral work pointers that:
- Come from inbox (new messages), queue (new tasks), or escalations
- Have time_sensitivity determining urgency
- Convert to Tasks for worker processing
- Auto-cleanup after actioning
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol
import uuid

logger = logging.getLogger(__name__)

from shared.comms.types import (
    Notification,
    TimeSensitivity,
    WorkerMessage,
)
from shared.wrkr.core.task import Task


class UrgentInterrupt(Exception):
    """Exception raised when urgent notification requires immediate attention.

    Workers should catch this to pause current work and handle the
    urgent notification, then resume previous work.
    """

    def __init__(self, notification: Notification, message: str = ""):
        self.notification = notification
        super().__init__(message or f"Urgent: {notification.title}")


@dataclass
class TaskConversionResult:
    """Result of converting a notification to a task.

    Attributes:
        task: The created task (None if conversion failed).
        notification: The original notification.
        success: Whether conversion succeeded.
        error: Error message if conversion failed.
    """

    task: Task | None
    notification: Notification
    success: bool = True
    error: str | None = None


class NotificationHandlerInterface(Protocol):
    """Protocol for notification handling.

    Handles notification retrieval, task conversion, and urgent interrupts.
    """

    def poll(self) -> list[Notification]:
        """Get pending notifications for this worker.

        Returns:
            List of unprocessed notifications.
        """
        ...

    def check_urgent(self) -> Notification | None:
        """Check for urgent notifications requiring immediate attention.

        Returns:
            The most urgent notification if any, None otherwise.
        """
        ...

    def convert_to_task(self, notification: Notification) -> TaskConversionResult:
        """Convert a notification to a task.

        Args:
            notification: The notification to convert.

        Returns:
            TaskConversionResult with the created task or error.
        """
        ...

    def acknowledge(self, notification_id: str) -> None:
        """Acknowledge/dismiss a notification.

        Args:
            notification_id: The notification to acknowledge.
        """
        ...


class NotificationHandler(ABC):
    """Base notification handler with task conversion logic.

    Subclasses implement storage-specific notification fetching.
    """

    def __init__(
        self,
        worker_id: str,
        on_urgent: Callable[[Notification], None] | None = None,
    ):
        """Initialize notification handler.

        Args:
            worker_id: The worker ID to handle notifications for.
            on_urgent: Optional callback for urgent notifications.
        """
        self._worker_id = worker_id
        self._on_urgent = on_urgent

    @property
    def worker_id(self) -> str:
        """The worker ID this handler belongs to."""
        return self._worker_id

    @abstractmethod
    def _fetch_notifications(self) -> list[Notification]:
        """Fetch pending notifications from storage.

        Returns:
            List of unprocessed notifications.
        """
        pass

    @abstractmethod
    def _acknowledge(self, notification_id: str) -> None:
        """Mark notification as acknowledged in storage.

        Args:
            notification_id: The notification to acknowledge.
        """
        pass

    @abstractmethod
    def _fetch_message(self, message_id: str) -> WorkerMessage | None:
        """Fetch a message by ID for task conversion.

        Args:
            message_id: The message ID to fetch.

        Returns:
            The message, or None if not found.
        """
        pass

    def poll(self) -> list[Notification]:
        """Get pending notifications, sorted by urgency.

        Returns:
            List of notifications, most urgent first.
        """
        notifications = self._fetch_notifications()
        return self._sort_by_urgency(notifications)

    def check_urgent(self) -> Notification | None:
        """Check for urgent notifications.

        If found and callback is set, invokes the callback.

        Returns:
            Most urgent notification if any with IMMEDIATE sensitivity.
        """
        notifications = self.poll()
        for notif in notifications:
            if notif.time_sensitivity == TimeSensitivity.IMMEDIATE:
                if self._on_urgent:
                    self._on_urgent(notif)
                return notif
        return None

    def raise_if_urgent(self) -> None:
        """Check for urgent notifications and raise interrupt if found.

        Raises:
            UrgentInterrupt: If an urgent notification is pending.
        """
        urgent = self.check_urgent()
        if urgent:
            raise UrgentInterrupt(urgent)

    def convert_to_task(self, notification: Notification) -> TaskConversionResult:
        """Convert a notification to a task.

        For message notifications: creates task from message content.
        For task notifications: retrieves the referenced task.

        Args:
            notification: The notification to convert.

        Returns:
            TaskConversionResult with task or error.
        """
        try:
            if notification.points_to_message():
                return self._convert_message_notification(notification)
            elif notification.points_to_task():
                return self._convert_task_notification(notification)
            else:
                # Generic notification becomes a task
                return self._convert_generic_notification(notification)
        except Exception as e:
            return TaskConversionResult(
                task=None,
                notification=notification,
                success=False,
                error=str(e),
            )

    def _convert_message_notification(
        self, notification: Notification
    ) -> TaskConversionResult:
        """Convert a message notification to a task.

        Args:
            notification: Notification pointing to a message.

        Returns:
            TaskConversionResult with message-based task.
        """
        message = self._fetch_message(notification.message_id)
        if not message:
            return TaskConversionResult(
                task=None,
                notification=notification,
                success=False,
                error=f"Message not found: {notification.message_id}",
            )

        # Map time sensitivity to priority
        priority_map = {
            TimeSensitivity.IMMEDIATE: 0,  # CRITICAL
            TimeSensitivity.HOURS: 1,      # HIGH
            TimeSensitivity.DAYS: 2,       # MEDIUM
            TimeSensitivity.WEEKS: 3,      # LOW
            TimeSensitivity.WHENEVER: 4,   # BACKLOG
        }

        task = Task(
            id=f"task-{notification.id}",
            title=f"Handle: {message.subject}",
            description=f"""From: {message.sender}
Type: {message.message_type.value}

{message.body}""",
            priority=priority_map.get(notification.time_sensitivity, 2),
            source="queue",  # Treated as queue-sourced task
            ask_id=message.ask_id,
            okr_id=message.okr_id,
            metadata={
                "notification_id": notification.id,
                "message_id": message.id,
                "sender": message.sender,
                "message_type": message.message_type.value,
            },
        )

        return TaskConversionResult(
            task=task,
            notification=notification,
            success=True,
        )

    def _convert_task_notification(
        self, notification: Notification
    ) -> TaskConversionResult:
        """Convert a task notification (just references existing task).

        Args:
            notification: Notification pointing to a task.

        Returns:
            TaskConversionResult indicating the task reference.
        """
        # For task notifications, we just need the task ID
        # The actual task retrieval is handled by the queue
        task = Task(
            id=notification.task_id,
            title=notification.title,
            description="Task referenced by notification",
            source="queue",
            metadata={
                "notification_id": notification.id,
                "is_reference": True,
            },
        )

        return TaskConversionResult(
            task=task,
            notification=notification,
            success=True,
        )

    def _convert_generic_notification(
        self, notification: Notification
    ) -> TaskConversionResult:
        """Convert a generic notification to a task.

        Args:
            notification: Generic notification without specific reference.

        Returns:
            TaskConversionResult with generic task.
        """
        priority_map = {
            TimeSensitivity.IMMEDIATE: 0,
            TimeSensitivity.HOURS: 1,
            TimeSensitivity.DAYS: 2,
            TimeSensitivity.WEEKS: 3,
            TimeSensitivity.WHENEVER: 4,
        }

        task = Task(
            id=f"task-{notification.id}",
            title=notification.title,
            description=f"Source: {notification.source}\n\n{notification.metadata.get('description', '')}",
            priority=priority_map.get(notification.time_sensitivity, 2),
            source="queue",
            metadata={
                "notification_id": notification.id,
                "source": notification.source,
                **notification.metadata,
            },
        )

        return TaskConversionResult(
            task=task,
            notification=notification,
            success=True,
        )

    def acknowledge(self, notification_id: str) -> None:
        """Acknowledge/dismiss a notification.

        Args:
            notification_id: The notification to acknowledge.
        """
        self._acknowledge(notification_id)

    def _sort_by_urgency(
        self, notifications: list[Notification]
    ) -> list[Notification]:
        """Sort notifications by urgency, then by creation time.

        Args:
            notifications: List to sort.

        Returns:
            Sorted list with most urgent first.
        """
        urgency_order = {
            TimeSensitivity.IMMEDIATE: 0,
            TimeSensitivity.HOURS: 1,
            TimeSensitivity.DAYS: 2,
            TimeSensitivity.WEEKS: 3,
            TimeSensitivity.WHENEVER: 4,
        }
        return sorted(
            notifications,
            key=lambda n: (urgency_order[n.time_sensitivity], n.created_at),
        )


class InMemoryNotificationHandler(NotificationHandler):
    """In-memory notification handler for testing."""

    def __init__(
        self,
        worker_id: str,
        on_urgent: Callable[[Notification], None] | None = None,
    ):
        super().__init__(worker_id, on_urgent)
        self._notifications: list[Notification] = []
        self._acknowledged: set[str] = set()
        self._messages: dict[str, WorkerMessage] = {}

    def add_notification(self, notification: Notification) -> None:
        """Add a notification (for testing).

        Args:
            notification: The notification to add.
        """
        self._notifications.append(notification)

    def add_message(self, message: WorkerMessage) -> None:
        """Add a message for reference (for testing).

        Args:
            message: The message to add.
        """
        self._messages[message.id] = message

    def _fetch_notifications(self) -> list[Notification]:
        """Fetch pending notifications."""
        return [
            n
            for n in self._notifications
            if n.id not in self._acknowledged and not n.is_expired()
        ]

    def _acknowledge(self, notification_id: str) -> None:
        """Mark notification as acknowledged."""
        self._acknowledged.add(notification_id)

    def _fetch_message(self, message_id: str) -> WorkerMessage | None:
        """Fetch message by ID."""
        return self._messages.get(message_id)


class BeadsNotificationHandler(NotificationHandler):
    """Notification handler that uses beads for storage.

    Notifications are stored as Issues with:
    - type: notification
    - assignee: worker_id
    - status: open (pending) / closed (acknowledged)
    - time_sensitivity: urgency level
    - ephemeral: true (auto-cleanup)
    """

    def __init__(
        self,
        worker_id: str,
        bd_command: str = "bd",
        db_path: str | None = None,
        on_urgent: Callable[[Notification], None] | None = None,
        bd_client: Any | None = None,
    ):
        """Initialize beads notification handler.

        Args:
            worker_id: The worker ID to handle notifications for.
            bd_command: Path to bd command.
            db_path: Optional database path override.
            on_urgent: Optional callback for urgent notifications.
            bd_client: Optional BdClient instance (preferred over bd_command/db_path).
        """
        super().__init__(worker_id, on_urgent)
        if bd_client is not None:
            self._bd_client = bd_client
        else:
            from shared.bd import BdClient

            self._bd_client = BdClient(bd_command=bd_command, db_path=db_path)

    def _run_bd(self, *args: str) -> str:
        """Run a bd command and return output."""
        from shared.bd import BdClientError

        try:
            return self._bd_client.run(*args)
        except BdClientError as e:
            raise RuntimeError(str(e)) from e

    def _parse_notification(self, issue_data: dict[str, Any]) -> Notification:
        """Convert beads issue to Notification.

        Args:
            issue_data: Issue data from bd list --json.

        Returns:
            Notification instance.
        """
        time_sens_map = {
            "immediate": TimeSensitivity.IMMEDIATE,
            "hours": TimeSensitivity.HOURS,
            "days": TimeSensitivity.DAYS,
            "weeks": TimeSensitivity.WEEKS,
            "whenever": TimeSensitivity.WHENEVER,
        }

        metadata = issue_data.get("metadata", {})

        return Notification(
            id=issue_data["id"],
            worker_id=issue_data.get("assignee", self._worker_id),
            title=issue_data.get("title", ""),
            time_sensitivity=time_sens_map.get(
                issue_data.get("time_sensitivity", "whenever"),
                TimeSensitivity.WHENEVER,
            ),
            message_id=metadata.get("message_id"),
            task_id=metadata.get("task_id"),
            source=metadata.get("source", "system"),
            created_at=datetime.fromisoformat(issue_data["created_at"])
            if issue_data.get("created_at")
            else datetime.now(),
            expires_at=datetime.fromisoformat(metadata["expires_at"])
            if metadata.get("expires_at")
            else None,
            metadata=metadata,
        )

    def _fetch_notifications(self) -> list[Notification]:
        """Fetch pending notifications from beads."""
        import json

        try:
            output = self._run_bd(
                "list",
                "--json",
                "--type=notification",
                "--status=open",
                f"--assignee={self._worker_id}",
            )
            issues = json.loads(output) if output.strip() else []
        except (RuntimeError, json.JSONDecodeError) as e:
            logger.warning("Failed to fetch notifications for worker %s: %s", self._worker_id, e)
            return []

        return [self._parse_notification(issue) for issue in issues]

    def _acknowledge(self, notification_id: str) -> None:
        """Acknowledge by closing the beads issue."""
        try:
            self._run_bd("close", notification_id, "--reason=acknowledged")
        except RuntimeError as e:
            logger.debug("Failed to acknowledge notification %s: %s", notification_id, e)

    def _fetch_message(self, message_id: str) -> WorkerMessage | None:
        """Fetch message from beads."""
        import json

        try:
            output = self._run_bd("show", message_id, "--json")
            issue = json.loads(output)
        except (RuntimeError, json.JSONDecodeError) as e:
            logger.warning("Failed to fetch message %s: %s", message_id, e)
            return None

        metadata = issue.get("metadata", {})

        # Map message type
        from shared.comms.types import MessageType

        type_map = {
            "request": MessageType.REQUEST,
            "response": MessageType.RESPONSE,
            "inform": MessageType.INFORM,
            "escalation": MessageType.ESCALATION,
            "delegation": MessageType.DELEGATION,
            "broadcast": MessageType.BROADCAST,
        }

        return WorkerMessage(
            id=issue["id"],
            sender=metadata.get("sender", ""),
            recipients=metadata.get("recipients", []),
            subject=issue.get("title", ""),
            body=issue.get("description", ""),
            message_type=type_map.get(
                metadata.get("message_type", "inform"),
                MessageType.INFORM,
            ),
            time_sensitivity=TimeSensitivity(
                issue.get("time_sensitivity", "whenever")
            ),
            thread_id=issue.get("thread_id"),
            reply_to=issue.get("reply_to"),
            ask_id=issue.get("ask_id"),
            okr_id=issue.get("okr_id"),
            ephemeral=issue.get("ephemeral", False),
            metadata=metadata,
            created_at=datetime.fromisoformat(issue["created_at"])
            if issue.get("created_at")
            else datetime.now(),
        )
