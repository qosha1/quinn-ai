"""
Worker state machine implementation.

Workers have dual state machines:
- Lifecycle: HR/org-chart state (pending → onboarding → active → offboarding → terminated)
- Runtime: Process/session state (starting → running ⇄ idle → stopped/crashed)
"""

from datetime import datetime, timedelta
from typing import Optional

from .db import Database
from .queries import (
    get_worker,
    update_worker_status,
    get_worker_state,
    create_worker_state,
    update_worker_runtime_status,
    record_worker_heartbeat,
    increment_worker_task_count,
)


# Valid lifecycle transitions
LIFECYCLE_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["onboarding"],
    "onboarding": ["active", "terminated"],
    "active": ["offboarding"],
    "offboarding": ["terminated"],
    "terminated": [],
}

# Valid runtime transitions
RUNTIME_TRANSITIONS: dict[str, list[str]] = {
    "starting": ["running", "crashed"],
    "running": ["idle", "stopped", "crashed"],
    "idle": ["running", "stopped"],
    "stopped": ["starting"],
    "crashed": ["starting"],
}

# Lifecycle states that allow sessions
SESSION_ALLOWED_LIFECYCLES = {"onboarding", "active", "offboarding"}


class InvalidStateTransition(Exception):
    """Raised when attempting an invalid state transition."""

    def __init__(self, current: str, attempted: str, valid: list[str]):
        self.current = current
        self.attempted = attempted
        self.valid = valid
        super().__init__(
            f"Cannot transition from '{current}' to '{attempted}'. "
            f"Valid transitions: {valid}"
        )


