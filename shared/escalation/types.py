"""Escalation value-object types: enums, config dataclasses, queue entries.

EscalationConfig (the larger config dataclass with load_from_yaml) lives
in config.py to keep this file focused on small data shapes.
EscalationManager (the orchestrator) lives in manager.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from shared.escalation.interface import EscalationResponse


class EscalationState(Enum):
    """State of an escalation in the queue."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    TIMEOUT = "timeout"
    FAILED = "failed"

@dataclass
class EscalationPathLevel:
    """
    A single level in an escalation path.

    Attributes:
        level: Numeric level in the escalation path (1-based).
        to: Target for escalation (direct_manager, skip_level_manager, ceo, board, or worker_id).
        after_minutes: Minutes after which this level triggers.
        priority_bump: Amount to increase priority when escalating to this level.
    """

    level: int
    to: str
    after_minutes: int
    priority_bump: int = 0


@dataclass
class RetryPolicy:
    """
    Retry policy for failed escalation operations.

    Attributes:
        max_retries: Maximum number of retry attempts.
        backoff: Backoff strategy (linear, exponential, fixed).
        base_delay_minutes: Base delay between retries in minutes.
        max_delay_minutes: Maximum delay between retries.
    """

    max_retries: int = 3
    backoff: str = "exponential"
    base_delay_minutes: int = 15
    max_delay_minutes: int = 120


@dataclass
class NotificationSettings:
    """
    Settings for escalation notifications.

    Attributes:
        notify_original_assignee: Notify the original assignee on escalation.
        notify_escalation_target: Notify the escalation target.
        create_bead: Create a bead to track the escalation.
        include_context: Include work item context in notification.
        channel: Channel for notifications (None = direct message).
        notify_escalation_chain: Notify all workers in escalation chain on resolution.
    """

    notify_original_assignee: bool = True
    notify_escalation_target: bool = True
    create_bead: bool = True
    include_context: bool = True
    channel: str | None = None
    notify_escalation_chain: bool = True


@dataclass
class TimeoutWarningSettings:
    """
    Settings for timeout warnings before escalation.

    Attributes:
        enabled: Whether to send warnings before escalation.
        warning_before_minutes: Minutes before escalation to send warning.
        notify_assignee: Notify assignee of impending escalation.
    """

    enabled: bool = True
    warning_before_minutes: int = 15
    notify_assignee: bool = True


@dataclass
class AutoEscalationSettings:
    """
    Settings for automatic escalation checks.

    Attributes:
        enabled: Whether automatic escalation is enabled.
        check_interval_minutes: How often to check for escalation triggers.
        escalatable_states: Work states that can trigger escalation.
        exempt_states: Work states exempt from escalation.
    """

    enabled: bool = True
    check_interval_minutes: int = 5
    escalatable_states: list[str] = field(
        default_factory=lambda: ["open", "in_progress", "blocked"]
    )
    exempt_states: list[str] = field(
        default_factory=lambda: ["draft", "review", "closed"]
    )


@dataclass
class BoardInterventionSettings:
    """
    Settings for board intervention thresholds.

    Attributes:
        consecutive_ceo_escalations: Escalations to CEO before board notification.
        org_wide_escalation_threshold: Percentage of org work items escalated threshold.
        threshold_window_minutes: Time window for org-wide threshold check.
    """

    consecutive_ceo_escalations: int = 3
    org_wide_escalation_threshold: float = 0.25
    threshold_window_minutes: int = 1440

@dataclass
class EscalationEntry:
    """
    An escalation in the queue.

    Attributes:
        id: Unique identifier for this escalation.
        worker_id: Worker who initiated the escalation.
        issue: Description of the problem.
        context: Additional context data.
        state: Current state of the escalation.
        created_at: When the escalation was created.
        timeout_at: When auto-escalation should trigger.
        current_target: Current escalation target in the path.
        escalation_path: Full path through hierarchy.
        attempts: Number of resolution attempts.
        response: Final response if resolved.
    """

    id: str
    worker_id: str
    issue: str
    context: dict[str, Any]
    state: EscalationState = EscalationState.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    timeout_at: datetime | None = None
    current_target: str | None = None
    escalation_path: list[str] = field(default_factory=list)
    attempts: int = 0
    response: EscalationResponse | None = None


@dataclass
class EscalationHistoryEntry:
    """
    A completed escalation for history tracking.

    Attributes:
        id: Escalation ID.
        worker_id: Originating worker.
        issue: Problem description.
        state: Final state.
        created_at: When created.
        resolved_at: When resolved (if applicable).
        resolved_by: Who resolved it (if applicable).
        escalation_path: Path taken through hierarchy.
        attempts: Total attempts made.
    """

    id: str
    worker_id: str
    issue: str
    state: EscalationState
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None
    escalation_path: list[str]
    attempts: int


class NotificationHandler(Protocol):
    """Protocol for notification system integration."""

    def notify(self, escalation: EscalationEntry, event: str) -> None:
        """
        Send a notification about an escalation event.

        Args:
            escalation: The escalation entry.
            event: Event type (created, timeout, resolved, failed).
        """
        ...


class InMemoryNotificationHandler:
    """
    In-memory notification handler for testing.

    Stores all notifications for inspection in tests.
    """

    def __init__(self) -> None:
        """Initialize the handler."""
        self.notifications: list[tuple[EscalationEntry, str]] = []

    def notify(self, escalation: EscalationEntry, event: str) -> None:
        """Store the notification."""
        self.notifications.append((escalation, event))

    def clear(self) -> None:
        """Clear all notifications."""
        self.notifications.clear()

    def get_events(self, escalation_id: str) -> list[str]:
        """Get all events for an escalation."""
        return [event for entry, event in self.notifications if entry.id == escalation_id]
