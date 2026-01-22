"""
OrgEscalation: Escalation implementation using org-chart hierarchy.

Routes escalations through the organizational hierarchy, creating
beads for tracking and notifying the board for human oversight.
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections import deque
from datetime import datetime
from typing import Any, Callable

from shared.wrkr.beads.client import BdClient
from shared.wrkr.beads.types import BeadsPriority, BeadsType
from shared.wrkr.escalation.interface import EscalationInterface, EscalationResponse
from shared.wrkr.escalation.hierarchical import (
    HierarchicalRouter,
    OrgTopology,
)
from shared.wrkr.org.topology import BeadsOrgLoader, OrgWorker

logger = logging.getLogger(__name__)


class OrgEscalation:
    """
    Escalation handler that routes through org hierarchy.

    Implements EscalationInterface by:
    - Using HierarchicalRouter for path determination
    - Creating beads to track escalations
    - Delegating to worker-specific handlers
    - Notifying board when escalation reaches top

    Attributes:
        worker_id: ID of the worker this handler serves.
        topology: The organizational hierarchy.
        router: Router for determining escalation paths.
    """

    def __init__(
        self,
        worker_id: str,
        topology: OrgTopology,
        worker_handlers: dict[str, EscalationInterface] | None = None,
        board_notifier: BoardNotifier | None = None,
        bd_command: str = "bd",
        db_path: str | None = None,
        client: BdClient | None = None,
    ):
        """
        Initialize the org escalation handler.

        Args:
            worker_id: The worker ID this handler serves.
            topology: The organizational hierarchy.
            worker_handlers: Optional dict of worker_id -> EscalationInterface
                for routing to specific workers.
            board_notifier: Optional notifier for board escalations.
            bd_command: Path to bd command for creating escalation beads.
            db_path: Optional database path override.
            client: Optional BdClient instance (for dependency injection).
        """
        self._worker_id = worker_id
        self._topology = topology
        self._router = HierarchicalRouter(topology)
        self._worker_handlers = worker_handlers or {}
        self._board_notifier = board_notifier
        self._client = client or BdClient(bd_command=bd_command, db_path=db_path)

    @property
    def worker_id(self) -> str:
        """The worker ID this handler serves."""
        return self._worker_id

    def _create_escalation_bead(
        self,
        issue: str,
        context: dict[str, Any],
        escalated_to: str,
    ) -> str | None:
        """
        Create a beads issue to track the escalation.

        Args:
            issue: Description of the escalated problem.
            context: Context information.
            escalated_to: Who was escalated to.

        Returns:
            The created issue ID, or None if creation failed.
        """
        metadata = {
            "escalation_from": self._worker_id,
            "escalation_to": escalated_to,
            "escalation_path": context.get("escalation_path", []),
            "original_context": context,
            "escalated_at": datetime.now().isoformat(),
        }

        issue_id = self._client.create_issue(
            title=f"Escalation: {issue[:80]}",
            type=BeadsType.ESCALATION,
            priority=BeadsPriority.HIGH,
            metadata=metadata,
        )
        if not issue_id:
            logger.warning(
                "Failed to create escalation bead for %s -> %s",
                self._worker_id,
                escalated_to,
            )

        return issue_id

    def ask(self, issue: str, context: dict[str, Any]) -> EscalationResponse:
        """
        Escalate an issue through the org hierarchy.

        Routes through management chain using HierarchicalRouter,
        creating tracking beads and notifying board if needed.

        Args:
            issue: Description of the problem.
            context: Additional contextual information.

        Returns:
            EscalationResponse with resolution status and guidance.
        """
        # Add worker-specific escalators plus board handler
        escalators: dict[str, EscalationInterface] = dict(self._worker_handlers)

        # Add board handler if we have a notifier
        if self._board_notifier:
            escalators["board"] = BoardEscalation(self._board_notifier)

        # Route through hierarchy
        response = self._router.route(self._worker_id, issue, escalators)

        # Create tracking bead if escalation was handled
        if response.escalated_to:
            self._create_escalation_bead(issue, context, response.escalated_to)

        return response

    def report(self, summary: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Report progress to direct supervisor.

        Creates a report bead linked to the supervisor.

        Args:
            summary: Brief description of what is being reported.
            metadata: Optional additional data.
        """
        boss_id = self._topology.get_boss(self._worker_id)
        if not boss_id:
            return

        report_metadata = {
            "reporter": self._worker_id,
            "supervisor": boss_id,
            "reported_at": datetime.now().isoformat(),
            **(metadata or {}),
        }

        issue_id = self._client.create_issue(
            title=f"Report: {summary[:80]}",
            type=BeadsType.REPORT,
            priority=BeadsPriority.BACKLOG,
            metadata=report_metadata,
            ephemeral=True,
        )
        if not issue_id:
            logger.warning("Failed to create report bead from %s", self._worker_id)

    def can_handle(self, issue: str) -> bool:
        """
        Check if escalation path exists.

        Returns True if there's at least one handler in the escalation
        path that might be able to handle the issue.

        Args:
            issue: Description of the problem.

        Returns:
            True if any handler in the path can potentially help.
        """
        path = self._router.get_escalation_path(self._worker_id)

        for target_id in path:
            handler = self._worker_handlers.get(target_id)
            if handler and handler.can_handle(issue):
                return True

        # Board can always handle as last resort
        if self._board_notifier and "board" in path:
            return True

        return False


