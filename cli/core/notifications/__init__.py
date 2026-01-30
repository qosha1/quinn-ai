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
]
