"""Notification channels for board communication.

Implements multiple notification channels with graceful degradation:
- FileQueueChannel: Always available, writes to shared/board/inbox/
- DesktopNotificationChannel: Platform-specific (macOS/Linux/Windows)
- SlackWebhookChannel: Optional webhook integration
- EmailChannel: Optional SMTP integration
"""

import json
import logging
import platform
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any

_logger = logging.getLogger(__name__)


class NotificationPriority(Enum):
    """Notification priority levels."""
    URGENT = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    INFO = 4


class NotificationResult(Enum):
    """Result of notification send attempt."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class BoardNotification:
    """Notification to be sent to board."""
    title: str
    message: str
    priority: NotificationPriority
    worker_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @abstractmethod
    def send(self, notification: BoardNotification) -> NotificationResult:
        """Send notification through this channel.

        Args:
            notification: Notification to send

        Returns:
            Result of send attempt
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if channel is available/configured.

        Returns:
            True if channel can be used
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get channel name for logging.

        Returns:
            Channel name
        """
        pass


class FileQueueChannel(NotificationChannel):
    """File-based notification queue (always available).

    Writes notifications as JSON files to shared/board/inbox/.
    Board UI reads these on launch.
    """

    def __init__(self, org_path: Path, retention_days: int = 7):
        """Initialize file queue channel.

        Args:
            org_path: Path to organization directory
            retention_days: Days to retain notifications
        """
        self.inbox_dir = org_path / "storage" / "shared" / "board" / "inbox"
        self.retention_days = retention_days
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, notification: BoardNotification) -> NotificationResult:
        """Write notification to inbox as JSON file."""
        try:
            # Create filename with timestamp and priority
            timestamp_str = notification.timestamp.strftime("%Y%m%d_%H%M%S")
            priority_str = notification.priority.name.lower()
            filename = f"{timestamp_str}_{priority_str}_{notification.worker_id or 'system'}.json"
            
            filepath = self.inbox_dir / filename

            # Write notification as JSON
            notification_data = {
                "title": notification.title,
                "message": notification.message,
                "priority": notification.priority.value,
                "worker_id": notification.worker_id,
                "timestamp": notification.timestamp.isoformat(),
                "metadata": notification.metadata or {},
            }

            filepath.write_text(json.dumps(notification_data, indent=2))
            _logger.debug(f"Wrote notification to {filepath}")

            # Clean up old notifications
            self._cleanup_old_notifications()

            return NotificationResult.SUCCESS

        except Exception as e:
            _logger.error(f"Failed to write notification to file queue: {e}")
            return NotificationResult.FAILED

    def is_available(self) -> bool:
        """File queue is always available."""
        return True

    def get_name(self) -> str:
        return "file_queue"

    def _cleanup_old_notifications(self) -> None:
        """Remove notifications older than retention period."""
        try:
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(days=self.retention_days)

            for filepath in self.inbox_dir.glob("*.json"):
                # Parse timestamp from filename
                timestamp_str = filepath.stem.split("_")[0] + "_" + filepath.stem.split("_")[1]
                try:
                    file_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    if file_time < cutoff:
                        filepath.unlink()
                        _logger.debug(f"Deleted old notification: {filepath.name}")
                except (ValueError, IndexError):
                    # Can't parse timestamp, skip
                    pass

        except Exception as e:
            _logger.warning(f"Failed to cleanup old notifications: {e}")


class DesktopNotificationChannel(NotificationChannel):
    """Desktop notification channel (platform-specific).

    Uses native notification systems:
    - macOS: osascript (AppleScript)
    - Linux: notify-send (libnotify)
    - Windows: PowerShell toast notifications
    """

    def __init__(self, min_priority: NotificationPriority = NotificationPriority.NORMAL):
        """Initialize desktop notification channel.

        Args:
            min_priority: Minimum priority to send (filters lower priority)
        """
        self.min_priority = min_priority
        self.system = platform.system()

    def send(self, notification: BoardNotification) -> NotificationResult:
        """Send desktop notification using platform-specific method."""
        # Check priority threshold
        if notification.priority.value > self.min_priority.value:
            return NotificationResult.SKIPPED

        if not self.is_available():
            return NotificationResult.SKIPPED

        try:
            if self.system == "Darwin":  # macOS
                return self._send_macos(notification)
            elif self.system == "Linux":
                return self._send_linux(notification)
            elif self.system == "Windows":
                return self._send_windows(notification)
            else:
                _logger.warning(f"Desktop notifications not supported on {self.system}")
                return NotificationResult.SKIPPED

        except Exception as e:
            _logger.warning(f"Failed to send desktop notification: {e}")
            return NotificationResult.FAILED

    def is_available(self) -> bool:
        """Check if platform-specific notification tool is available."""
        try:
            if self.system == "Darwin":
                # macOS always has osascript
                return True
            elif self.system == "Linux":
                # Check for notify-send
                result = subprocess.run(["which", "notify-send"], capture_output=True)
                return result.returncode == 0
            elif self.system == "Windows":
                # Windows always has PowerShell
                return True
            return False
        except Exception:
            return False

    def get_name(self) -> str:
        return "desktop"

    def _send_macos(self, notification: BoardNotification) -> NotificationResult:
        """Send notification via macOS notification center with enhanced features."""
        # Escape quotes in strings
        title = notification.title.replace('"', '\\"')

        # Truncate message for notification (keep full message in metadata)
        message = notification.message[:200]  # macOS notification limit
        message = message.replace('"', '\\"').replace('\n', ' ')

        # Build AppleScript with sound and subtitle
        script_parts = [f'display notification "{message}" with title "{title}"']

        # Add subtitle for worker context
        if notification.worker_id:
            subtitle = f"Worker: {notification.worker_id}"
            script_parts[0] = script_parts[0].replace('"', f'" subtitle "{subtitle}" with title "', 1)

        # Add sound for urgent/high priority
        if notification.priority in (NotificationPriority.URGENT, NotificationPriority.HIGH):
            script_parts[0] += ' sound name "Submarine"'  # Built-in macOS sound

        script = script_parts[0]

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            _logger.debug(f"Sent macOS notification (priority: {notification.priority.name})")
            return NotificationResult.SUCCESS
        else:
            _logger.warning(f"macOS notification failed: {result.stderr}")
            return NotificationResult.FAILED

    def _send_linux(self, notification: BoardNotification) -> NotificationResult:
        """Send notification via libnotify (notify-send)."""
        # Map priority to urgency
        urgency_map = {
            NotificationPriority.URGENT: "critical",
            NotificationPriority.HIGH: "critical",
            NotificationPriority.NORMAL: "normal",
            NotificationPriority.LOW: "low",
            NotificationPriority.INFO: "low",
        }
        urgency = urgency_map.get(notification.priority, "normal")

        result = subprocess.run(
            [
                "notify-send",
                "-u", urgency,
                notification.title,
                notification.message,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            _logger.debug("Sent Linux notification")
            return NotificationResult.SUCCESS
        else:
            _logger.warning(f"Linux notification failed: {result.stderr}")
            return NotificationResult.FAILED

    def _send_windows(self, notification: BoardNotification) -> NotificationResult:
        """Send notification via Windows PowerShell toast."""
        # PowerShell script for toast notification
        script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        
        $template = @"
        <toast>
            <visual>
                <binding template="ToastGeneric">
                    <text>{notification.title}</text>
                    <text>{notification.message}</text>
                </binding>
            </visual>
        </toast>
        "@
        
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("QuinnAI").Show($toast)
        """

        result = subprocess.run(
            ["powershell", "-Command", script],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            _logger.debug("Sent Windows notification")
            return NotificationResult.SUCCESS
        else:
            _logger.warning(f"Windows notification failed: {result.stderr}")
            return NotificationResult.FAILED


class SlackWebhookChannel(NotificationChannel):
    """Slack webhook notification channel (optional)."""

    def __init__(
        self,
        webhook_url: str,
        min_priority: NotificationPriority = NotificationPriority.HIGH,
    ):
        """Initialize Slack webhook channel.

        Args:
            webhook_url: Slack webhook URL
            min_priority: Minimum priority to send
        """
        self.webhook_url = webhook_url
        self.min_priority = min_priority

    def send(self, notification: BoardNotification) -> NotificationResult:
        """Send notification to Slack via webhook."""
        # Check priority threshold
        if notification.priority.value > self.min_priority.value:
            return NotificationResult.SKIPPED

        if not self.is_available():
            return NotificationResult.SKIPPED

        try:
            import requests

            # Format Slack message
            payload = {
                "text": f"*{notification.title}*",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": notification.title,
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": notification.message,
                        },
                    },
                ],
            }

            if notification.worker_id:
                payload["blocks"].append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Worker: `{notification.worker_id}`",
                        }
                    ],
                })

            response = requests.post(self.webhook_url, json=payload, timeout=10)

            if response.status_code == 200:
                _logger.debug("Sent Slack notification")
                return NotificationResult.SUCCESS
            else:
                _logger.warning(f"Slack notification failed: {response.status_code}")
                return NotificationResult.FAILED

        except ImportError:
            _logger.warning("requests library not installed, cannot send Slack notifications")
            return NotificationResult.FAILED
        except Exception as e:
            _logger.warning(f"Failed to send Slack notification: {e}")
            return NotificationResult.FAILED

    def is_available(self) -> bool:
        """Check if Slack webhook is configured."""
        return bool(self.webhook_url and self.webhook_url.startswith("https://hooks.slack.com/"))

    def get_name(self) -> str:
        return "slack"


