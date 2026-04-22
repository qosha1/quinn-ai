"""Messaging subsystem for QuinnAI."""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from .board_messages import BoardMessageCreator

if TYPE_CHECKING:
    from ..db import Database


@dataclass
class MessageResult:
    """Result of a messaging operation."""
    success: bool
    message_id: Optional[str] = None
    channel_id: Optional[str] = None
    notification_id: Optional[str] = None
    error: Optional[str] = None


class MessagingService:
    """Service for handling all messaging operations."""

    def __init__(self, db: "Database"):
        self._db = db

    def send_offboarding_notification(
        self,
        worker_id: str,
        worker_name: str,
        worker_role: str,
        manager_id: str,
    ) -> MessageResult:
        """Send offboarding notification to manager."""
        from ..queries import (
            create_channel,
            subscribe_to_channel,
            create_message,
        )
        from ..notifications import create_notification_bead

        try:
            channel_name = f"handoff-{worker_id}"
            channel = create_channel(
                self._db,
                name=channel_name,
                channel_type="direct",
            )
            subscribe_to_channel(self._db, channel.id, worker_id)
            subscribe_to_channel(self._db, channel.id, manager_id)

            message = create_message(
                self._db,
                channel_id=channel.id,
                from_worker_id=worker_id,
                content=(
                    f"OFFBOARDING REVIEW REQUIRED\n\n"
                    f"Worker {worker_name} ({worker_id}) is being terminated.\n"
                    f"Role: {worker_role}\n\n"
                    f"Please review their frozen storage and archive any useful files "
                    f"to shared/archive/{worker_id}/ before completing termination."
                ),
                priority=1,
                time_sensitivity="hours",
            )

            notification_id = create_notification_bead(
                self._db,
                worker_id=manager_id,
                message_id=message.id,
                channel_id=channel.id,
                priority=1,
            )

            return MessageResult(
                success=True,
                message_id=message.id,
                channel_id=channel.id,
                notification_id=notification_id,
            )

        except Exception as e:
            return MessageResult(success=False, error=str(e))

    def create_direct_channel(
        self,
        worker_id_1: str,
        worker_id_2: str,
        name: Optional[str] = None,
    ) -> MessageResult:
        """Create a direct channel between two workers."""
        from ..queries import create_channel, subscribe_to_channel

        try:
            channel_name = name or f"dm-{worker_id_1}-{worker_id_2}"
            channel = create_channel(self._db, name=channel_name, channel_type="direct")
            subscribe_to_channel(self._db, channel.id, worker_id_1)
            subscribe_to_channel(self._db, channel.id, worker_id_2)
            return MessageResult(success=True, channel_id=channel.id)
        except Exception as e:
            return MessageResult(success=False, error=str(e))

    def send_message(
        self,
        channel_id: str,
        from_worker_id: str,
        content: str,
        priority: int = 2,
        time_sensitivity: str = "whenever",
    ) -> MessageResult:
        """Send a message to a channel."""
        from ..queries import create_message

        try:
            message = create_message(
                self._db,
                channel_id=channel_id,
                from_worker_id=from_worker_id,
                content=content,
                priority=priority,
                time_sensitivity=time_sensitivity,
            )
            return MessageResult(success=True, message_id=message.id, channel_id=channel_id)
        except Exception as e:
            return MessageResult(success=False, error=str(e))

    def notify_worker(
        self,
        worker_id: str,
        message_id: str,
        channel_id: str,
        priority: int = 2,
    ) -> MessageResult:
        """Create a notification for a worker about a message."""
        from ..notifications import create_notification_bead

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
            return MessageResult(success=False, error=str(e))


__all__ = [
    "BoardMessageCreator",
    "MessagingService",
    "MessageResult",
]