class BoardNotifier:
    """
    Notifies board of escalations requiring human oversight.

    The board represents human operators who can intervene when
    the org cannot resolve an issue autonomously.
    """

    DEFAULT_MAX_NOTIFICATIONS = 1000

    def __init__(
        self,
        notification_callback: Callable[[str, dict[str, Any]], None] | None = None,
        bd_command: str = "bd",
        db_path: str | None = None,
        client: BdClient | None = None,
        max_notifications: int | None = None,
    ):
        """
        Initialize the board notifier.

        Args:
            notification_callback: Optional callback for immediate notification.
                Called with (issue, context) when board escalation occurs.
            bd_command: Path to bd command.
            db_path: Optional database path override.
            client: Optional BdClient instance (for dependency injection).
            max_notifications: Max notifications to keep in memory (prevents leak).
                Defaults to 1000. Older notifications are discarded.
        """
        self._callback = notification_callback
        self._client = client or BdClient(bd_command=bd_command, db_path=db_path)
        max_size = max_notifications or self.DEFAULT_MAX_NOTIFICATIONS
        self._notifications: deque[dict[str, Any]] = deque(maxlen=max_size)

    def notify(self, issue: str, context: dict[str, Any]) -> str | None:
        """
        Notify board of an escalation.

        Creates a high-priority board-attention bead and optionally
        invokes the notification callback.

        Args:
            issue: Description of the escalated problem.
            context: Escalation context.

        Returns:
            The notification bead ID, or None if creation failed.
        """
        notification = {
            "issue": issue,
            "context": context,
            "notified_at": datetime.now().isoformat(),
        }
        self._notifications.append(notification)

        # Create high-priority bead for board attention
        metadata = {
            "requires_human_review": True,
            "escalation_chain": context.get("escalation_path", []),
            "original_worker": context.get("worker_id"),
            "notified_at": notification["notified_at"],
        }

        bead_id = self._client.create_issue(
            title=f"BOARD: {issue[:70]}",
            type=BeadsType.BOARD_ESCALATION,
            priority=BeadsPriority.CRITICAL,
            metadata=metadata,
        )
        if not bead_id:
            logger.warning("Failed to create board escalation bead for: %s", issue[:50])

        # Invoke callback for immediate notification
        if self._callback:
            self._callback(issue, context)

        return bead_id

    def get_pending_notifications(self) -> list[dict[str, Any]]:
        """Get all pending board notifications."""
        return list(self._notifications)

    def clear_notifications(self) -> None:
        """Clear the pending notifications list."""
        self._notifications.clear()


