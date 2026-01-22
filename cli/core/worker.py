"""
Worker state machine implementation.

Workers have dual state machines:
- Lifecycle: HR/org-chart state (pending → onboarding → active → offboarding → terminated)
- Runtime: Process/session state (starting → running ⇄ idle → stopped/crashed)
"""

from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from .db import Database
from .constants import (
    DEFAULT_HEARTBEAT_THRESHOLD,
    DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
    DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
    COST_TIER_BUDGET_MAX,
    COST_TIER_STANDARD_MAX,
    COST_TIER_ADVANCED_MAX,
)
from .budget import (
    enforce_budget,
    record_spend,
    estimate_cost,
    BudgetExhaustedError,
    NoBudgetAllocationError,
)

if TYPE_CHECKING:
    from .session import SessionInterface, SessionState
from .queries import (
    get_worker,
    update_worker_status,
    get_worker_state,
    create_worker_state,
    update_worker_runtime_status,
    record_worker_heartbeat,
    increment_worker_task_count,
)

# Import shared business logic
from shared import (
    LIFECYCLE_TRANSITIONS,
    RUNTIME_TRANSITIONS,
    SESSION_ALLOWED_LIFECYCLES,
    InvalidStateTransition,
    WorkerNotFound,
    InvalidLifecycleState,
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
        self._session: Optional["SessionInterface"] = None

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

    @property
    def cost(self) -> int:
        """Get worker cost score (0-100)."""
        if self._worker_data is None:
            self._load_worker()
        return self._worker_data.cost

    @property
    def skills(self) -> dict[str, int]:
        """Get worker skills dict."""
        if self._worker_data is None:
            self._load_worker()
        return self._worker_data.skills

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
    def cost_tier(self) -> str:
        """Get worker's cost tier based on cost score.

        Returns:
            Cost tier: 'budget', 'standard', 'advanced', or 'premium'
        """
        cost_score = self.cost
        if cost_score <= COST_TIER_BUDGET_MAX:
            return "budget"
        elif cost_score <= COST_TIER_STANDARD_MAX:
            return "standard"
        elif cost_score <= COST_TIER_ADVANCED_MAX:
            return "advanced"
        else:
            return "premium"

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

    def is_heartbeat_stale(self, threshold_seconds: int = DEFAULT_HEARTBEAT_THRESHOLD) -> bool:
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
    # SESSION MANAGEMENT
    # ==================

    @property
    def session(self) -> Optional["SessionInterface"]:
        """Get the current session instance, if any."""
        return self._session

    def attach_session(self, session: "SessionInterface") -> None:
        """Attach a session instance to this worker.

        Binds the session to this worker and sets up state change callbacks
        to keep the worker's runtime state in sync with the session.

        Args:
            session: SessionInterface instance to attach

        Raises:
            InvalidLifecycleState: If lifecycle doesn't allow sessions
            ValueError: If worker already has an attached session
        """
        # Import here to avoid circular imports
        from .session import SessionState

        self._validate_session_allowed()

        if self._session is not None:
            raise ValueError(
                f"Worker {self.id} already has an attached session. "
                "Call detach_session() first."
            )

        # Bind session to this worker (enforces 1:1)
        session.bind_to_worker(self.id)

        # Set up callback to sync session state to worker runtime state
        def on_session_state_change(old: "SessionState", new: "SessionState") -> None:
            state_mapping = {
                SessionState.STARTING: "starting",
                SessionState.RUNNING: "running",
                SessionState.IDLE: "idle",
                SessionState.STOPPED: "stopped",
                SessionState.CRASHED: "crashed",
            }
            runtime_status = state_mapping.get(new)
            if runtime_status:
                # Update DB state to match session state
                update_worker_runtime_status(self.db, self.id, runtime_status)
                self._state_data = None  # Invalidate cache

        session.on_state_change(on_session_state_change)
        self._session = session

    def detach_session(self) -> Optional["SessionInterface"]:
        """Detach the current session from this worker.

        Does NOT stop the session - call terminate_session() for that.

        Returns:
            The detached session, or None if no session was attached
        """
        session = self._session
        self._session = None
        return session

    def spawn_session(self, session: "SessionInterface") -> None:
        """Spawn a session for this worker.

        Attaches the session, starts it, and updates worker state.
        Enforces budget check before spawning and records spend after.

        Args:
            session: Configured SessionInterface instance to spawn

        Raises:
            InvalidLifecycleState: If lifecycle doesn't allow sessions
            SessionSpawnError: If session fails to start
            BudgetExhaustedError: If worker has insufficient budget
            NoBudgetAllocationError: If worker has no budget allocation
        """
        # Estimate session spawn cost based on worker's cost tier
        estimated_cost = estimate_cost(
            model_tier=self.cost_tier,
            input_tokens=DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
            output_tokens=DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
        )

        # Check budget before spawning - raises if insufficient
        budget_check = enforce_budget(
            db=self.db,
            worker_id=self.id,
            required_amount=estimated_cost,
        )

        self.attach_session(session)

        try:
            # Start the session - state callbacks will update our runtime status
            session.start()

            # Record spend after successful spawn
            record_spend(
                db=self.db,
                worker_id=self.id,
                allocation_id=budget_check.allocation_id,
                amount=estimated_cost,
                provider=session.provider_name,
                model=f"{self.cost_tier}-tier",
                input_tokens=DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
                output_tokens=DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
                reference_type="session",
                reference_id=str(session.id),
                description=f"Session spawn for worker {self.name}",
            )
        except Exception:
            # If spawn fails, detach the session
            self._session = None
            raise

    def terminate_session(self, force: bool = False) -> None:
        """Terminate the current session.

        Stops the session and detaches it from this worker.

        Args:
            force: If True, force kill without cleanup
        """
        if self._session is None:
            return

        try:
            self._session.stop(force=force)
        finally:
            self._session = None

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
