"""
Organization connection interface.

Defines the contract for connecting to and interacting with running orgs.
The board TUI is independent of org lifecycle - orgs can run without board,
board can connect/disconnect at will.

Key principle: No one waits. All interactions are async or observable state.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any


class OrgStatus(Enum):
    """Organization lifecycle status."""
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"


class WorkerStatus(Enum):
    """Worker lifecycle status."""
    PENDING = "pending"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    OFFBOARDING = "offboarding"
    TERMINATED = "terminated"


class SessionState(Enum):
    """Worker session runtime state."""
    STARTING = "starting"
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"


@dataclass
class WorkerInfo:
    """Information about a worker for display in the board UI.

    Contains only what the board needs to see - not the full Worker model.
    """
    id: str
    name: str
    role: str
    team_name: str
    status: WorkerStatus
    session_state: Optional[SessionState]
    tmux_session_name: Optional[str]
    manager_id: Optional[str]
    current_task: Optional[str] = None
    is_ceo: bool = False
    session_mode: Optional[str] = None  # "autonomous" or "interactive"


@dataclass
class OrgInfo:
    """Information about an org for display in the board UI."""
    path: Path
    name: str
    status: OrgStatus
    ceo_worker_id: Optional[str]
    worker_count: int
    active_session_count: int
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]


@dataclass
class BudgetSummary:
    """Budget summary for display."""
    total_allocated: float
    total_spent: float
    total_available: float
    period_start: datetime
    period_end: datetime
    spend_today: float = 0.0
    spend_this_week: float = 0.0


@dataclass
class Message:
    """A message in the board inbox."""
    id: str
    from_worker_id: str
    from_worker_name: str
    channel_name: str
    content: str
    priority: int
    created_at: datetime
    is_read: bool = False
    requires_response: bool = False


@dataclass
class OKRInfo:
    """OKR information for display."""
    id: str
    title: str
    description: Optional[str]
    owner_name: str
    owner_id: str
    status: str
    parent_id: Optional[str]
    key_results: list[dict[str, Any]] = field(default_factory=list)
    due_date: Optional[datetime] = None
    children_count: int = 0


@dataclass
class HealthIssue:
    """A health issue detected in the org."""
    worker_id: str
    worker_name: str
    issue_type: str  # "no_okrs", "no_tasks", "no_activity", "crashed_session"
    severity: str  # "info", "warning", "error"
    message: str


@dataclass
class HealthStatus:
    """Organization health status."""
    overall_score: str  # "healthy", "warning", "critical"
    issues: list[HealthIssue] = field(default_factory=list)
    workers_with_issues: int = 0
    total_workers: int = 0
    last_checked: Optional[datetime] = None


@dataclass
class WorkerDetail:
    """Rich per-worker context for the worker detail panel."""
    worker_id: str
    tools: list[dict]
    storage_tree: dict
    active_beads: list[dict]
    recent_messages: list[dict]
    briefing_excerpt: str


class OrgConnection(ABC):
    """Abstract interface for connecting to organizations.

    Provides read access to org state and ability to perform board actions.
    The connection is stateless from the org's perspective - connecting
    doesn't change anything, disconnecting doesn't affect the org.

    All methods that return data should be fast (cached or indexed queries).
    Methods that trigger actions (send_message, start_org) may be slower.
    """

    @property
    @abstractmethod
    def org_path(self) -> Path:
        """Path to the connected org."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected to an org."""
        ...

    # ==================
    # ORG STATE
    # ==================

    @abstractmethod
    def get_org_info(self) -> OrgInfo:
        """Get current org information.

        Returns:
            OrgInfo with current org state
        """
        ...

    @abstractmethod
    def get_budget_summary(self) -> BudgetSummary:
        """Get budget summary for the org.

        Returns:
            BudgetSummary with current budget state
        """
        ...

    @abstractmethod
    def get_health_status(self) -> HealthStatus:
        """Get organization health status.

        Checks for common issues:
        - Workers without OKRs
        - Workers without assigned tasks
        - Workers with no recent activity
        - Crashed sessions

        Returns:
            HealthStatus with overall score and list of issues
        """
        ...

    # ==================
    # WORKERS
    # ==================

    @abstractmethod
    def get_workers(self) -> list[WorkerInfo]:
        """Get all workers in the org.

        Returns:
            List of WorkerInfo sorted by hierarchy (CEO first)
        """
        ...

    @abstractmethod
    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """Get a specific worker by ID.

        Args:
            worker_id: Worker ID to look up

        Returns:
            WorkerInfo or None if not found
        """
        ...

    @abstractmethod
    def get_ceo(self) -> Optional[WorkerInfo]:
        """Get the CEO worker.

        Returns:
            WorkerInfo for CEO or None if org not initialized
        """
        ...

    @abstractmethod
    def get_recent_activity(
        self,
        minutes: int = 30,
        limit: int = 50,
    ) -> list[dict]:
        """Get recent activity from all workers.

        Reads activity logs from live/logs/activity/*.jsonl files.

        Args:
            minutes: How far back to look (in minutes)
            limit: Maximum number of activity entries to return

        Returns:
            List of activity dictionaries sorted by timestamp (most recent first)
        """
        ...

    # ==================
    # MESSAGES (BOARD INBOX)
    # ==================

    @abstractmethod
    def get_board_messages(self, unread_only: bool = False) -> list[Message]:
        """Get messages escalated to the board.

        These are messages in channels/threads where the board is mentioned
        or messages explicitly escalated for board review.

        Args:
            unread_only: If True, only return unread messages

        Returns:
            List of messages sorted by priority then recency
        """
        ...

    @abstractmethod
    def get_unread_count(self) -> int:
        """Get count of unread board messages.

        Returns:
            Number of unread messages
        """
        ...

    @abstractmethod
    def send_board_response(
        self,
        message_id: str,
        response: str,
    ) -> bool:
        """Send a board response to a message.

        This is async - the response is queued and the worker will
        receive a notification when they next check.

        Args:
            message_id: ID of message being responded to
            response: Response content

        Returns:
            True if response was queued successfully
        """
        ...

    @abstractmethod
    def mark_message_read(self, message_id: str) -> bool:
        """Mark a message as read.

        Args:
            message_id: ID of message to mark

        Returns:
            True if marked successfully
        """
        ...

    # ==================
    # OKRS
    # ==================

    @abstractmethod
    def get_okrs(self, owner_id: Optional[str] = None) -> list[OKRInfo]:
        """Get OKRs, optionally filtered by owner.

        Args:
            owner_id: If provided, only return OKRs owned by this worker

        Returns:
            List of OKRs in hierarchy order
        """
        ...

    # ==================
    # ORG ACTIONS
    # ==================

    @abstractmethod
    def start_org(self) -> bool:
        """Start the org (if stopped or initialized).

        Returns:
            True if org was started successfully
        """
        ...

    @abstractmethod
    def stop_org(self) -> bool:
        """Stop the org gracefully.

        Returns:
            True if org was stopped successfully
        """
        ...

    @abstractmethod
    def restart_org(self) -> tuple[bool, str]:
        """Restart the org (stop then start).

        Returns:
            Tuple of (success: bool, message: str)
        """
        ...

    # ==================
    # BOARD INTERVENTIONS
    # ==================

    @abstractmethod
    def pause_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Pause a worker.

        Args:
            worker_id: Worker ID to pause
            reason: Optional reason for pausing

        Returns:
            True if worker was paused successfully
        """
        ...

    @abstractmethod
    def resume_worker(self, worker_id: str) -> bool:
        """Resume a paused worker.

        Args:
            worker_id: Worker ID to resume

        Returns:
            True if worker was resumed successfully
        """
        ...

    @abstractmethod
    def fire_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        """Terminate a worker immediately.

        Args:
            worker_id: Worker ID to terminate
            reason: Optional reason for termination

        Returns:
            True if worker was terminated successfully
        """
        ...

    # ==================
    # CEO BRIEFING
    # ==================

    @abstractmethod
    def send_ceo_briefing(self, briefing_content: str) -> bool:
        """Send briefing to CEO as high-priority message.

        Args:
            briefing_content: Markdown content for briefing

        Returns:
            True if briefing was sent successfully
        """
        ...

    @abstractmethod
    def get_current_briefing(self) -> Optional[str]:
        """Get current CEO briefing from config.

        Returns:
            Briefing markdown content or None if no briefing exists
        """
        ...

    @abstractmethod
    def update_briefing(self, briefing_content: str) -> bool:
        """Update CEO briefing and notify CEO.

        Args:
            briefing_content: New briefing markdown content

        Returns:
            True if briefing was updated and CEO notified successfully
        """
        ...

    def get_worker_detail(self, worker_id: str) -> Optional["WorkerDetail"]:
        """Return rich per-worker context for the detail panel.

        Args:
            worker_id: Worker ID

        Returns:
            WorkerDetail or None if worker not found
        """
        return None

    # ==================
    # SUBSCRIPTIONS (FOR REAL-TIME UPDATES)
    # ==================

    def subscribe_to_updates(
        self,
        callback: Callable[[str, Any], None],
    ) -> Callable[[], None]:
        """Subscribe to real-time org updates.

        The callback receives (event_type, data) for each update.
        Returns an unsubscribe function.

        Args:
            callback: Function called with (event_type, event_data)

        Returns:
            Function to call to unsubscribe
        """
        # Default: no-op subscription (polling fallback)
        return lambda: None
