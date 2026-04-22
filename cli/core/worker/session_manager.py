"""
Worker session management.

Handles session spawning, attachment, state management, and lifecycle operations.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from ..constants import DEFAULT_HEARTBEAT_THRESHOLD
from ..queries import (
    get_worker_state,
    create_worker_state,
    update_worker_runtime_status,
    record_worker_heartbeat,
    increment_worker_task_count,
)
from ..sessions.persistence import (
    create_session_record,
    update_session_state,
    update_session_pid,
    get_session_for_worker,
    delete_session_record,
    delete_session_for_worker,
)
from ..logging import get_logger, log_session_spawn, log_session_stop
from shared import (
    RUNTIME_TRANSITIONS,
    SESSION_ALLOWED_LIFECYCLES,
    InvalidStateTransition,
    InvalidLifecycleState,
    ActiveSessionExistsError,
)
from shared.exceptions import SessionSpawnError, SessionStartTimeout

if TYPE_CHECKING:
    from ..db import Database
    from ..session import SessionInterface, SessionConfig, SessionState
    from ..sessions.registry import SessionRegistry


_logger = get_logger(__name__)


class WorkerSessionManager:
    """Manages session operations for a worker.

    Handles:
    - Session spawning and attachment
    - Runtime state transitions
    - Session lifecycle management
    - Heartbeat tracking
    """

    def __init__(self, worker: "WorkerBase"):
        """Initialize session manager.

        Args:
            worker: Parent Worker instance
        """
        self.worker = worker
        self._session: Optional["SessionInterface"] = None
        self._session_registry: Optional["SessionRegistry"] = None

    @property
    def session(self) -> Optional["SessionInterface"]:
        """Get the current session instance, if any."""
        return self._session

    @property
    def runtime_status(self) -> Optional[str]:
        """Get current runtime status, or None if no session."""
        if self.worker._state_data is None:
            self.worker._load_state()
        return self.worker._state_data.runtime_status if self.worker._state_data else None

    @property
    def is_session_active(self) -> bool:
        """Check if worker session is active.

        Returns True if:
        1. Session is attached in memory (spawn in progress), OR
        2. Session record exists in database (persisted session)

        Auto-repairs inconsistent state where worker_state says 'running'
        but no session exists.
        """
        # Check in-memory session (handles spawn-in-progress case)
        if self._session is not None:
            return True

        # Check database for persisted session
        session_record = get_session_for_worker(self.worker.db, self.worker.id)
        if session_record is not None:
            # Verify session is in an active state
            active_states = ("starting", "running", "idle")
            if session_record.get("state") in active_states:
                return True

        # No session found - check if worker state thinks it's running
        runtime = self.runtime_status
        if runtime in ("starting", "running", "idle"):
            # Inconsistent state - auto-repair
            _logger.warning(
                f"Worker {self.worker.id} state shows '{runtime}' but no session exists. "
                "Auto-repairing by resetting to 'stopped'."
            )
            update_worker_runtime_status(self.worker.db, self.worker.id, "stopped")
            self.worker._state_data = None  # Invalidate cache

        return False

    def set_registry(self, registry: "SessionRegistry") -> None:
        """Set the session registry for this worker.

        Args:
            registry: SessionRegistry instance to use for creating sessions
        """
        self._session_registry = registry

    def get_registry(self) -> "SessionRegistry":
        """Get the session registry (creates default if not set).

        Returns:
            SessionRegistry instance
        """
        if self._session_registry is None:
            from ..sessions.registry import get_default_registry
            self._session_registry = get_default_registry()
        return self._session_registry

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
        lifecycle = self.worker.lifecycle_status
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

        if self.worker._state_data is None:
            self.worker._load_state()

        if self.worker._state_data is None:
            # Create new state
            create_worker_state(self.worker.db, self.worker.id, pid)
        else:
            # Validate transition and update
            self._validate_runtime_transition("starting")
            update_worker_runtime_status(self.worker.db, self.worker.id, "starting")
            # Update PID if provided
            if pid is not None:
                self.worker.db.execute(
                    "UPDATE worker_state SET pid = ? WHERE worker_id = ?",
                    (pid, self.worker.id)
                )
                self.worker.db.connection.commit()

        self.worker._state_data = None  # Invalidate cache

    def session_ready(self) -> None:
        """Mark session as ready (running state)."""
        self._validate_runtime_transition("running")
        update_worker_runtime_status(self.worker.db, self.worker.id, "running")
        self.worker._state_data = None

    def begin_work(self, task_id: str) -> None:
        """Begin working on a task.

        Args:
            task_id: ID of task being worked on
        """
        self._validate_runtime_transition("running")
        update_worker_runtime_status(self.worker.db, self.worker.id, "running", task_id)
        self.worker._state_data = None

    def finish_work(self, success: bool = True) -> None:
        """Finish current work and return to idle.

        Args:
            success: Whether task completed successfully
        """
        self._validate_runtime_transition("idle")
        update_worker_runtime_status(self.worker.db, self.worker.id, "idle", None)
        increment_worker_task_count(self.worker.db, self.worker.id, completed=success)
        self.worker._state_data = None

    def stop_session(self, force: bool = False) -> None:
        """Gracefully stop session.

        Args:
            force: If True, force stop without cleanup
        """
        self._validate_runtime_transition("stopped")
        update_worker_runtime_status(self.worker.db, self.worker.id, "stopped")

        # Also update session record if it exists
        session_record = get_session_for_worker(self.worker.db, self.worker.id)
        if session_record:
            from datetime import datetime
            update_session_state(
                self.worker.db,
                session_record["id"],
                "stopped",
                stopped_at=datetime.now()
            )

        self.worker._state_data = None

    def mark_crashed(self) -> None:
        """Mark session as crashed."""
        # Can crash from any running state
        if self.runtime_status in ("starting", "running", "idle"):
            update_worker_runtime_status(self.worker.db, self.worker.id, "crashed")

            # Also update session record if it exists
            session_record = get_session_for_worker(self.worker.db, self.worker.id)
            if session_record:
                from datetime import datetime
                update_session_state(
                    self.worker.db,
                    session_record["id"],
                    "crashed",
                    stopped_at=datetime.now()
                )

            self.worker._state_data = None

    def heartbeat(self) -> None:
        """Record heartbeat to indicate liveness."""
        record_worker_heartbeat(self.worker.db, self.worker.id)
        self.worker._state_data = None

    def is_heartbeat_stale(
        self,
        threshold_seconds: int = DEFAULT_HEARTBEAT_THRESHOLD
    ) -> bool:
        """Check if heartbeat is stale.

        Args:
            threshold_seconds: Seconds after which heartbeat is considered stale

        Returns:
            True if last_activity is older than threshold
        """
        if self.worker._state_data is None:
            self.worker._load_state()

        if self.worker._state_data is None or self.worker._state_data.last_activity is None:
            return True

        # Parse datetime string if needed (SQLite returns strings)
        last_activity = self.worker._state_data.last_activity
        if isinstance(last_activity, str):
            last_activity = datetime.fromisoformat(last_activity)

        threshold = datetime.now() - timedelta(seconds=threshold_seconds)
        return last_activity < threshold

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
        from ..session import SessionState

        self._validate_session_allowed()

        if self._session is not None:
            raise ValueError(
                f"Worker {self.worker.id} already has an attached session. "
                "Call detach_session() first."
            )

        # Bind session to this worker (enforces 1:1)
        session.bind_to_worker(self.worker.id)

        # Set up callback to sync session state to worker runtime state
        def on_session_state_change(old: "SessionState", new: "SessionState") -> None:
            # SessionState enum values match the runtime status strings
            runtime_status = new.value
            # Update DB state to match session state
            update_worker_runtime_status(self.worker.db, self.worker.id, runtime_status)
            self.worker._state_data = None  # Invalidate cache

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

        Orchestrates the session spawn process through distinct phases:
        1. Validate preconditions (no existing active session, worker state ready)
        2. Enforce budget constraints (estimate cost, check allocation)
        3. Attach and start the session
        4. Finalize (record spend, persist session record, handle race conditions)

        Args:
            session: Configured SessionInterface instance to spawn

        Raises:
            InvalidLifecycleState: If lifecycle doesn't allow sessions
            SessionSpawnError: If session fails to start
            BudgetExhaustedError: If worker has insufficient budget
            NoBudgetAllocationError: If worker has no budget allocation
            ActiveSessionExistsError: If worker already has an active session
        """
        # Phase 1: Validate preconditions
        self._validate_spawn_preconditions(session)

        # Phase 2: Budget enforcement
        budget_check = self.worker._budget_mgr.enforce_spawn_budget(session)

        # Phase 3: Attach and start session
        self._start_session(session)

        # Phase 4: Record spend and persist
        self._finalize_spawn(session, budget_check.allocation_id)

    def _validate_spawn_preconditions(self, session: "SessionInterface") -> None:
        """Validate that session can be spawned.

        Checks:
        - No existing active session for this worker
        - Worker state row exists (required for session state callbacks)

        Args:
            session: The session to be spawned (used for type consistency)

        Raises:
            ActiveSessionExistsError: If worker already has an active session
        """
        # Check for existing session before spawning
        existing_session = get_session_for_worker(self.worker.db, self.worker.id)
        if existing_session is not None:
            active_states = ("starting", "running", "idle")
            if existing_session.get("state") in active_states:
                # Actively running session — block the spawn
                raise ActiveSessionExistsError(
                    worker_id=self.worker.id,
                    existing_session_id=existing_session["id"],
                )
            else:
                # Stale stopped/crashed record from an unclean shutdown — clean it up
                # so the UNIQUE(worker_id) constraint doesn't block the new insert
                _logger.debug(
                    f"Cleaning up stale session record for worker {self.worker.id} "
                    f"(state={existing_session.get('state')}, id={existing_session.get('id')})"
                )
                delete_session_for_worker(self.worker.db, self.worker.id)

        # Ensure worker_state row exists before session state callbacks fire.
        # The attach_session callback calls update_worker_runtime_status which
        # only does UPDATE (not INSERT), so the row must exist first.
        if self.worker._state_data is None:
            self.worker._load_state()
        if self.worker._state_data is None:
            create_worker_state(self.worker.db, self.worker.id, pid=None)
            self.worker._state_data = None  # Will be reloaded on next access

    def _start_session(self, session: "SessionInterface") -> None:
        """Attach and start the session.

        Attaches the session to this worker and starts it. If start fails,
        the session is detached before the exception propagates.

        Args:
            session: The session to attach and start

        Raises:
            SessionSpawnError: If session fails to start
        """
        self.attach_session(session)

        try:
            # Start the session - state callbacks will update our runtime status
            session.start()
        except (SessionSpawnError, SessionStartTimeout, OSError, RuntimeError, TimeoutError) as e:
            # If start fails, detach the session before re-raising
            _logger.error(f"Session start failed for worker {self.worker.id}: {e}")
            self._session = None
            raise

    def _finalize_spawn(
        self,
        session: "SessionInterface",
        allocation_id: str,
    ) -> None:
        """Record spend and persist session record.

        Records the session spawn cost against the budget allocation and
        persists the session record to the database for crash recovery.
        Handles race conditions where another process created a session
        between our precondition check and the database insert.

        Args:
            session: The started session to finalize
            allocation_id: Budget allocation ID to charge against

        Raises:
            ActiveSessionExistsError: If race condition detected during persist
        """
        try:
            # Record spend after successful spawn
            self.worker._budget_mgr.record_spawn_spend(session, allocation_id)

            # Persist session record to database
            config = session.config
            working_dir = str(config.working_directory) if config.working_directory else None

            # Get platform session name (tmux session name, etc.)
            tmux_session_name = session.platform_session_name

            try:
                create_session_record(
                    db=self.worker.db,
                    session_id=str(session.id),
                    worker_id=self.worker.id,
                    provider=session.provider_name,
                    command=config.command,
                    args=config.args,
                    working_directory=working_dir,
                    tmux_session_name=tmux_session_name,
                    state=session.state.value,
                )
            except sqlite3.IntegrityError:
                # Race condition: another session was created between our check
                # and this insert. Stop the session we just started and raise.
                self._handle_spawn_race_condition(session)

            # Update PID if available
            if session.pid:
                update_session_pid(self.worker.db, str(session.id), session.pid)

            # Log successful session spawn
            log_session_spawn(
                _logger,
                worker_id=self.worker.id,
                worker_name=self.worker.name,
                provider=session.provider_name,
                session_id=str(session.id),
            )

        except (sqlite3.Error, OSError, ValueError, ActiveSessionExistsError) as e:
            # If finalization fails, detach the session
            _logger.error(f"Session finalization failed for worker {self.worker.id}: {e}")
            self._session = None
            raise

    def _handle_spawn_race_condition(self, session: "SessionInterface") -> None:
        """Handle race condition where another session was created concurrently.

        Stops the session we just started (best-effort cleanup) and raises
        an error indicating the existing session.

        Args:
            session: The session that was started but cannot be persisted

        Raises:
            ActiveSessionExistsError: Always raised to indicate race condition
        """
        try:
            session.stop(force=True)
        except (OSError, RuntimeError):
            # Intentionally swallowed: best-effort cleanup after race condition.
            # OSError: process issues, RuntimeError: session state issues
            pass
        self._session = None
        # Re-fetch to get the existing session ID
        existing = get_session_for_worker(self.worker.db, self.worker.id)
        existing_id = existing["id"] if existing else "unknown"
        raise ActiveSessionExistsError(
            worker_id=self.worker.id,
            existing_session_id=existing_id,
        )

    def terminate_session(self, force: bool = False) -> None:
        """Terminate the current session.

        Stops the session, deletes database record, and detaches from worker.

        Args:
            force: If True, force kill without cleanup
        """
        if self._session is None:
            return

        session_id = str(self._session.id)

        try:
            self._session.stop(force=force)
        finally:
            # Delete session record from database
            # This allows new sessions to be spawned immediately (e.g., during restart)
            delete_session_record(
                db=self.worker.db,
                session_id=session_id,
            )
            # Log session stop
            log_session_stop(_logger, self.worker.id, self.worker.name, force=force)
            self._session = None

    def spawn(self, config: "SessionConfig") -> "SessionInterface":
        """Spawn a session for this worker using the registry.

        Creates a session via the registry based on config.provider, attaches
        it to this worker, and starts it. Falls back to the default registry
        if no registry was provided to __init__ or set_registry().

        Args:
            config: SessionConfig with provider and settings.
                   config.provider determines which adapter is used.

        Returns:
            The spawned and attached SessionInterface instance

        Raises:
            InvalidLifecycleState: If lifecycle doesn't allow sessions
            SessionSpawnError: If session fails to start
            BudgetExhaustedError: If worker has insufficient budget
            NoBudgetAllocationError: If worker has no budget allocation
            AdapterNotFoundError: If provider not found in registry

        Example:
            config = SessionConfig(
                worker_id=worker.id,
                provider="claude_code",
                command="claude",
                args=["--dangerously-skip-permissions"],
            )
            session = worker.spawn(config)
        """
        self._ensure_onboarding(config)

        # Get registry - use instance registry or fall back to default
        registry = self.get_registry()

        # Create session via registry
        session = registry.create(config.provider, config)

        # Delegate to existing spawn_session for budget enforcement, attach, start
        self.spawn_session(session)

        return session

    def _ensure_onboarding(self, config: "SessionConfig") -> None:
        """Ensure onboarding artifacts and session context are prepared."""
        from core.onboarding import (
            prepare_worker_onboarding,
            load_onboarding_context,
            get_worker_env_vars,
            generate_welcome_message,
            generate_returning_message,
        )

        welcome_message = getattr(config, "welcome_message", None)
        env_vars = getattr(config, "env_vars", None)
        working_directory = getattr(config, "working_directory", None)

        if env_vars is None:
            config.env_vars = {}
            env_vars = config.env_vars

        if (
            welcome_message
            and working_directory
            and isinstance(env_vars, dict)
            and "BRIEFING_PATH" in env_vars
        ):
            return

        org_path = self.worker._storage_mgr.get_org_path()
        worker_dir = org_path / "storage" / "workers" / self.worker.id
        onboarding_dir = worker_dir / ".onboarding"
        marker = onboarding_dir / "initialized"

        has_onboarding = marker.exists() and (worker_dir / "BRIEFING.md").exists()
        if has_onboarding:
            ctx = load_onboarding_context(self.worker.db, self.worker.id, org_path)
        else:
            ctx = prepare_worker_onboarding(self.worker.db, self.worker.id, org_path)

        onboarding_env = get_worker_env_vars(ctx, org_path, self.worker.db)
        for key, value in onboarding_env.items():
            env_vars.setdefault(key, value)

        if working_directory is None:
            config.working_directory = worker_dir

        if not welcome_message:
            if has_onboarding:
                config.welcome_message = generate_returning_message(ctx)
            else:
                config.welcome_message = generate_welcome_message(ctx, worker_dir)
