"""Notification configuration loader.

Loads notification settings from config/notifications.yaml and
creates configured NotificationDispatcher and BoardNotifier instances.
"""

import logging
from datetime import time
from pathlib import Path
from typing import Optional

import yaml

from .channels import (
    NotificationChannel,
    NotificationPriority,
    FileQueueChannel,
    DesktopNotificationChannel,
    SlackWebhookChannel,
    EmailChannel,
)
from .dispatcher import NotificationDispatcher
from .board_notifier import BoardNotifier

_logger = logging.getLogger(__name__)


def load_notification_config(org_path: Path) -> Optional[dict]:
    """Load notification configuration from YAML file.

    Args:
        org_path: Path to organization directory

    Returns:
        Configuration dict or None if file doesn't exist
    """
    config_path = org_path / "config" / "notifications.yaml"

    if not config_path.exists():
        _logger.debug("No notifications.yaml found, using defaults")
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        _logger.warning(f"Failed to load notifications.yaml: {e}")
        return None


def create_board_notifier(org_path: Path) -> Optional[BoardNotifier]:
    """Create a configured BoardNotifier instance.

    Args:
        org_path: Path to organization directory

    Returns:
        BoardNotifier instance or None if notifications disabled
    """
    config = load_notification_config(org_path)

    if not config:
        # Create minimal notifier with file queue only
        channels = [FileQueueChannel(org_path)]
        dispatcher = NotificationDispatcher(channels)
        return BoardNotifier(dispatcher)

    # Check if notifications are enabled
    settings = config.get("settings", {})
    if not settings.get("enabled", True):
        _logger.info("Notifications disabled in config")
        return None

    # Create channels based on config
    channels = []
    channel_configs = config.get("channels", {})

    # File queue (always available)
    file_queue_config = channel_configs.get("file_queue", {})
    if file_queue_config.get("enabled", True):
        retention_days = file_queue_config.get("retention_days", 7)
        channels.append(FileQueueChannel(org_path, retention_days=retention_days))

    # Desktop notifications
    desktop_config = channel_configs.get("desktop", {})
    if desktop_config.get("enabled", True):
        min_priority_str = desktop_config.get("min_priority", "normal")
        min_priority = _parse_priority(min_priority_str)
        channels.append(DesktopNotificationChannel(min_priority=min_priority))

    # Slack webhook
    slack_config = channel_configs.get("slack", {})
    if slack_config.get("enabled", False):
        webhook_url = slack_config.get("webhook_url", "")
        if webhook_url:
            min_priority_str = slack_config.get("min_priority", "high")
            min_priority = _parse_priority(min_priority_str)
            channels.append(SlackWebhookChannel(webhook_url, min_priority=min_priority))

    # Email
    email_config = channel_configs.get("email", {})
    if email_config.get("enabled", False):
        smtp_host = email_config.get("smtp_host", "")
        smtp_port = email_config.get("smtp_port", 587)
        from_addr = email_config.get("from_address", "")
        to_addr = email_config.get("to_address", "")

        if smtp_host and from_addr and to_addr:
            min_priority_str = email_config.get("min_priority", "urgent")
            min_priority = _parse_priority(min_priority_str)
            username = email_config.get("username")
            password = email_config.get("password")

            channels.append(EmailChannel(
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                from_addr=from_addr,
                to_addr=to_addr,
                username=username,
                password=password,
                min_priority=min_priority,
            ))

    # Create dispatcher with rate limiting and quiet hours
    rate_limit = settings.get("rate_limit", {})
    max_per_minute = rate_limit.get("max_per_minute", 5)
    max_per_hour = rate_limit.get("max_per_hour", 20)

    batch_window = settings.get("batch_window_seconds", 60)

    quiet_hours = settings.get("quiet_hours", {})
    quiet_hours_enabled = quiet_hours.get("enabled", False)
    quiet_hours_start = _parse_time(quiet_hours.get("start", "22:00"))
    quiet_hours_end = _parse_time(quiet_hours.get("end", "07:00"))

    dispatcher = NotificationDispatcher(
        channels=channels,
        max_per_minute=max_per_minute,
        max_per_hour=max_per_hour,
        batch_window_seconds=batch_window,
        quiet_hours_enabled=quiet_hours_enabled,
        quiet_hours_start=quiet_hours_start,
        quiet_hours_end=quiet_hours_end,
    )

    return BoardNotifier(dispatcher)


def _parse_priority(priority_str: str) -> NotificationPriority:
    """Parse priority string to enum.

    Args:
        priority_str: Priority string (urgent, high, normal, low, info)

    Returns:
        NotificationPriority enum value
    """
    priority_map = {
        "urgent": NotificationPriority.URGENT,
        "high": NotificationPriority.HIGH,
        "normal": NotificationPriority.NORMAL,
        "low": NotificationPriority.LOW,
        "info": NotificationPriority.INFO,
    }
    return priority_map.get(priority_str.lower(), NotificationPriority.NORMAL)


def _parse_time(time_str: str) -> time:
    """Parse time string to time object.

    Args:
        time_str: Time string in HH:MM format

    Returns:
        time object
    """
    try:
        hour, minute = map(int, time_str.split(":"))
        return time(hour, minute)
    except Exception:
        return time(22, 0)  # Default to 10 PM
