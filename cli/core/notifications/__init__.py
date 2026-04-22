"""Notification system for board communication.

Provides multi-channel notifications with priority routing, rate limiting,
and quiet hours support.
"""

from .channels import (
    BoardNotification,
    NotificationChannel,
    NotificationPriority,
    NotificationResult,
    FileQueueChannel,
    DesktopNotificationChannel,
    SlackWebhookChannel,
    EmailChannel,
)
from .dispatcher import NotificationDispatcher
from .board_notifier import BoardNotifier
from .config import create_board_notifier, load_notification_config
from .escalation_handler import EscalationNotificationHandler

# Import SQL-based notification creation and related types from queries
from ..queries.notification import (
    NotificationBead,
    DEFAULT_RETENTION_DAYS,
    create_notification_bead,
    get_notification_bead,
    get_worker_notifications,
    count_pending_notifications,
    mark_notification_read,
    mark_notification_actioned,
    close_notification,
    close_notifications_for_message,
    cleanup_old_notifications,
    cleanup_expired_notifications,
    cleanup_orphaned_notifications,
)
import sqlite3
from ..queries import get_channel_subscribers
from ..db import Database


def get_pending_notifications(
    db: Database,
    worker_id: str,
    limit: int = 50,
) -> list["NotificationBead"]:
    """Get pending (unread) notifications for a worker."""
    return get_worker_notifications(db, worker_id, status="pending", limit=limit)


def create_notifications_for_message(
    db: Database,
    message_id: str,
    channel_id: str,
    from_worker_id: str,
    priority: int = 2,
) -> list["NotificationBead"]:
    """Create notification beads for all channel subscribers except the sender."""
    subscribers = get_channel_subscribers(db, channel_id)
    notifications = []

    for worker_id in subscribers:
        if worker_id == from_worker_id:
            continue
        try:
            notif = create_notification_bead(db, worker_id, message_id, channel_id, priority)
            notifications.append(notif)
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint" not in str(e):
                raise

    return notifications


def acknowledge_notification(db: Database, notification_id: str) -> bool:
    """Acknowledge a notification, marking it as closed."""
    return close_notification(db, notification_id)


def run_notification_cleanup(
    db: Database,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, int]:
    """Run full notification cleanup (old, expired, orphaned beads)."""
    old_count = cleanup_old_notifications(db, retention_days)
    expired_count = cleanup_expired_notifications(db)
    orphan_count = cleanup_orphaned_notifications(db)
    return {
        "old_notifications_purged": old_count,
        "expired_notifications_purged": expired_count,
        "orphaned_notifications_purged": orphan_count,
        "total_purged": old_count + expired_count + orphan_count,
    }


__all__ = [
    "BoardNotification",
    "NotificationChannel",
    "NotificationPriority",
    "NotificationResult",
    "FileQueueChannel",
    "DesktopNotificationChannel",
    "SlackWebhookChannel",
    "EmailChannel",
    "NotificationDispatcher",
    "BoardNotifier",
    "create_board_notifier",
    "load_notification_config",
    "EscalationNotificationHandler",
    # Notification bead types and constants
    "NotificationBead",
    "DEFAULT_RETENTION_DAYS",
    # CRUD operations
    "create_notification_bead",
    "get_notification_bead",
    "get_worker_notifications",
    "get_pending_notifications",
    "count_pending_notifications",
    # State transitions
    "mark_notification_read",
    "mark_notification_actioned",
    "close_notification",
    "close_notifications_for_message",
    "acknowledge_notification",
    # Cleanup
    "cleanup_old_notifications",
    "cleanup_expired_notifications",
    "cleanup_orphaned_notifications",
    "run_notification_cleanup",
    # Message integration
    "create_notifications_for_message",
]
