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
from .utils import (
    run_notification_cleanup,
    create_notification_bead,
    get_worker_notifications,
    get_pending_notifications,
    count_pending_notifications,
    mark_notification_read,
)

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
    "run_notification_cleanup",
    "create_notification_bead",
    "get_worker_notifications",
    "get_pending_notifications",
    "count_pending_notifications",
    "mark_notification_read",
]
