"""
EscalationManager: Centralized coordinator for escalation workflows.

This module provides a manager class that orchestrates escalations across
the organization, handling:
- Escalation queue management
- Timeout-based auto-escalation
- Integration with notification systems
- Escalation history tracking
- Config-driven behavior

The manager sits above the HierarchicalRouter and EscalationInterface,
coordinating the full lifecycle of escalations.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml

from shared.escalation.interface import EscalationInterface, EscalationResponse
from shared.escalation.hierarchical import HierarchicalRouter, OrgTopology

logger = logging.getLogger(__name__)


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
class EscalationConfig:
    """
    Configuration for escalation behavior.

    This class supports both simple programmatic configuration and loading
    from YAML files (like escalation.yaml). Use load_from_yaml() to load
    a full configuration including escalation paths, notification rules,
    and auto-escalation settings.

    Attributes:
        timeout_seconds: Default timeout before auto-escalation (default 300s).
        max_escalation_depth: Maximum levels to escalate before failing (default 10).
        auto_escalate_on_timeout: Whether to automatically escalate on timeout.
        retry_attempts: Number of retry attempts before escalating (default 1).
        enable_history: Whether to track escalation history (default True).
        max_history_size: Maximum history entries to retain (default 10000).
        max_queue_size: Maximum pending escalations (default 1000).
        escalation_paths: Named escalation paths (default, critical, blocked, etc.).
        retry_policy: Retry policy for failed operations.
        notification_settings: Settings for escalation notifications.
        timeout_warning: Settings for timeout warnings.
        auto_escalation: Settings for automatic escalation checks.
        board_intervention: Settings for board intervention thresholds.
    """

    timeout_seconds: int = 300
    max_escalation_depth: int = 10
    auto_escalate_on_timeout: bool = True
    retry_attempts: int = 1
    enable_history: bool = True
    max_history_size: int = 10000
    max_queue_size: int = 1000

    # Extended configuration from escalation.yaml
    escalation_paths: dict[str, list[EscalationPathLevel]] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    notification_settings: NotificationSettings = field(default_factory=NotificationSettings)
    timeout_warning: TimeoutWarningSettings = field(default_factory=TimeoutWarningSettings)
    auto_escalation: AutoEscalationSettings = field(default_factory=AutoEscalationSettings)
    board_intervention: BoardInterventionSettings = field(default_factory=BoardInterventionSettings)

    def get_path(self, path_name: str = "default") -> list[EscalationPathLevel]:
        """
        Get an escalation path by name.

        Args:
            path_name: Name of the path (default, critical, blocked, okr_linked).

        Returns:
            List of escalation levels for the path, or empty list if not found.
        """
        return self.escalation_paths.get(path_name, [])

    def get_timeout_for_level(
        self, path_name: str, level: int
    ) -> int | None:
        """
        Get the timeout in seconds for a specific level in a path.

        Args:
            path_name: Name of the escalation path.
            level: The level number (1-based).

        Returns:
            Timeout in seconds, or None if level not found.
        """
        for path_level in self.get_path(path_name):
            if path_level.level == level:
                return path_level.after_minutes * 60
        return None

    @classmethod
    def load_from_yaml(cls, path: str | Path) -> EscalationConfig:
        """
        Load escalation configuration from a YAML file.

        The YAML file should follow the structure defined in
        cli/config/escalation.yaml, including:
        - default_timeout_minutes
        - escalation_paths (default, critical, blocked, okr_linked)
        - retry_policy
        - notification_rules
        - auto_escalation
        - board_intervention

        Args:
            path: Path to the YAML configuration file.

        Returns:
            EscalationConfig populated from the YAML file.

        Raises:
            FileNotFoundError: If the YAML file doesn't exist.
            yaml.YAMLError: If the YAML is invalid.
        """
        path = Path(path)
        with path.open() as f:
            data = yaml.safe_load(f)

        # Parse escalation paths
        escalation_paths: dict[str, list[EscalationPathLevel]] = {}
        for path_name, levels in data.get("escalation_paths", {}).items():
            escalation_paths[path_name] = [
                EscalationPathLevel(
                    level=lvl["level"],
                    to=lvl["to"],
                    after_minutes=lvl["after_minutes"],
                    priority_bump=lvl.get("priority_bump", 0),
                )
                for lvl in levels
            ]

        # Parse retry policy
        retry_data = data.get("retry_policy", {})
        retry_policy = RetryPolicy(
            max_retries=retry_data.get("max_retries", 3),
            backoff=retry_data.get("backoff", "exponential"),
            base_delay_minutes=retry_data.get("base_delay_minutes", 15),
            max_delay_minutes=retry_data.get("max_delay_minutes", 120),
        )

        # Parse notification settings
        notif_data = data.get("notification_rules", {})
        esc_notif = notif_data.get("escalation", {})
        res_notif = notif_data.get("resolution", {})
        notification_settings = NotificationSettings(
            notify_original_assignee=esc_notif.get("notify_original_assignee", True),
            notify_escalation_target=esc_notif.get("notify_escalation_target", True),
            create_bead=esc_notif.get("create_bead", True),
            include_context=esc_notif.get("include_context", True),
            channel=esc_notif.get("channel"),
            notify_escalation_chain=res_notif.get("notify_escalation_chain", True),
        )

        # Parse timeout warning settings
        warn_data = notif_data.get("timeout_warning", {})
        timeout_warning = TimeoutWarningSettings(
            enabled=warn_data.get("enabled", True),
            warning_before_minutes=warn_data.get("warning_before_minutes", 15),
            notify_assignee=warn_data.get("notify_assignee", True),
        )

        # Parse auto-escalation settings
        auto_data = data.get("auto_escalation", {})
        auto_escalation = AutoEscalationSettings(
            enabled=auto_data.get("enabled", True),
            check_interval_minutes=auto_data.get("check_interval_minutes", 5),
            escalatable_states=auto_data.get(
                "escalatable_states", ["open", "in_progress", "blocked"]
            ),
            exempt_states=auto_data.get("exempt_states", ["draft", "review", "closed"]),
        )

        # Parse board intervention settings
        board_data = data.get("board_intervention", {})
        board_intervention = BoardInterventionSettings(
            consecutive_ceo_escalations=board_data.get("consecutive_ceo_escalations", 3),
            org_wide_escalation_threshold=board_data.get(
                "org_wide_escalation_threshold", 0.25
            ),
            threshold_window_minutes=board_data.get("threshold_window_minutes", 1440),
        )

        # Convert default_timeout_minutes to seconds
        default_timeout_minutes = data.get("default_timeout_minutes", 5)
        timeout_seconds = default_timeout_minutes * 60

        return cls(
            timeout_seconds=timeout_seconds,
            retry_attempts=retry_policy.max_retries,
            escalation_paths=escalation_paths,
            retry_policy=retry_policy,
            notification_settings=notification_settings,
            timeout_warning=timeout_warning,
            auto_escalation=auto_escalation,
            board_intervention=board_intervention,
        )


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


class EscalationManager:
    """
    Centralized manager for escalation workflows.

    Coordinates escalations across the organization by:
    - Maintaining a queue of pending escalations
    - Running timeout checks for auto-escalation
    - Routing through the organizational hierarchy
    - Integrating with notification systems
    - Tracking escalation history

    This class is thread-safe and can be used in async contexts
    with the async methods.

    Example:
        >>> config = EscalationConfig(timeout_seconds=60)
        >>> topology = create_simple_topology([...])
        >>> manager = EscalationManager(topology, config)
        >>> manager.start()  # Start timeout checker
        >>> entry = manager.submit("worker-1", "Issue", {"ctx": "data"})
        >>> manager.process(entry.id, {"mgr": mgr_handler})
        >>> manager.stop()  # Stop timeout checker
    """

    def __init__(
        self,
        topology: OrgTopology,
        config: EscalationConfig | None = None,
        notification_handler: NotificationHandler | None = None,
    ) -> None:
        """
        Initialize the escalation manager.

        Args:
            topology: Organizational hierarchy for routing.
            config: Escalation configuration. Uses defaults if not provided.
            notification_handler: Optional handler for notifications.
        """
        self._topology = topology
        self._config = config or EscalationConfig()
        self._router = HierarchicalRouter(topology)
        self._notification_handler = notification_handler

        # Queue management
        self._queue: dict[str, EscalationEntry] = {}
        self._queue_lock = threading.Lock()

        # History tracking
        self._history: deque[EscalationHistoryEntry] = deque(
            maxlen=self._config.max_history_size if self._config.enable_history else 0
        )
        self._history_lock = threading.Lock()

        # Timeout checker
        self._running = False
        self._timeout_thread: threading.Thread | None = None
        self._escalation_counter = 0

    @property
    def config(self) -> EscalationConfig:
        """Get the current configuration."""
        return self._config

    @property
    def queue_size(self) -> int:
        """Get the current queue size."""
        with self._queue_lock:
            return len(self._queue)

    @property
    def history_size(self) -> int:
        """Get the current history size."""
        with self._history_lock:
            return len(self._history)

    def _generate_id(self) -> str:
        """Generate a unique escalation ID."""
        self._escalation_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"esc-{timestamp}-{self._escalation_counter:06d}"

    def submit(
        self,
        worker_id: str,
        issue: str,
        context: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> EscalationEntry:
        """
        Submit a new escalation to the queue.

        Args:
            worker_id: Worker initiating the escalation.
            issue: Description of the problem.
            context: Additional context data.
            timeout_seconds: Override timeout for this escalation.

        Returns:
            The created EscalationEntry.

        Raises:
            RuntimeError: If queue is full.
        """
        with self._queue_lock:
            if len(self._queue) >= self._config.max_queue_size:
                raise RuntimeError(
                    f"Escalation queue full (max: {self._config.max_queue_size})"
                )

            entry_id = self._generate_id()
            timeout = timeout_seconds or self._config.timeout_seconds
            path = self._router.get_escalation_path(worker_id)

            entry = EscalationEntry(
                id=entry_id,
                worker_id=worker_id,
                issue=issue,
                context=context or {},
                created_at=datetime.now(),
                timeout_at=datetime.now() + timedelta(seconds=timeout),
                escalation_path=path,
                current_target=path[0] if path else None,
            )

            self._queue[entry_id] = entry

            logger.info(
                "Escalation submitted: %s from %s -> %s",
                entry_id,
                worker_id,
                path,
            )

            if self._notification_handler:
                self._notification_handler.notify(entry, "created")

            return entry

    def get_entry(self, escalation_id: str) -> EscalationEntry | None:
        """
        Get an escalation entry by ID.

        Args:
            escalation_id: The escalation ID.

        Returns:
            The entry if found, None otherwise.
        """
        with self._queue_lock:
            return self._queue.get(escalation_id)

    def get_pending(self) -> list[EscalationEntry]:
        """
        Get all pending escalations.

        Returns:
            List of pending escalation entries.
        """
        with self._queue_lock:
            return [
                e for e in self._queue.values() if e.state == EscalationState.PENDING
            ]

    def get_by_worker(self, worker_id: str) -> list[EscalationEntry]:
        """
        Get all escalations for a worker.

        Args:
            worker_id: The worker ID.

        Returns:
            List of escalation entries for the worker.
        """
        with self._queue_lock:
            return [e for e in self._queue.values() if e.worker_id == worker_id]

    def process(
        self,
        escalation_id: str,
        escalators: dict[str, EscalationInterface],
    ) -> EscalationResponse:
        """
        Process an escalation through the hierarchy.

        Args:
            escalation_id: ID of the escalation to process.
            escalators: Dictionary of worker_id -> EscalationInterface.

        Returns:
            EscalationResponse from the resolution attempt.

        Raises:
            KeyError: If escalation ID not found.
            ValueError: If escalation already resolved.
        """
        with self._queue_lock:
            entry = self._queue.get(escalation_id)
            if entry is None:
                raise KeyError(f"Escalation not found: {escalation_id}")

            if entry.state in (EscalationState.RESOLVED, EscalationState.FAILED):
                raise ValueError(f"Escalation already completed: {escalation_id}")

            entry.state = EscalationState.IN_PROGRESS
            entry.attempts += 1

        # Route through hierarchy
        response = self._router.route(entry.worker_id, entry.issue, escalators)

        with self._queue_lock:
            if response.resolved:
                entry.state = EscalationState.RESOLVED
                entry.response = response
                logger.info(
                    "Escalation resolved: %s by %s",
                    escalation_id,
                    response.escalated_to,
                )
                self._complete_escalation(entry, response.escalated_to)

                if self._notification_handler:
                    self._notification_handler.notify(entry, "resolved")
            else:
                # Check if we should retry or fail
                if entry.attempts >= self._config.retry_attempts:
                    entry.state = EscalationState.FAILED
                    logger.warning(
                        "Escalation failed after %d attempts: %s",
                        entry.attempts,
                        escalation_id,
                    )
                    self._complete_escalation(entry, None)

                    if self._notification_handler:
                        self._notification_handler.notify(entry, "failed")
                else:
                    entry.state = EscalationState.PENDING

        return response

    def _complete_escalation(
        self,
        entry: EscalationEntry,
        resolved_by: str | None,
    ) -> None:
        """
        Move an escalation from queue to history.

        Must be called with queue_lock held.

        Args:
            entry: The completed escalation.
            resolved_by: Who resolved it (if applicable).
        """
        # Remove from queue
        self._queue.pop(entry.id, None)

        # Add to history if enabled
        if self._config.enable_history:
            history_entry = EscalationHistoryEntry(
                id=entry.id,
                worker_id=entry.worker_id,
                issue=entry.issue,
                state=entry.state,
                created_at=entry.created_at,
                resolved_at=datetime.now(),
                resolved_by=resolved_by,
                escalation_path=entry.escalation_path,
                attempts=entry.attempts,
            )

            with self._history_lock:
                self._history.append(history_entry)

    def cancel(self, escalation_id: str) -> bool:
        """
        Cancel a pending escalation.

        Args:
            escalation_id: ID of the escalation to cancel.

        Returns:
            True if cancelled, False if not found or not cancellable.
        """
        with self._queue_lock:
            entry = self._queue.get(escalation_id)
            if entry is None:
                return False

            if entry.state != EscalationState.PENDING:
                return False

            entry.state = EscalationState.FAILED
            self._complete_escalation(entry, None)

            logger.info("Escalation cancelled: %s", escalation_id)
            return True

    def get_history(
        self,
        worker_id: str | None = None,
        state: EscalationState | None = None,
        limit: int = 100,
    ) -> list[EscalationHistoryEntry]:
        """
        Query escalation history.

        Args:
            worker_id: Filter by worker ID.
            state: Filter by final state.
            limit: Maximum entries to return.

        Returns:
            List of matching history entries (newest first).
        """
        with self._history_lock:
            results = list(self._history)

        # Filter
        if worker_id is not None:
            results = [e for e in results if e.worker_id == worker_id]
        if state is not None:
            results = [e for e in results if e.state == state]

        # Return newest first, limited
        return list(reversed(results))[:limit]

    def _check_timeouts(self) -> None:
        """Check for timed-out escalations and auto-escalate."""
        with self._queue_lock:
            now = datetime.now()
            timed_out = [
                e
                for e in self._queue.values()
                if e.state == EscalationState.PENDING
                and e.timeout_at is not None
                and now >= e.timeout_at
            ]

        for entry in timed_out:
            logger.warning(
                "Escalation timeout: %s (created %s)",
                entry.id,
                entry.created_at.isoformat(),
            )

            with self._queue_lock:
                entry.state = EscalationState.TIMEOUT

                if self._config.auto_escalate_on_timeout:
                    # Move to next target in path
                    if entry.current_target and entry.escalation_path:
                        try:
                            idx = entry.escalation_path.index(entry.current_target)
                            if idx + 1 < len(entry.escalation_path):
                                entry.current_target = entry.escalation_path[idx + 1]
                                entry.timeout_at = now + timedelta(
                                    seconds=self._config.timeout_seconds
                                )
                                entry.state = EscalationState.PENDING
                                logger.info(
                                    "Auto-escalated %s to %s",
                                    entry.id,
                                    entry.current_target,
                                )
                        except ValueError:
                            pass

                    if entry.state == EscalationState.TIMEOUT:
                        # Couldn't auto-escalate further
                        self._complete_escalation(entry, None)

                if self._notification_handler:
                    self._notification_handler.notify(entry, "timeout")

    def _timeout_loop(self) -> None:
        """Background loop for timeout checking."""
        while self._running:
            try:
                self._check_timeouts()
            except Exception as e:
                logger.error("Error in timeout check: %s", e)

            # Sleep in small increments to allow clean shutdown
            for _ in range(10):
                if not self._running:
                    break
                time.sleep(1)

    def start(self) -> None:
        """Start the background timeout checker."""
        if self._running:
            return

        self._running = True
        self._timeout_thread = threading.Thread(
            target=self._timeout_loop,
            name="EscalationManager-timeout",
            daemon=True,
        )
        self._timeout_thread.start()
        logger.info("EscalationManager started")

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stop the background timeout checker.

        Args:
            timeout: Maximum seconds to wait for thread to stop.
        """
        if not self._running:
            return

        self._running = False
        if self._timeout_thread is not None:
            self._timeout_thread.join(timeout=timeout)
            self._timeout_thread = None

        logger.info("EscalationManager stopped")

    def __enter__(self) -> EscalationManager:
        """Context manager entry - starts the manager."""
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - stops the manager."""
        self.stop()


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