class BoardEscalation:
    """
    EscalationInterface implementation for board escalations.

    Wraps BoardNotifier to implement the EscalationInterface protocol,
    allowing the board to be included in escalation routing.
    """

    def __init__(self, notifier: BoardNotifier):
        """
        Initialize board escalation handler.

        Args:
            notifier: The BoardNotifier to use for notifications.
        """
        self._notifier = notifier

    def ask(self, issue: str, context: dict[str, Any]) -> EscalationResponse:
        """
        Escalate to the board.

        Notifies board and returns a response indicating human
        review is required.

        Args:
            issue: Description of the problem.
            context: Escalation context.

        Returns:
            EscalationResponse marked as resolved (board will handle).
        """
        bead_id = self._notifier.notify(issue, context)

        return EscalationResponse(
            resolved=True,  # Board accepted the escalation
            guidance="Escalated to board for human review. "
            f"Tracking: {bead_id or 'pending'}",
            new_tasks=[],
            escalated_to="board",
        )

    def report(self, summary: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Report to board (informational only).

        Board reports are logged but don't create high-priority beads.

        Args:
            summary: Brief description.
            metadata: Optional additional data.
        """
        pass

    def can_handle(self, issue: str) -> bool:
        """
        Board can always handle escalations as last resort.

        Args:
            issue: Description of the problem.

        Returns:
            Always True.
        """
        return True


class InMemoryOrgEscalation:
    """
    In-memory org escalation handler for testing.

    Simulates org escalation without actual bd CLI calls.
    """

    def __init__(
        self,
        worker_id: str,
        topology: OrgTopology,
        worker_handlers: dict[str, EscalationInterface] | None = None,
    ):
        """
        Initialize the mock org escalation handler.

        Args:
            worker_id: The worker ID this handler serves.
            topology: The organizational hierarchy.
            worker_handlers: Optional dict of worker_id -> EscalationInterface.
        """
        self._worker_id = worker_id
        self._topology = topology
        self._router = HierarchicalRouter(topology)
        self._worker_handlers = worker_handlers or {}
        self._escalations: list[dict[str, Any]] = []
        self._reports: list[dict[str, Any]] = []
        self._board_notifications: list[dict[str, Any]] = []

    @property
    def worker_id(self) -> str:
        """The worker ID this handler serves."""
        return self._worker_id

    @property
    def escalations(self) -> list[dict[str, Any]]:
        """All recorded escalations."""
        return self._escalations

    @property
    def reports(self) -> list[dict[str, Any]]:
        """All recorded reports."""
        return self._reports

    @property
    def board_notifications(self) -> list[dict[str, Any]]:
        """All board notifications."""
        return self._board_notifications

    def ask(self, issue: str, context: dict[str, Any]) -> EscalationResponse:
        """
        Escalate through the org hierarchy (in-memory).

        Args:
            issue: Description of the problem.
            context: Additional contextual information.

        Returns:
            EscalationResponse with resolution status.
        """
        # Add in-memory board handler
        escalators: dict[str, EscalationInterface] = dict(self._worker_handlers)
        escalators["board"] = InMemoryBoardEscalation(self._board_notifications)

        # Route through hierarchy
        response = self._router.route(self._worker_id, issue, escalators)

        # Record escalation
        self._escalations.append({
            "issue": issue,
            "context": context,
            "response": response,
            "escalated_at": datetime.now().isoformat(),
        })

        return response

    def report(self, summary: str, metadata: dict[str, Any] | None = None) -> None:
        """Record a report."""
        self._reports.append({
            "summary": summary,
            "metadata": metadata,
            "reporter": self._worker_id,
            "reported_at": datetime.now().isoformat(),
        })

    def can_handle(self, issue: str) -> bool:
        """Check if escalation path exists."""
        path = self._router.get_escalation_path(self._worker_id)

        for target_id in path:
            handler = self._worker_handlers.get(target_id)
            if handler and handler.can_handle(issue):
                return True

        # Board always exists in path
        return "board" in path


class InMemoryBoardEscalation:
    """
    In-memory board escalation for testing.
    """

    def __init__(self, notification_store: list[dict[str, Any]]):
        """
        Initialize with a shared notification store.

        Args:
            notification_store: List to append notifications to.
        """
        self._notifications = notification_store

    def ask(self, issue: str, context: dict[str, Any]) -> EscalationResponse:
        """Escalate to board (in-memory)."""
        self._notifications.append({
            "issue": issue,
            "context": context,
            "notified_at": datetime.now().isoformat(),
        })

        return EscalationResponse(
            resolved=True,
            guidance="Escalated to board for human review.",
            new_tasks=[],
            escalated_to="board",
        )

    def report(self, summary: str, metadata: dict[str, Any] | None = None) -> None:
        """Board reports are no-op."""
        pass

    def can_handle(self, issue: str) -> bool:
        """Board can always handle."""
        return True
