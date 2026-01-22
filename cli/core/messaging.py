"""
Messaging service for QuinnAI.

Provides a clean interface for communication operations:
- Creating channels
- Sending messages
- Creating notifications

Centralizes messaging logic that was previously scattered across modules.
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .db import Database


@dataclass
class MessageResult:
    """Result of a messaging operation."""
    success: bool
    message_id: Optional[str] = None
    channel_id: Optional[str] = None
    notification_id: Optional[str] = None
    error: Optional[str] = None


class MessagingService:
    """
    Service for handling all messaging operations.

    Provides a clean interface for:
    - Creating channels between workers
    - Sending messages
    - Creating notification beads
    """

    def __init__(self, db: "Database"):
        self._db = db

    def send_offboarding_notification(
        self,
        worker_id: str,
        worker_name: str,
        worker_role: str,
        manager_id: str,
    ) -> MessageResult:
        """Send offboarding notification to manager.

        Creates a direct channel between worker and manager,
        sends a handoff message, and creates a notification bead.

        Args:
            worker_id: ID of the worker being offboarded
            worker_name: Name of the worker
            worker_role: Role of the worker
            manager_id: ID of the manager to notify

        Returns:
            MessageResult with operation status
        """
        from .queries import (
            create_channel,
            subscribe_to_channel,
            create_message,
        )
        from .notifications import create_notification_bead

        try:
            # Create or get direct channel for handoff
            channel_name = f"handoff-{worker_id}"
            channel = create_channel(
                self._db,
                name=channel_name,
                channel_type="direct",
            )

            # Subscribe both workers to the channel
            subscribe_to_channel(self._db, channel.id, worker_id)
            subscribe_to_channel(self._db, channel.id, manager_id)

            # Create handoff message
            message = create_message(
                self._db,
                channel_id=channel.id,
                from_worker_id=worker_id,
                content=(
                    f"OFFBOARDING REVIEW REQUIRED\n\n"
                    f"Worker {worker_name} ({worker_id}) is being terminated.\n"
                    f"Role: {worker_role}\n\n"
                    f"Please review their frozen storage and archive any useful files "
                    f"to shared/archive/{worker_id}/ before completing termination.\n\n"
                    f"Use: cleanup_terminated_worker(db, '{worker_id}', storage_manager)"
                ),
                priority=1,  # High priority
                time_sensitivity="hours",  # Needs attention soon
            )

            # Create notification bead for manager
            notification_id = create_notification_bead(
                self._db,
                worker_id=manager_id,
                message_id=message.id,
                channel_id=channel.id,
                priority=1,  # High priority
            )

            return MessageResult(
                success=True,
                message_id=message.id,
                channel_id=channel.id,
                notification_id=notification_id,
            )

        except Exception as e:
            return MessageResult(
                success=False,
                error=str(e),
            )

    def create_direct_channel(
        self,
        worker_id_1: str,
        worker_id_2: str,
        name: Optional[str] = None,
    ) -> MessageResult:
        """Create a direct channel between two workers.

        Args:
            worker_id_1: First worker ID
            worker_id_2: Second worker ID
            name: Optional channel name (defaults to 'dm-{id1}-{id2}')

        Returns:
            MessageResult with channel_id if successful
        """
        from .queries import create_channel, subscribe_to_channel

        try:
            channel_name = name or f"dm-{worker_id_1}-{worker_id_2}"
            channel = create_channel(
                self._db,
                name=channel_name,
                channel_type="direct",
            )

            subscribe_to_channel(self._db, channel.id, worker_id_1)
            subscribe_to_channel(self._db, channel.id, worker_id_2)

            return MessageResult(
                success=True,
                channel_id=channel.id,
            )

        except Exception as e:
            return MessageResult(
                success=False,
                error=str(e),
            )

    def send_message(
        self,
        channel_id: str,
        from_worker_id: str,
        content: str,
        priority: int = 2,
        time_sensitivity: str = "whenever",
    ) -> MessageResult:
        """Send a message to a channel.

        Args:
            channel_id: Channel to send to
            from_worker_id: Worker sending the message
            content: Message content
            priority: Message priority (1-4)
            time_sensitivity: When message needs attention

        Returns:
            MessageResult with message_id if successful
        """
        from .queries import create_message

        try:
            message = create_message(
                self._db,
                channel_id=channel_id,
                from_worker_id=from_worker_id,
                content=content,
                priority=priority,
                time_sensitivity=time_sensitivity,
            )

            return MessageResult(
                success=True,
                message_id=message.id,
                channel_id=channel_id,
            )

        except Exception as e:
            return MessageResult(
                success=False,
                error=str(e),
            )

    def notify_worker(
        self,
        worker_id: str,
        message_id: str,
        channel_id: str,
        priority: int = 2,
    ) -> MessageResult:
        """Create a notification for a worker about a message.

        Args:
            worker_id: Worker to notify
            message_id: Message to notify about
            channel_id: Channel the message is in
            priority: Notification priority (1-4)

        Returns:
            MessageResult with notification_id if successful
        """
        from .notifications import create_notification_bead

        try:
            notification_id = create_notification_bead(
                self._db,
                worker_id=worker_id,
                message_id=message_id,
                channel_id=channel_id,
                priority=priority,
            )

            return MessageResult(
                success=True,
                notification_id=notification_id,
                message_id=message_id,
                channel_id=channel_id,
            )

        except Exception as e:
            return MessageResult(
                success=False,
                error=str(e),
            )
