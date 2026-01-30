"""Notification utility functions.

Provides helper functions for notification cleanup and bead creation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List

_logger = logging.getLogger(__name__)


def run_notification_cleanup(db, retention_days: int) -> dict:
    """Clean up old notifications from the database.

    Args:
        db: Database instance
        retention_days: Number of days to retain notifications

    Returns:
        Dict with cleanup results: {"total_purged": int}
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        # Clean up old notification beads (if notifications table exists)
        result = db.execute(
            """DELETE FROM beads
               WHERE type = 'notification'
               AND created_at < ?""",
            (cutoff_date.isoformat(),)
        )
        db.connection.commit()

        purged = result.rowcount if result else 0
        _logger.info(f"Purged {purged} old notifications (older than {retention_days} days)")

        return {"total_purged": purged}

    except Exception as e:
        _logger.warning(f"Failed to run notification cleanup: {e}")
        return {"total_purged": 0}


def create_notification_bead(
    db,
    worker_id: str,
    message_id: str,
    channel_id: str,
    priority: int,
) -> Optional[str]:
    """Create a notification bead for a worker.

    Args:
        db: Database instance
        worker_id: Worker to notify
        message_id: Message ID
        channel_id: Channel ID
        priority: Priority level (0-4)

    Returns:
        Bead ID if created, None otherwise
    """
    try:
        from core.bd_wrapper import run_bd
        from pathlib import Path

        # Get org path from db
        db_path = Path(db.db_path)
        org_path = db_path.parent.parent

        # Create notification bead via bd CLI
        result = run_bd(
            org_path,
            [
                "create",
                f"--title=New message in channel",
                f"--description=You have a new message (message_id: {message_id})",
                "--type=notification",
                f"--priority={priority}",
                f"--assignee={worker_id}",
            ],
            worker_id="system",
        )

        if result.returncode == 0:
            _logger.debug(f"Created notification bead for worker {worker_id}")
            return message_id  # Return something as bead ID
        else:
            _logger.warning(f"Failed to create notification bead: {result.stderr}")
            return None

    except Exception as e:
        _logger.warning(f"Failed to create notification bead: {e}")
        return None


def get_worker_notifications(db, worker_id: str, limit: int = 50) -> List[dict]:
    """Get notifications for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        limit: Maximum number of notifications to return

    Returns:
        List of notification dicts
    """
    try:
        rows = db.fetchall(
            """SELECT * FROM beads
               WHERE type = 'notification'
               AND assignee = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (worker_id, limit)
        )
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        _logger.warning(f"Failed to get worker notifications: {e}")
        return []


def get_pending_notifications(db, worker_id: str) -> List[dict]:
    """Get pending (unread) notifications for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of pending notification dicts
    """
    try:
        rows = db.fetchall(
            """SELECT * FROM beads
               WHERE type = 'notification'
               AND assignee = ?
               AND status = 'open'
               ORDER BY created_at DESC""",
            (worker_id,)
        )
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        _logger.warning(f"Failed to get pending notifications: {e}")
        return []


def count_pending_notifications(db, worker_id: str) -> int:
    """Count pending notifications for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Number of pending notifications
    """
    try:
        row = db.fetchone(
            """SELECT COUNT(*) as count FROM beads
               WHERE type = 'notification'
               AND assignee = ?
               AND status = 'open'""",
            (worker_id,)
        )
        return row["count"] if row else 0
    except Exception as e:
        _logger.warning(f"Failed to count pending notifications: {e}")
        return 0


def mark_notification_read(db, notification_id: str) -> bool:
    """Mark a notification as read.

    Args:
        db: Database instance
        notification_id: Notification ID

    Returns:
        True if marked, False otherwise
    """
    try:
        db.execute(
            """UPDATE beads
               SET status = 'closed'
               WHERE id = ?
               AND type = 'notification'""",
            (notification_id,)
        )
        db.connection.commit()
        return True
    except Exception as e:
        _logger.warning(f"Failed to mark notification read: {e}")
        return False
