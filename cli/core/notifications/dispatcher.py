"""Notification dispatcher with routing, rate limiting, and policies.

Handles routing notifications to appropriate channels based on priority,
with rate limiting and quiet hours support.
"""

import logging
from collections import deque
from datetime import datetime, time, timedelta
from typing import List, Optional, Dict

from .channels import (
    NotificationChannel,
    BoardNotification,
    NotificationPriority,
    NotificationResult,
)

_logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Routes notifications to channels with rate limiting and policies."""

    def __init__(
        self,
        channels: List[NotificationChannel],
        max_per_minute: int = 5,
        max_per_hour: int = 20,
        batch_window_seconds: int = 60,
        quiet_hours_enabled: bool = False,
        quiet_hours_start: Optional[time] = None,
        quiet_hours_end: Optional[time] = None,
    ):
        """Initialize notification dispatcher.

        Args:
            channels: List of notification channels to use
            max_per_minute: Maximum notifications per minute
            max_per_hour: Maximum notifications per hour
            batch_window_seconds: Window for batching similar notifications
            quiet_hours_enabled: Whether to enforce quiet hours
            quiet_hours_start: Start of quiet hours (e.g., 22:00)
            quiet_hours_end: End of quiet hours (e.g., 07:00)
        """
        self.channels = channels
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self.batch_window_seconds = batch_window_seconds
        self.quiet_hours_enabled = quiet_hours_enabled
        self.quiet_hours_start = quiet_hours_start or time(22, 0)
        self.quiet_hours_end = quiet_hours_end or time(7, 0)

        # Rate limiting tracking
        self._recent_notifications: deque = deque()  # Timestamps of recent notifications
        self._pending_batch: Dict[str, BoardNotification] = {}  # Notifications waiting to batch

    def dispatch(self, notification: BoardNotification) -> Dict[str, NotificationResult]:
        """Dispatch notification to all appropriate channels.

        Args:
            notification: Notification to dispatch

        Returns:
            Dict mapping channel name to result
        """
        # Check rate limiting
        if not self._check_rate_limit():
            _logger.warning("Rate limit exceeded, notification dropped")
            return {"rate_limited": NotificationResult.SKIPPED}

        # Check quiet hours
        if self._is_quiet_hours() and notification.priority.value > NotificationPriority.HIGH.value:
            _logger.debug("Quiet hours active, non-urgent notification deferred")
            return {"quiet_hours": NotificationResult.SKIPPED}

        # Send to all available channels
        results = {}
        for channel in self.channels:
            if channel.is_available():
                try:
                    result = channel.send(notification)
                    results[channel.get_name()] = result
                    _logger.debug(f"Channel {channel.get_name()}: {result.value}")
                except Exception as e:
                    _logger.error(f"Channel {channel.get_name()} failed: {e}")
                    results[channel.get_name()] = NotificationResult.FAILED
            else:
                results[channel.get_name()] = NotificationResult.SKIPPED

        # Track for rate limiting
        self._recent_notifications.append(datetime.now())

        return results

    def _check_rate_limit(self) -> bool:
        """Check if rate limit allows sending.

        Returns:
            True if can send, False if rate limited
        """
        now = datetime.now()

        # Clean old timestamps
        one_minute_ago = now - timedelta(minutes=1)
        one_hour_ago = now - timedelta(hours=1)

        # Remove timestamps older than 1 hour
        while self._recent_notifications and self._recent_notifications[0] < one_hour_ago:
            self._recent_notifications.popleft()

        # Count recent notifications
        recent_minute = sum(1 for ts in self._recent_notifications if ts > one_minute_ago)
        recent_hour = len(self._recent_notifications)

        # Check limits
        if recent_minute >= self.max_per_minute:
            _logger.warning(f"Per-minute rate limit exceeded: {recent_minute}/{self.max_per_minute}")
            return False

        if recent_hour >= self.max_per_hour:
            _logger.warning(f"Per-hour rate limit exceeded: {recent_hour}/{self.max_per_hour}")
            return False

        return True

    def _is_quiet_hours(self) -> bool:
        """Check if currently in quiet hours.

        Returns:
            True if in quiet hours
        """
        if not self.quiet_hours_enabled:
            return False

        now_time = datetime.now().time()

        # Handle quiet hours that span midnight
        if self.quiet_hours_start < self.quiet_hours_end:
            # Normal case: 22:00 - 07:00 doesn't span midnight in comparison
            # But 22:00 > 07:00, so this is the span case
            return now_time >= self.quiet_hours_start or now_time < self.quiet_hours_end
        else:
            # Quiet hours within same day: 08:00 - 17:00
            return self.quiet_hours_start <= now_time < self.quiet_hours_end

    def batch_similar(
        self,
        notification: BoardNotification,
        similarity_key: str,
    ) -> Optional[BoardNotification]:
        """Batch similar notifications within time window.

        Args:
            notification: Notification to potentially batch
            similarity_key: Key to group similar notifications

        Returns:
            Batched notification if window elapsed, None if still batching
        """
        now = datetime.now()

        # Check if we have a pending batch for this key
        if similarity_key in self._pending_batch:
            existing = self._pending_batch[similarity_key]
            time_diff = (now - existing.timestamp).total_seconds()

            if time_diff < self.batch_window_seconds:
                # Still within batch window, update the notification
                existing.message += f"\n\n{notification.message}"
                if existing.metadata is None:
                    existing.metadata = {}
                existing.metadata["batch_count"] = existing.metadata.get("batch_count", 1) + 1
                _logger.debug(f"Batched notification with key: {similarity_key}")
                return None

            # Window elapsed, return the batched notification
            batched = self._pending_batch.pop(similarity_key)
            return batched

        # No existing batch, start a new one
        self._pending_batch[similarity_key] = notification
        return None

    def flush_batches(self) -> List[BoardNotification]:
        """Flush all pending batched notifications.

        Returns:
            List of batched notifications
        """
        batched = list(self._pending_batch.values())
        self._pending_batch.clear()
        return batched
