"""
WorkerBridge - Bridge between pyterm AgentSession and qn wrkr operations.

Provides programmatic access to worker operations (get-work, inbox, send, status)
for AI workers running in AgentSessions. The session knows the worker_id and can
query SQLite directly.

This is the integration point between:
- AgentSession (terminal session management)
- Worker (organization role and lifecycle)
- Beads (work item tracking)
- Messaging (inter-worker communication)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
import json
import logging
import re
import sqlite3

if TYPE_CHECKING:
    from sqlite3 import Connection

_logger = logging.getLogger(__name__)


# Safe pattern for worker IDs - alphanumeric, underscores, hyphens only
SAFE_WORKER_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_worker_id(worker_id: str) -> None:
    """Validate worker_id format to prevent injection attacks.

    Args:
        worker_id: Worker ID to validate

    Raises:
        ValueError: If worker_id contains unsafe characters
    """
    if not worker_id:
        raise ValueError("worker_id cannot be empty")
    if len(worker_id) > 128:
        raise ValueError(f"worker_id too long: {len(worker_id)} chars (max 128)")
    if not SAFE_WORKER_ID_PATTERN.match(worker_id):
        raise ValueError(
            f"Invalid worker_id format: '{worker_id}'. "
            "Only alphanumeric characters, underscores, and hyphens allowed."
        )


@dataclass
class WorkItem:
    """A work item (bead) assigned to a worker."""

    id: str
    title: str
    priority: int
    status: str
    type: str
    description: str = ""
    created_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "status": self.status,
            "type": self.type,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }


@dataclass
class Notification:
    """An inbox notification for a worker."""

    id: str
    channel_id: str
    channel_name: str
    message_id: str
    from_worker_id: str
    content: str
    priority: int
    status: str
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "message_id": self.message_id,
            "from_worker_id": self.from_worker_id,
            "content": self.content,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class WorkerStatus:
    """Status of a worker."""

    worker_id: str
    name: str
    role: str
    lifecycle_status: str
    runtime_status: Optional[str]
    current_task_id: Optional[str]
    can_work: bool
    is_session_active: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "role": self.role,
            "lifecycle_status": self.lifecycle_status,
            "runtime_status": self.runtime_status,
            "current_task_id": self.current_task_id,
            "can_work": self.can_work,
            "is_session_active": self.is_session_active,
        }


@dataclass
class SendResult:
    """Result of sending a message."""

    success: bool
    message_id: Optional[str] = None
    channel_name: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message_id": self.message_id,
            "channel_name": self.channel_name,
            "error": self.error,
        }


class WorkerBridgeError(Exception):
    """Base error for WorkerBridge operations."""

    pass


class WorkerNotFoundError(WorkerBridgeError):
    """Worker not found in database."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        super().__init__(f"Worker not found: {worker_id}")


class PermissionDeniedError(WorkerBridgeError):
    """Worker lacks permission for operation."""

    def __init__(self, action: str, resource: str):
        self.action = action
        self.resource = resource
        super().__init__(f"Permission denied: cannot {action} on {resource}")


