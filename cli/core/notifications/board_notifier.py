"""Board notifier facade for domain events.

Provides high-level methods for notifying the board about specific events,
abstracting away the notification system details.
"""

import logging
from pathlib import Path
from typing import Optional

from .channels import BoardNotification, NotificationPriority
from .dispatcher import NotificationDispatcher

_logger = logging.getLogger(__name__)


class BoardNotifier:
    """High-level facade for board notifications."""

    def __init__(self, dispatcher: NotificationDispatcher):
        """Initialize board notifier.

        Args:
            dispatcher: Notification dispatcher to use
        """
        self.dispatcher = dispatcher

    def notify_worker_idle(
        self,
        worker_id: str,
        worker_name: str,
        idle_minutes: int,
        role: str,
    ) -> None:
        """Notify board that a worker is idle.

        Args:
            worker_id: Worker ID
            worker_name: Worker name
            idle_minutes: How long worker has been idle
            role: Worker role
        """
        notification = BoardNotification(
            title=f"Worker Idle: {worker_name}",
            message=(
                f"{worker_name} ({role}) has been idle for {idle_minutes} minutes.\n\n"
                f"**Actions:**\n"
                f"- Check their session: `qn wrkr logs {worker_id}`\n"
                f"- Review their tasks: `bd list --assignee={worker_id}`\n"
                f"- Send a message: `qn wrkr message {worker_id}`"
            ),
            priority=NotificationPriority.HIGH,
            worker_id=worker_id,
            metadata={"event": "worker_idle", "idle_minutes": idle_minutes},
        )

        self.dispatcher.dispatch(notification)

    def notify_worker_blocked(
        self,
        worker_id: str,
        worker_name: str,
        blocker_description: str,
    ) -> None:
        """Notify board that a worker is blocked.

        Args:
            worker_id: Worker ID
            worker_name: Worker name
            blocker_description: Description of what's blocking them
        """
        notification = BoardNotification(
            title=f"Worker Blocked: {worker_name}",
            message=(
                f"{worker_name} is blocked:\n\n"
                f"{blocker_description}\n\n"
                f"**Actions:**\n"
                f"- Review blocker details\n"
                f"- Provide guidance or unblock"
            ),
            priority=NotificationPriority.URGENT,
            worker_id=worker_id,
            metadata={"event": "worker_blocked"},
        )

        self.dispatcher.dispatch(notification)

    def notify_session_crash(
        self,
        worker_id: str,
        worker_name: str,
        error_message: str,
    ) -> None:
        """Notify board that a worker session crashed.

        Args:
            worker_id: Worker ID
            worker_name: Worker name
            error_message: Crash error message
        """
        notification = BoardNotification(
            title=f"Session Crashed: {worker_name}",
            message=(
                f"{worker_name}'s session has crashed.\n\n"
                f"**Error:** {error_message}\n\n"
                f"**Actions:**\n"
                f"- Check logs: `qn wrkr logs {worker_id}`\n"
                f"- Restart session: `qn org start --worker={worker_id}`"
            ),
            priority=NotificationPriority.URGENT,
            worker_id=worker_id,
            metadata={"event": "session_crash", "error": error_message},
        )

        self.dispatcher.dispatch(notification)

    def notify_okr_at_risk(
        self,
        okr_title: str,
        okr_id: str,
        reason: str,
    ) -> None:
        """Notify board that an OKR is at risk.

        Args:
            okr_title: OKR title
            okr_id: OKR ID
            reason: Why the OKR is at risk
        """
        notification = BoardNotification(
            title=f"OKR At Risk: {okr_title}",
            message=(
                f"OKR is at risk of not being completed:\n\n"
                f"**Reason:** {reason}\n\n"
                f"**Actions:**\n"
                f"- Review OKR: `qn org okr show {okr_id}`\n"
                f"- Adjust timeline or resources"
            ),
            priority=NotificationPriority.HIGH,
            metadata={"event": "okr_at_risk", "okr_id": okr_id},
        )

        self.dispatcher.dispatch(notification)

    def notify_work_completed(
        self,
        worker_id: str,
        worker_name: str,
        work_title: str,
        work_id: str,
    ) -> None:
        """Notify board that work has been completed.

        Args:
            worker_id: Worker ID
            worker_name: Worker name
            work_title: Work item title
            work_id: Work item ID
        """
        notification = BoardNotification(
            title=f"Work Completed: {work_title}",
            message=(
                f"{worker_name} completed: {work_title}\n\n"
                f"**Actions:**\n"
                f"- Review work: `bd show {work_id}`\n"
                f"- Approve or request changes"
            ),
            priority=NotificationPriority.NORMAL,
            worker_id=worker_id,
            metadata={"event": "work_completed", "work_id": work_id},
        )

        self.dispatcher.dispatch(notification)

    def notify_custom(
        self,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        worker_id: Optional[str] = None,
    ) -> None:
        """Send a custom notification to the board.

        Args:
            title: Notification title
            message: Notification message
            priority: Notification priority
            worker_id: Optional worker ID
        """
        notification = BoardNotification(
            title=title,
            message=message,
            priority=priority,
            worker_id=worker_id,
            metadata={"event": "custom"},
        )

        self.dispatcher.dispatch(notification)
