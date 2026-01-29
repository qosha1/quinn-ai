"""
Notification system for QuinnAI CLI.

Implements ephemeral beads for message notifications. When a message is sent
to a channel, notification beads are created for each subscriber (except the
sender). These notifications are closed when actioned and purged after a
configurable retention period.

Per CLAUDE.md: "Notifications = ephemeral work units (beads) pointing to messages.
Cleaned up after actioned."
"""

import sqlite3
from typing import Optional

from .db import Database
from .queries.notification import (
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
from .queries import get_channel_subscribers


# Re-export for backward compatibility
__all__ = [
    "NotificationBead",
    "DEFAULT_RETENTION_DAYS",
    "create_notification_bead",
    "get_notification_bead",
    "get_worker_notifications",
    "get_pending_notifications",
    "count_pending_notifications",
    "mark_notification_read",
    "mark_notification_actioned",
    "close_notification",
    "close_notifications_for_message",
    "acknowledge_notification",
    "cleanup_old_notifications",
    "cleanup_expired_notifications",
    "cleanup_orphaned_notifications",
    "run_notification_cleanup",
    "create_notifications_for_message",
]


def create_notifications_for_message(
    db: Database,
    message_id: str,
    channel_id: str,
    from_worker_id: str,
    priority: int = 2,
) -> list[NotificationBead]:
    """Create notification beads for all channel subscribers except the sender.

    This is the main entry point for the notification flow. When a message
    is sent to a channel, call this function to notify all subscribers.

    Args:
        db: Database instance
        message_id: The message that was sent
        channel_id: The channel the message was sent to
        from_worker_id: The sender (will not receive notification)
        priority: Priority for the notifications

    Returns:
        List of created notification beads
    """
    subscribers = get_channel_subscribers(db, channel_id)
    notifications = []

    for worker_id in subscribers:
        # Don't notify the sender
        if worker_id == from_worker_id:
            continue

        try:
            notif = create_notification_bead(
                db, worker_id, message_id, channel_id, priority
            )
            notifications.append(notif)
        except sqlite3.IntegrityError as e:
            # Ignore duplicate notifications (UNIQUE constraint)
            if "UNIQUE constraint" in str(e):
                pass
            else:
                raise

    return notifications


def get_pending_notifications(
    db: Database,
    worker_id: str,
    limit: int = 50,
) -> list[NotificationBead]:
    """Get pending (unread) notifications for a worker.

    Convenience function for getting actionable notifications.

    Args:
        db: Database instance
        worker_id: Worker ID
        limit: Max notifications to return

    Returns:
        List of pending notification beads
    """
    return get_worker_notifications(db, worker_id, status="pending", limit=limit)


def acknowledge_notification(db: Database, notification_id: str) -> bool:
    """Acknowledge a notification, marking it as closed.

    This is the primary function for workers to dismiss notifications after
    processing them. Per CLAUDE.md: "Notifications = ephemeral tasks (beads
    pointing to messages). Single central SQLite for everything."

    Acknowledged notifications are closed and will be cleaned up during the
    next cleanup cycle.

    Args:
        db: Database instance
        notification_id: Notification ID to acknowledge

    Returns:
        True if acknowledged, False if not found or already closed
    """
    return close_notification(db, notification_id)


def run_notification_cleanup(
    db: Database,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, int]:
    """Run full notification cleanup.

    This is the main cleanup entry point that runs all cleanup operations.
    Per CLAUDE.md: "Notifications = ephemeral tasks (beads pointing to messages)."

    Cleanup includes:
    - Closed notifications older than retention period
    - Expired notifications (past their expires_at time)
    - Orphaned notifications (message or worker deleted)

    Note: Messages are NEVER deleted - they are permanent knowledge.
    Only the ephemeral notification beads are cleaned up.

    Args:
        db: Database instance
        retention_days: Days to retain closed notifications

    Returns:
        Dict with counts of cleaned up notifications by type
    """
    old_count = cleanup_old_notifications(db, retention_days)
    expired_count = cleanup_expired_notifications(db)
    orphan_count = cleanup_orphaned_notifications(db)

    return {
        "old_notifications_purged": old_count,
        "expired_notifications_purged": expired_count,
        "orphaned_notifications_purged": orphan_count,
        "total_purged": old_count + expired_count + orphan_count,
    }
