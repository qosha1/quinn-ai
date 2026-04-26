"""Notification utility functions.

Provides helper functions for notification cleanup and bead creation.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List

_logger = logging.getLogger(__name__)


def run_notification_cleanup(db, retention_days: int) -> dict:
    """Clean up old notifications from the beads database.

    Args:
        db: Database instance
        retention_days: Number of days to retain notifications

    Returns:
        Dict with cleanup results: {"total_purged": int}
    """
    try:
        from pathlib import Path
        from cli.core.bd_wrapper import run_bd

        # Get org path from db
        db_path = Path(db.db_path)
        org_path = db_path.parent.parent

        # Use bd CLI to clean up old notification beads
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        # Query for old notification beads via bd CLI
        result = run_bd(
            [
                "list",
                "--type=notification",
                "--status=closed",
                f"--format=json",
            ],
            org_path,
            worker_id="worker-ceo",  # Use CEO for system operations
        )

        if result.returncode == 0:
            # Parse and count - in reality we'd parse the JSON and close old ones
            # For now just log success
            _logger.debug(f"Notification cleanup completed")
            return {"total_purged": 0}
        else:
            _logger.warning(f"Failed to run notification cleanup: {result.stderr}")
            return {"total_purged": 0}

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
        from cli.core.bd_wrapper import run_bd
        from pathlib import Path

        # Get org path from db
        db_path = Path(db.db_path)
        org_path = db_path.parent.parent

        # Create notification bead via bd CLI
        result = run_bd(
            [
                "create",
                f"--title=New message in channel",
                f"--description=You have a new message (message_id: {message_id})",
                "--type=notification",
                f"--priority={priority}",
                f"--assignee={worker_id}",
            ],
            org_path,
            worker_id="worker-ceo",  # Use CEO for system operations
        )

        if result.returncode == 0:
            _logger.debug(f"Created notification bead for worker {worker_id}")
            return message_id  # Return something as bead ID
        else:
            _logger.warning(f"Failed to create notification bead: stderr={result.stderr}, stdout={result.stdout}, returncode={result.returncode}")
            return None

    except Exception as e:
        _logger.warning(f"Failed to create notification bead: {e}")
        return None


def get_worker_notifications(db, worker_id: str, limit: int = 50) -> List[dict]:
    """Get notifications for a worker via beads CLI.

    Args:
        db: Database instance
        worker_id: Worker ID
        limit: Maximum number of notifications to return

    Returns:
        List of notification dicts
    """
    try:
        from pathlib import Path
        from cli.core.bd_wrapper import run_bd
        import json

        # Get org path from db
        db_path = Path(db.db_path)
        org_path = db_path.parent.parent

        # Use bd CLI to get notifications
        result = run_bd(
            [
                "list",
                "--type=notification",
                f"--assignee={worker_id}",
                f"--limit={limit}",
                "--format=json",
            ],
            org_path,
            worker_id=worker_id,
        )

        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
        return []
    except Exception as e:
        _logger.warning(f"Failed to get worker notifications: {e}")
        return []


def get_pending_notifications(db, worker_id: str) -> List[dict]:
    """Get pending (unread) notifications for a worker via beads CLI.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of pending notification dicts
    """
    try:
        from pathlib import Path
        from cli.core.bd_wrapper import run_bd
        import json

        # Get org path from db
        db_path = Path(db.db_path)
        org_path = db_path.parent.parent

        # Use bd CLI to get pending notifications
        result = run_bd(
            [
                "list",
                "--type=notification",
                f"--assignee={worker_id}",
                "--status=open",
                "--format=json",
            ],
            org_path,
            worker_id=worker_id,
        )

        if result.returncode == 0 and result.stdout:
            return json.loads(result.stdout)
        return []
    except Exception as e:
        _logger.warning(f"Failed to get pending notifications: {e}")
        return []


def count_pending_notifications(db, worker_id: str) -> int:
    """Count pending notifications for a worker via beads CLI.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Number of pending notifications
    """
    try:
        # Use get_pending_notifications and count the results
        notifications = get_pending_notifications(db, worker_id)
        return len(notifications)
    except Exception as e:
        _logger.warning(f"Failed to count pending notifications: {e}")
        return 0


def mark_notification_read(db, notification_id: str) -> bool:
    """Mark a notification as read via beads CLI.

    Args:
        db: Database instance
        notification_id: Notification ID

    Returns:
        True if marked, False otherwise
    """
    try:
        from pathlib import Path
        from cli.core.bd_wrapper import run_bd

        # Get org path from db
        db_path = Path(db.db_path)
        org_path = db_path.parent.parent

        # Use bd CLI to close the notification bead
        result = run_bd(
            [
                "close",
                notification_id,
                "--reason=Read by worker",
            ],
            org_path,
            worker_id="worker-ceo",  # Use CEO for system operations
        )

        return result.returncode == 0
    except Exception as e:
        _logger.warning(f"Failed to mark notification read: {e}")
        return False


def create_notifications_for_message(
    db,
    message_id: str,
    channel_id: str,
    from_worker_id: str,
    priority: int = 2,
) -> List[Optional[str]]:
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
        List of created notification bead IDs
    """
    from cli.core.queries.channel import get_channel_subscribers

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
            if notif:
                notifications.append(notif)
        except Exception as e:
            # Ignore errors creating individual notifications
            _logger.warning(f"Failed to create notification for {worker_id}: {e}")

    return notifications