class EmailChannel(NotificationChannel):
    """Email notification channel (optional)."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        from_addr: str,
        to_addr: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        min_priority: NotificationPriority = NotificationPriority.URGENT,
    ):
        """Initialize email channel.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            from_addr: From email address
            to_addr: To email address
            username: SMTP username (optional)
            password: SMTP password (optional)
            min_priority: Minimum priority to send
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.username = username
        self.password = password
        self.min_priority = min_priority

    def send(self, notification: BoardNotification) -> NotificationResult:
        """Send notification via email."""
        # Check priority threshold
        if notification.priority.value > self.min_priority.value:
            return NotificationResult.SKIPPED

        if not self.is_available():
            return NotificationResult.SKIPPED

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[QuinnAI] {notification.title}"
            msg["From"] = self.from_addr
            msg["To"] = self.to_addr

            # Plain text body
            text = f"{notification.title}\n\n{notification.message}"
            if notification.worker_id:
                text += f"\n\nWorker: {notification.worker_id}"
            
            msg.attach(MIMEText(text, "plain"))

            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(msg)

            _logger.debug("Sent email notification")
            return NotificationResult.SUCCESS

        except ImportError:
            _logger.warning("Email libraries not available")
            return NotificationResult.FAILED
        except Exception as e:
            _logger.warning(f"Failed to send email notification: {e}")
            return NotificationResult.FAILED

    def is_available(self) -> bool:
        """Check if email is configured."""
        return bool(self.smtp_host and self.smtp_port and self.from_addr and self.to_addr)

    def get_name(self) -> str:
        return "email"
