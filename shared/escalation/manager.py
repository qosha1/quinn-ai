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
from typing import Any, Callable, Protocol

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
class EscalationConfig:
    """
    Configuration for escalation behavior.

    Attributes:
        timeout_seconds: Default timeout before auto-escalation (default 300s).
        max_escalation_depth: Maximum levels to escalate before failing (default 10).
        auto_escalate_on_timeout: Whether to automatically escalate on timeout.
        retry_attempts: Number of retry attempts before escalating (default 1).
        enable_history: Whether to track escalation history (default True).
        max_history_size: Maximum history entries to retain (default 10000).
        max_queue_size: Maximum pending escalations (default 1000).
    """

    timeout_seconds: int = 300
    max_escalation_depth: int = 10
    auto_escalate_on_timeout: bool = True
    retry_attempts: int = 1
    enable_history: bool = True
    max_history_size: int = 10000
    max_queue_size: int = 1000


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
