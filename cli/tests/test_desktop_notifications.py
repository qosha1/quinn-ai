"""Tests for desktop notification channel."""

import platform
from unittest.mock import Mock, patch, call

import pytest

from cli.core.notifications import (
    DesktopNotificationChannel,
    BoardNotification,
    NotificationPriority,
    NotificationResult,
)


class TestDesktopNotificationChannel:
    """Tests for desktop notification channel."""

    def test_create_channel(self):
        """Test creating desktop notification channel."""
        channel = DesktopNotificationChannel()
        assert channel.get_name() == "desktop"
        assert channel.min_priority == NotificationPriority.NORMAL

    def test_create_channel_with_min_priority(self):
        """Test creating channel with minimum priority filter."""
        channel = DesktopNotificationChannel(min_priority=NotificationPriority.HIGH)
        assert channel.min_priority == NotificationPriority.HIGH

    def test_priority_filtering(self):
        """Test that low priority notifications are skipped."""
        channel = DesktopNotificationChannel(min_priority=NotificationPriority.HIGH)

        # INFO priority should be skipped (higher value = lower priority)
        notification = BoardNotification(
            title="Test",
            message="Low priority",
            priority=NotificationPriority.INFO,
        )

        result = channel.send(notification)
        assert result == NotificationResult.SKIPPED

    @pytest.mark.skipif(
        platform.system() != "Darwin",
        reason="macOS-specific test"
    )
    @patch("subprocess.run")
    def test_macos_notification(self, mock_run):
        """Test macOS notification sending."""
        mock_run.return_value = Mock(returncode=0)

        channel = DesktopNotificationChannel()
        notification = BoardNotification(
            title="Test Notification",
            message="This is a test message",
            priority=NotificationPriority.NORMAL,
        )

        result = channel.send(notification)

        assert result == NotificationResult.SUCCESS
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert "Test Notification" in args[2]

    @pytest.mark.skipif(
        platform.system() != "Darwin",
        reason="macOS-specific test"
    )
    @patch("subprocess.run")
    def test_macos_urgent_notification_with_sound(self, mock_run):
        """Test macOS urgent notification includes sound."""
        mock_run.return_value = Mock(returncode=0)

        channel = DesktopNotificationChannel()
        notification = BoardNotification(
            title="Urgent Alert",
            message="Critical issue",
            priority=NotificationPriority.URGENT,
        )

        result = channel.send(notification)

        assert result == NotificationResult.SUCCESS
        args = mock_run.call_args[0][0]
        script = args[2]
        # Urgent notifications should have sound
        assert "sound name" in script

    @pytest.mark.skipif(
        platform.system() != "Darwin",
        reason="macOS-specific test"
    )
    @patch("subprocess.run")
    def test_macos_notification_with_worker_context(self, mock_run):
        """Test macOS notification includes worker subtitle."""
        mock_run.return_value = Mock(returncode=0)

        channel = DesktopNotificationChannel()
        notification = BoardNotification(
            title="Worker Update",
            message="Worker needs attention",
            priority=NotificationPriority.HIGH,
            worker_id="worker-123",
        )

        result = channel.send(notification)

        assert result == NotificationResult.SUCCESS
        args = mock_run.call_args[0][0]
        script = args[2]
        # Should include worker ID in subtitle
        assert "worker-123" in script

    @pytest.mark.skipif(
        platform.system() != "Darwin",
        reason="macOS-specific test"
    )
    @patch("subprocess.run")
    def test_macos_message_truncation(self, mock_run):
        """Test long messages are truncated for macOS."""
        mock_run.return_value = Mock(returncode=0)

        channel = DesktopNotificationChannel()
        long_message = "A" * 300  # Longer than 200 char limit

        notification = BoardNotification(
            title="Test",
            message=long_message,
            priority=NotificationPriority.NORMAL,
        )

        result = channel.send(notification)

        assert result == NotificationResult.SUCCESS
        args = mock_run.call_args[0][0]
        script = args[2]
        # Message should be truncated
        assert len(script) < len(long_message) + 100  # Account for script boilerplate

    @pytest.mark.skipif(
        platform.system() != "Darwin",
        reason="macOS-specific test"
    )
    @patch("subprocess.run")
    def test_macos_notification_escapes_quotes(self, mock_run):
        """Test quotes in message are escaped."""
        mock_run.return_value = Mock(returncode=0)

        channel = DesktopNotificationChannel()
        notification = BoardNotification(
            title='Test "quoted" title',
            message='Message with "quotes"',
            priority=NotificationPriority.NORMAL,
        )

        result = channel.send(notification)

        assert result == NotificationResult.SUCCESS
        args = mock_run.call_args[0][0]
        script = args[2]
        # Quotes should be escaped
        assert '\\"' in script

    @pytest.mark.skipif(
        platform.system() != "Darwin",
        reason="macOS-specific test"
    )
    @patch("subprocess.run")
    def test_macos_notification_failure(self, mock_run):
        """Test handling of macOS notification failure."""
        mock_run.return_value = Mock(returncode=1, stderr="Error")

        channel = DesktopNotificationChannel()
        notification = BoardNotification(
            title="Test",
            message="Test",
            priority=NotificationPriority.NORMAL,
        )

        result = channel.send(notification)

        assert result == NotificationResult.FAILED

    def test_is_available(self):
        """Test availability check."""
        channel = DesktopNotificationChannel()
        # Should return True/False based on platform
        available = channel.is_available()
        assert isinstance(available, bool)