class WorkerBridge:
    """
    Bridge between pyterm AgentSession and qn wrkr operations.

    Provides programmatic access to:
    - get_work(): Get assigned beads/tasks
    - get_inbox(): Get inbox notifications
    - send_message(): Send message to channel
    - get_status(): Get worker status

    The bridge handles:
    - Database access
    - Permission checks
    - Data transformation

    Example usage:
        bridge = WorkerBridge(db, worker_id, org_path)

        # Get assigned work
        work_items = bridge.get_work(limit=5)

        # Check inbox
        notifications = bridge.get_inbox(pending_only=True)

        # Send a message
        result = bridge.send_message("team-channel", "Hello team!")

        # Get status
        status = bridge.get_status()
    """

    def __init__(
        self,
        db: "Connection",
        worker_id: str,
        org_path: Optional[str] = None,
    ):
        """
        Initialize WorkerBridge.

        Args:
            db: SQLite database connection
            worker_id: ID of the worker this bridge serves
            org_path: Optional org path for beads integration

        Raises:
            ValueError: If worker_id format is invalid
            WorkerNotFoundError: If worker not found in database
        """
        # Validate worker_id format first (security)
        validate_worker_id(worker_id)

        self._db = db
        self._worker_id = worker_id
        self._org_path = org_path

        # Verify worker exists at construction
        self._verify_worker()

    def _verify_worker(self) -> None:
        """Verify the worker exists in the database."""
        from cli.core.worker import Worker
        from shared import WorkerNotFound

        try:
            Worker.get(self._db, self._worker_id)
        except WorkerNotFound:
            raise WorkerNotFoundError(self._worker_id)

    @property
    def worker_id(self) -> str:
        """Get the worker ID."""
        return self._worker_id

    # =========================================================================
    # Work Items (Beads)
    # =========================================================================

    def get_work(self, limit: int = 10) -> list[WorkItem]:
        """
        Get assigned work items (beads) for this worker.

        Args:
            limit: Maximum items to return

        Returns:
            List of WorkItem objects sorted by priority
        """
        from cli.core.worker import Worker
        from cli.core.bd_wrapper import run_bd
        from cli.core.permissions import PermissionLevel, can_worker_access_bead

        # Check if worker can accept work
        worker = Worker.get(self._db, self._worker_id)
        if not worker.can_work:
            return []

        # Query beads if org_path available
        if not self._org_path:
            return []

        try:
            result = run_bd(
                [
                    "list",
                    f"--assignee={self._worker_id}",
                    "--status=open",
                    "--status=in_progress",
                    "--json",
                ],
                org_path=self._org_path,
                worker_id=self._worker_id,
                capture_output=True,
            )

            if result.returncode != 0:
                return []

            if not result.stdout or result.stdout.strip() == "[]":
                return []

            try:
                items = json.loads(result.stdout)
            except json.JSONDecodeError:
                return []

            if not isinstance(items, list):
                return []

            # Filter by permission and convert to WorkItem
            work_items = []
            for item in items:
                bead_id = item.get("id")
                if not bead_id:
                    continue

                # Check permission
                if not can_worker_access_bead(
                    self._db, self._worker_id, bead_id, PermissionLevel.READ
                ):
                    continue

                work_items.append(
                    WorkItem(
                        id=bead_id,
                        title=item.get("title", "(no title)"),
                        priority=item.get("priority", 4),
                        status=item.get("status", "unknown"),
                        type=item.get("type", "task"),
                        description=item.get("description", ""),
                        metadata=item,
                    )
                )

            # Sort by priority and limit
            work_items.sort(key=lambda x: x.priority)
            return work_items[:limit]

        except FileNotFoundError:
            return []
        except ValueError:
            return []

    # =========================================================================
    # Inbox (Notifications)
    # =========================================================================

    def get_inbox(
        self,
        pending_only: bool = True,
        limit: int = 50,
    ) -> list[Notification]:
        """
        Get inbox notifications for this worker.

        Args:
            pending_only: If True, only return pending (unread) notifications
            limit: Maximum notifications to return

        Returns:
            List of Notification objects
        """
        from cli.core.notifications import (
            get_worker_notifications,
            get_pending_notifications,
        )
        from cli.core.queries import get_message, get_channel
        from cli.core.permissions import PermissionLevel, can_worker_access_channel

        # Get notifications
        if pending_only:
            notifs = get_pending_notifications(self._db, self._worker_id, limit=limit)
        else:
            notifs = get_worker_notifications(self._db, self._worker_id, limit=limit)

        # Convert to Notification objects, checking permissions
        notifications = []
        for notif in notifs:
            # Check channel permission
            if not can_worker_access_channel(
                self._db, self._worker_id, notif.channel_id, PermissionLevel.READ
            ):
                continue

            # Get channel name
            channel = get_channel(self._db, notif.channel_id)
            channel_name = channel.name if channel else notif.channel_id

            # Get message content
            message = get_message(self._db, notif.message_id)
            if not message:
                continue

            notifications.append(
                Notification(
                    id=notif.id,
                    channel_id=notif.channel_id,
                    channel_name=channel_name,
                    message_id=notif.message_id,
                    from_worker_id=message.from_worker_id,
                    content=message.content,
                    priority=notif.priority,
                    status=notif.status,
                    created_at=notif.created_at,
                )
            )

        return notifications

    def mark_notification_read(self, notification_id: str) -> bool:
        """
        Mark a notification as read.

        Args:
            notification_id: ID of notification to mark

        Returns:
            True if marked successfully
        """
        from cli.core.notifications import mark_notification_read

        try:
            mark_notification_read(self._db, notification_id)
            return True
        except (sqlite3.Error, ValueError) as e:
            _logger.warning(f"Failed to mark notification as read: {e}")
            return False

    def get_pending_count(self) -> int:
        """Get count of pending notifications."""
        from cli.core.notifications import count_pending_notifications

        return count_pending_notifications(self._db, self._worker_id)

    # =========================================================================
    # Messaging
    # =========================================================================

    def send_message(
        self,
        channel_id: str,
        content: str,
        priority: int = 2,
    ) -> SendResult:
        """
        Send a message to a channel.

        Args:
            channel_id: Channel to send to
            content: Message content
            priority: Priority 0-4 (lower is higher)

        Returns:
            SendResult with success status and message ID
        """
        from cli.core.queries import get_channel, create_message_with_notifications
        from cli.core.permissions import PermissionLevel, can_worker_access_channel

        # Verify channel exists
        channel = get_channel(self._db, channel_id)
        if not channel:
            return SendResult(
                success=False,
                error=f"Channel not found: {channel_id}",
            )

        # Check permission
        if not can_worker_access_channel(
            self._db, self._worker_id, channel_id, PermissionLevel.COMMENT
        ):
            return SendResult(
                success=False,
                error=f"Permission denied: cannot send to {channel.name}",
            )

        # Validate priority
        if not 0 <= priority <= 4:
            return SendResult(
                success=False,
                error=f"Invalid priority: {priority} (must be 0-4)",
            )

        # Send message
        try:
            msg = create_message_with_notifications(
                db=self._db,
                channel_id=channel_id,
                from_worker_id=self._worker_id,
                content=content,
                priority=priority,
            )
            return SendResult(
                success=True,
                message_id=msg.id,
                channel_name=channel.name,
            )
        except Exception as e:
            return SendResult(
                success=False,
                error=str(e),
            )

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> WorkerStatus:
        """
        Get status of this worker.

        Returns:
            WorkerStatus with current state
        """
        from cli.core.worker import Worker

        worker = Worker.get(self._db, self._worker_id)

        return WorkerStatus(
            worker_id=self._worker_id,
            name=worker.name,
            role=worker.role,
            lifecycle_status=worker.lifecycle_status,
            runtime_status=worker.runtime_status,
            current_task_id=worker.current_task_id,
            can_work=worker.can_work,
            is_session_active=worker.is_session_active,
        )

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize bridge state to dict."""
        return {
            "worker_id": self._worker_id,
            "org_path": self._org_path,
            "pending_notifications": self.get_pending_count(),
        }
