"""Escalation notification handler that bridges escalations to board notifications.

Converts escalation events into board notifications and dispatches them
through the multi-channel notification system.
"""

import logging
from typing import Optional

from shared.escalation.manager import EscalationEntry, NotificationHandler

from .channels import BoardNotification, NotificationPriority
from .dispatcher import NotificationDispatcher

_logger = logging.getLogger(__name__)


class EscalationNotificationHandler(NotificationHandler):
    """Handles escalation events by sending board notifications.

    Bridges the escalation system to the board notification system,
    converting escalation events into appropriate notifications based
    on event type and escalation context.
    """

    def __init__(self, dispatcher: NotificationDispatcher):
        """Initialize the handler.

        Args:
            dispatcher: Notification dispatcher to send through
        """
        self.dispatcher = dispatcher

    def notify(self, escalation: EscalationEntry, event: str) -> None:
        """Send notification about an escalation event.

        Args:
            escalation: The escalation entry
            event: Event type (created, timeout, resolved, failed)
        """
        # Map event type to priority and message
        priority, title, message = self._format_notification(escalation, event)

        # Create board notification
        notification = BoardNotification(
            title=title,
            message=message,
            priority=priority,
            worker_id=escalation.worker_id,
            metadata={
                "escalation_id": escalation.id,
                "event_type": event,
                "escalation_target": escalation.current_target,
                "escalation_path": escalation.escalation_path,
                "attempts": escalation.attempts,
                "issue": escalation.issue[:200],  # Truncate long issues
            },
        )

        # Dispatch through channels
        results = self.dispatcher.dispatch(notification)

        # Log results
        success_count = sum(
            1 for r in results.values() if r.name == "SUCCESS"
        )
        _logger.info(
            "Escalation %s notification sent (%s): %d/%d channels successful",
            event,
            escalation.id,
            success_count,
            len(results),
        )

    def _format_notification(
        self, escalation: EscalationEntry, event: str
    ) -> tuple[NotificationPriority, str, str]:
        """Format notification based on event type.

        Args:
            escalation: The escalation entry
            event: Event type

        Returns:
            Tuple of (priority, title, message)
        """
        worker = escalation.worker_id
        target = escalation.current_target or "unknown"
        issue_summary = escalation.issue[:100]

        if event == "created":
            priority = NotificationPriority.NORMAL
            title = f"New Escalation: {worker}"
            message = (
                f"Worker {worker} escalated an issue to {target}:\n\n"
                f"Issue: {issue_summary}\n\n"
                f"Escalation path: {' → '.join(escalation.escalation_path)}"
            )

        elif event == "timeout":
            priority = NotificationPriority.HIGH
            title = f"Escalation Timeout: {worker}"
            message = (
                f"Escalation from {worker} timed out at level {target}.\n\n"
                f"Issue: {issue_summary}\n\n"
                f"Auto-escalating to next level in path."
            )

        elif event == "resolved":
            priority = NotificationPriority.INFO
            title = f"Escalation Resolved: {worker}"
            resolved_by = (
                escalation.response.escalated_to
                if escalation.response
                else "unknown"
            )
            message = (
                f"Escalation from {worker} was resolved by {resolved_by}.\n\n"
                f"Issue: {issue_summary}\n\n"
                f"Attempts: {escalation.attempts}"
            )

        elif event == "failed":
            priority = NotificationPriority.URGENT
            title = f"Escalation Failed: {worker}"
            message = (
                f"Escalation from {worker} failed after {escalation.attempts} attempts.\n\n"
                f"Issue: {issue_summary}\n\n"
                f"Path attempted: {' → '.join(escalation.escalation_path)}\n\n"
                f"⚠️ Board intervention may be required."
            )

        else:
            # Unknown event type
            priority = NotificationPriority.NORMAL
            title = f"Escalation Event: {event}"
            message = (
                f"Unknown escalation event '{event}' for {worker}:\n\n"
                f"Issue: {issue_summary}"
            )

        return priority, title, message