class WorkerNotFound(Exception):
    """Raised when worker doesn't exist."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        super().__init__(f"Worker not found: {worker_id}")


class InvalidLifecycleState(Exception):
    """Raised when operation not allowed in current lifecycle state."""

    def __init__(self, operation: str, lifecycle: str):
        self.operation = operation
        self.lifecycle = lifecycle
        super().__init__(
            f"Cannot {operation} when lifecycle is '{lifecycle}'"
        )


class Worker:
    """Worker with dual state machine (lifecycle + runtime).

    Provides methods for managing worker state transitions with validation.
    All state changes are persisted to the database.
    """

    def __init__(self, db: Database, worker_id: str):
        """Initialize worker wrapper.

        Args:
            db: Database instance
            worker_id: Worker ID to manage
        """
        self.db = db
        self.id = worker_id
        self._worker_data = None
        self._state_data = None

    def _load_worker(self) -> None:
        """Load worker data from database."""
        self._worker_data = get_worker(self.db, self.id)
        if self._worker_data is None:
            raise WorkerNotFound(self.id)

    def _load_state(self) -> None:
        """Load runtime state from database."""
        self._state_data = get_worker_state(self.db, self.id)

    def refresh(self) -> None:
        """Refresh data from database."""
        self._load_worker()
        self._load_state()

    # ==================
    # LIFECYCLE PROPERTIES
    # ==================

    @property
    def lifecycle_status(self) -> str:
        """Get current lifecycle status."""
        if self._worker_data is None:
            self._load_worker()
        return self._worker_data.status

    @property
    def name(self) -> str:
        """Get worker name."""
        if self._worker_data is None:
            self._load_worker()
        return self._worker_data.name

    @property
    def role(self) -> str:
        """Get worker role."""
        if self._worker_data is None:
            self._load_worker()
        return self._worker_data.role

    # ==================
    # RUNTIME PROPERTIES
    # ==================

    @property
    def runtime_status(self) -> Optional[str]:
        """Get current runtime status, or None if no session."""
        if self._state_data is None:
            self._load_state()
        return self._state_data.runtime_status if self._state_data else None

    @property
    def current_task_id(self) -> Optional[str]:
        """Get current task ID, or None."""
        if self._state_data is None:
            self._load_state()
        return self._state_data.current_task_id if self._state_data else None

    @property
    def pid(self) -> Optional[int]:
        """Get process ID, or None."""
        if self._state_data is None:
            self._load_state()
        return self._state_data.pid if self._state_data else None

    # ==================
    # CAPABILITY QUERIES
    # ==================

    @property
    def can_work(self) -> bool:
        """Check if worker can accept work.

        Returns True only if lifecycle is 'active' and runtime is 'running' or 'idle'.
        """
        return (
            self.lifecycle_status == "active"
            and self.runtime_status in ("running", "idle")
        )

    @property
    def is_session_active(self) -> bool:
        """Check if worker session is active.

        Returns True if runtime is 'starting', 'running', or 'idle'.
        """
        return self.runtime_status in ("starting", "running", "idle")

    # ==================
    # LIFECYCLE TRANSITIONS
    # ==================

    def _validate_lifecycle_transition(self, new_status: str) -> None:
        """Validate lifecycle state transition.

        Args:
            new_status: Attempted new status

        Raises:
            InvalidStateTransition: If transition is not allowed
        """
        current = self.lifecycle_status
        valid = LIFECYCLE_TRANSITIONS.get(current, [])
        if new_status not in valid:
            raise InvalidStateTransition(current, new_status, valid)

    def start_onboarding(self) -> None:
        """Transition from pending to onboarding."""
        self._validate_lifecycle_transition("onboarding")
        update_worker_status(self.db, self.id, "onboarding")
        self._worker_data = None  # Invalidate cache

    def complete_onboarding(self) -> None:
        """Transition from onboarding to active."""
        self._validate_lifecycle_transition("active")
        update_worker_status(self.db, self.id, "active")
        self._worker_data = None

    def fail_onboarding(self) -> None:
        """Transition from onboarding to terminated (failed onboarding)."""
        self._validate_lifecycle_transition("terminated")
        update_worker_status(self.db, self.id, "terminated")
        self._worker_data = None

    def start_offboarding(self) -> None:
        """Transition from active to offboarding."""
        self._validate_lifecycle_transition("offboarding")
        update_worker_status(self.db, self.id, "offboarding")
        self._worker_data = None

    def terminate(self) -> None:
        """Transition from offboarding to terminated."""
        self._validate_lifecycle_transition("terminated")
        update_worker_status(self.db, self.id, "terminated")
        self._worker_data = None

    # ==================
    # RUNTIME TRANSITIONS
    # ==================

    def _validate_runtime_transition(self, new_status: str) -> None:
        """Validate runtime state transition.

        Args:
            new_status: Attempted new status

        Raises:
            InvalidStateTransition: If transition is not allowed
        """
        current = self.runtime_status
        if current is None:
            # No current state - only starting is valid
            if new_status != "starting":
                raise InvalidStateTransition("(none)", new_status, ["starting"])
            return

        valid = RUNTIME_TRANSITIONS.get(current, [])
        if new_status not in valid:
            raise InvalidStateTransition(current, new_status, valid)

    def _validate_session_allowed(self) -> None:
        """Validate that sessions are allowed in current lifecycle.

        Raises:
            InvalidLifecycleState: If sessions not allowed
        """
        lifecycle = self.lifecycle_status
        if lifecycle not in SESSION_ALLOWED_LIFECYCLES:
            raise InvalidLifecycleState("start session", lifecycle)

    def start_session(self, pid: Optional[int] = None) -> None:
        """Start a new session (starting state).

        Args:
            pid: Process ID for crash detection

        Raises:
            InvalidLifecycleState: If lifecycle doesn't allow sessions
        """
        self._validate_session_allowed()

        if self._state_data is None:
            self._load_state()

        if self._state_data is None:
            # Create new state
            create_worker_state(self.db, self.id, pid)
        else:
            # Validate transition and update
            self._validate_runtime_transition("starting")
            update_worker_runtime_status(self.db, self.id, "starting")
            # Update PID if provided
            if pid is not None:
                self.db.execute(
                    "UPDATE worker_state SET pid = ? WHERE worker_id = ?",
                    (pid, self.id)
                )
                self.db.connection.commit()

        self._state_data = None  # Invalidate cache

    def session_ready(self) -> None:
        """Mark session as ready (running state)."""
        self._validate_runtime_transition("running")
        update_worker_runtime_status(self.db, self.id, "running")
        self._state_data = None

    def begin_work(self, task_id: str) -> None:
        """Begin working on a task.

        Args:
            task_id: ID of task being worked on
        """
        self._validate_runtime_transition("running")
        update_worker_runtime_status(self.db, self.id, "running", task_id)
        self._state_data = None

    def finish_work(self, success: bool = True) -> None:
        """Finish current work and return to idle.

        Args:
            success: Whether task completed successfully
        """
        self._validate_runtime_transition("idle")
        update_worker_runtime_status(self.db, self.id, "idle", None)
        increment_worker_task_count(self.db, self.id, completed=success)
        self._state_data = None

    def stop_session(self) -> None:
        """Gracefully stop session."""
        self._validate_runtime_transition("stopped")
        update_worker_runtime_status(self.db, self.id, "stopped")
        self._state_data = None

    def mark_crashed(self) -> None:
        """Mark session as crashed."""
        # Can crash from any running state
        if self.runtime_status in ("starting", "running", "idle"):
            update_worker_runtime_status(self.db, self.id, "crashed")
            self._state_data = None

    # ==================
    # HEARTBEAT
    # ==================

    def heartbeat(self) -> None:
        """Record heartbeat to indicate liveness."""
        record_worker_heartbeat(self.db, self.id)
        self._state_data = None

    def is_heartbeat_stale(self, threshold_seconds: int = 60) -> bool:
        """Check if heartbeat is stale.

        Args:
            threshold_seconds: Seconds after which heartbeat is considered stale

        Returns:
            True if last_activity is older than threshold
        """
        if self._state_data is None:
            self._load_state()

        if self._state_data is None or self._state_data.last_activity is None:
            return True

        # Parse datetime string if needed (SQLite returns strings)
        last_activity = self._state_data.last_activity
        if isinstance(last_activity, str):
            last_activity = datetime.fromisoformat(last_activity)

        threshold = datetime.now() - timedelta(seconds=threshold_seconds)
        return last_activity < threshold

    # ==================
    # CLASS METHODS
    # ==================

    @classmethod
    def get(cls, db: Database, worker_id: str) -> "Worker":
        """Get a worker by ID.

        Args:
            db: Database instance
            worker_id: Worker ID

        Returns:
            Worker instance

        Raises:
            WorkerNotFound: If worker doesn't exist
        """
        worker = cls(db, worker_id)
        worker._load_worker()  # Validate exists
        return worker
