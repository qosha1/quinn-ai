"""Notification bead queries.

Implements ephemeral beads for message notifications. When a message is sent
to a channel, notification beads are created for each subscriber (except the
sender). These notifications are closed when actioned and purged after a
configurable retention period.

Per CLAUDE.md: "Notifications = ephemeral work units (beads) pointing to messages.
Cleaned up after actioned."
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ..db import Database
from .common import generate_id


# Default retention days for closed notifications
DEFAULT_RETENTION_DAYS = 7


@dataclass
class NotificationBead:
    """Ephemeral bead pointing to a message notification."""
    id: str
    worker_id: str
    message_id: str
    channel_id: str
    status: str
    priority: int
    created_at: datetime
    read_at: Optional[datetime]
    actioned_at: Optional[datetime]
    closed_at: Optional[datetime]
    expires_at: Optional[datetime] = None


def create_notification_bead(
    db: Database,
    worker_id: str,
    message_id: str,
    channel_id: str,
    priority: int = 2,
    notification_id: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> NotificationBead:
    """Create a notification bead for a worker.

    Args:
        db: Database instance
        worker_id: Worker to notify
        message_id: Message ID being notified about
        channel_id: Channel the message is in
        priority: Notification priority (0-4)
        notification_id: Optional custom ID
        expires_at: Optional expiration datetime for auto-cleanup

    Returns:
        Created NotificationBead
    """
    if notification_id is None:
        notification_id = generate_id("notif")

    now = datetime.now()
    db.execute(
        """INSERT INTO notification_beads
           (id, worker_id, message_id, channel_id, status, priority, created_at, expires_at)
           VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)""",
        (notification_id, worker_id, message_id, channel_id, priority, now, expires_at)
    )
    db.connection.commit()

    return NotificationBead(
        id=notification_id,
        worker_id=worker_id,
        message_id=message_id,
        channel_id=channel_id,
        status="pending",
        priority=priority,
        created_at=now,
        read_at=None,
        actioned_at=None,
        closed_at=None,
        expires_at=expires_at,
    )


def get_notification_bead(db: Database, notification_id: str) -> Optional[NotificationBead]:
    """Get a notification bead by ID.

    Args:
        db: Database instance
        notification_id: Notification ID

    Returns:
        NotificationBead or None
    """
    row = db.fetchone(
        "SELECT * FROM notification_beads WHERE id = ?",
        (notification_id,)
    )
    if not row:
        return None

    return NotificationBead(
        id=row["id"],
        worker_id=row["worker_id"],
        message_id=row["message_id"],
        channel_id=row["channel_id"],
        status=row["status"],
        priority=row["priority"],
        created_at=row["created_at"],
        read_at=row["read_at"],
        actioned_at=row["actioned_at"],
        closed_at=row["closed_at"],
        expires_at=row["expires_at"],
    )


def get_worker_notifications(
    db: Database,
    worker_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[NotificationBead]:
    """Get notifications for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        status: Optional status filter ('pending', 'read', 'actioned', 'closed')
        limit: Max notifications to return
        offset: Offset for pagination

    Returns:
        List of notification beads, ordered by priority then creation time
    """
    if status:
        rows = db.fetchall(
            """SELECT * FROM notification_beads
               WHERE worker_id = ? AND status = ?
               ORDER BY priority ASC, created_at DESC
               LIMIT ? OFFSET ?""",
            (worker_id, status, limit, offset)
        )
    else:
        rows = db.fetchall(
            """SELECT * FROM notification_beads
               WHERE worker_id = ?
               ORDER BY priority ASC, created_at DESC
               LIMIT ? OFFSET ?""",
            (worker_id, limit, offset)
        )

    return [
        NotificationBead(
            id=row["id"],
            worker_id=row["worker_id"],
            message_id=row["message_id"],
            channel_id=row["channel_id"],
            status=row["status"],
            priority=row["priority"],
            created_at=row["created_at"],
            read_at=row["read_at"],
            actioned_at=row["actioned_at"],
            closed_at=row["closed_at"],
            expires_at=row["expires_at"],
        )
        for row in rows
    ]


def count_pending_notifications(db: Database, worker_id: str) -> int:
    """Count pending notifications for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Number of pending notifications
    """
    row = db.fetchone(
        "SELECT COUNT(*) as count FROM notification_beads WHERE worker_id = ? AND status = 'pending'",
        (worker_id,)
    )
    return row["count"] if row else 0


def mark_notification_read(db: Database, notification_id: str) -> bool:
    """Mark a notification as read.

    Args:
        db: Database instance
        notification_id: Notification ID

    Returns:
        True if updated, False if not found
    """
    now = datetime.now()
    cursor = db.execute(
        """UPDATE notification_beads
           SET status = 'read', read_at = ?
           WHERE id = ? AND status = 'pending'""",
        (now, notification_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def mark_notification_actioned(db: Database, notification_id: str) -> bool:
    """Mark a notification as actioned (worker took action on it).

    Args:
        db: Database instance
        notification_id: Notification ID

    Returns:
        True if updated, False if not found
    """
    now = datetime.now()
    cursor = db.execute(
        """UPDATE notification_beads
           SET status = 'actioned', actioned_at = ?, read_at = COALESCE(read_at, ?)
           WHERE id = ? AND status IN ('pending', 'read')""",
        (now, now, notification_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def close_notification(db: Database, notification_id: str) -> bool:
    """Close a notification bead.

    Closed notifications will be purged during cleanup.

    Args:
        db: Database instance
        notification_id: Notification ID

    Returns:
        True if closed, False if not found
    """
    now = datetime.now()
    cursor = db.execute(
        """UPDATE notification_beads
           SET status = 'closed', closed_at = ?,
               read_at = COALESCE(read_at, ?),
               actioned_at = COALESCE(actioned_at, ?)
           WHERE id = ? AND status != 'closed'""",
        (now, now, now, notification_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def close_notifications_for_message(
    db: Database,
    worker_id: str,
    message_id: str,
) -> int:
    """Close all notifications for a specific message and worker.

    Useful when a worker reads/actions a message directly.

    Args:
        db: Database instance
        worker_id: Worker ID
        message_id: Message ID

    Returns:
        Number of notifications closed
    """
    now = datetime.now()
    cursor = db.execute(
        """UPDATE notification_beads
           SET status = 'closed', closed_at = ?,
               read_at = COALESCE(read_at, ?),
               actioned_at = COALESCE(actioned_at, ?)
           WHERE worker_id = ? AND message_id = ? AND status != 'closed'""",
        (now, now, now, worker_id, message_id)
    )
    db.connection.commit()
    return cursor.rowcount


def cleanup_old_notifications(
    db: Database,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> int:
    """Purge closed notifications older than retention period.

    This should be run periodically (e.g., daily) to clean up old
    notification beads that are no longer needed.

    Args:
        db: Database instance
        retention_days: Days to retain closed notifications

    Returns:
        Number of notifications purged
    """
    cutoff = datetime.now() - timedelta(days=retention_days)
    cursor = db.execute(
        """DELETE FROM notification_beads
           WHERE status = 'closed' AND closed_at < ?""",
        (cutoff,)
    )
    db.connection.commit()
    return cursor.rowcount


def cleanup_expired_notifications(db: Database) -> int:
    """Delete notifications that have passed their expiration time.

    Per CLAUDE.md: "Notifications = ephemeral tasks (beads pointing to messages)."
    Notifications with an expires_at timestamp that has passed are automatically
    removed during cleanup, regardless of their status.

    Note: The underlying messages are NOT deleted - only the ephemeral notification
    beads are removed. Messages are permanent knowledge.

    Args:
        db: Database instance

    Returns:
        Number of expired notifications deleted
    """
    now = datetime.now()
    cursor = db.execute(
        """DELETE FROM notification_beads
           WHERE expires_at IS NOT NULL AND expires_at < ?""",
        (now,)
    )
    db.connection.commit()
    return cursor.rowcount


def cleanup_orphaned_notifications(db: Database) -> int:
    """Clean up notifications for messages or workers that no longer exist.

    This handles edge cases where foreign key cascades may not have fired.

    Args:
        db: Database instance

    Returns:
        Number of notifications cleaned up
    """
    # Delete notifications for messages that don't exist
    cursor = db.execute(
        """DELETE FROM notification_beads
           WHERE message_id NOT IN (SELECT id FROM messages)"""
    )
    count = cursor.rowcount

    # Delete notifications for workers that don't exist
    cursor = db.execute(
        """DELETE FROM notification_beads
           WHERE worker_id NOT IN (SELECT id FROM workers)"""
    )
    count += cursor.rowcount

    db.connection.commit()
    return count


__all__ = [
    "NotificationBead",
    "DEFAULT_RETENTION_DAYS",
    "create_notification_bead",
    "get_notification_bead",
    "get_worker_notifications",
    "count_pending_notifications",
    "mark_notification_read",
    "mark_notification_actioned",
    "close_notification",
    "close_notifications_for_message",
    "cleanup_old_notifications",
    "cleanup_expired_notifications",
    "cleanup_orphaned_notifications",
]
