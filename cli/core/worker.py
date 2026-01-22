"""
Worker state machine implementation.

Workers have dual state machines:
- Lifecycle: HR/org-chart state (pending → onboarding → active → offboarding → terminated)
- Runtime: Process/session state (starting → running ⇄ idle → stopped/crashed)
"""

import json
from dataclasses import dataclass, field
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
    DEFAULT_MAX_REPORTS,
    DEFAULT_DELEGATED_BUDGET,
)
from .budget import (
    enforce_budget,
    record_spend,
    estimate_cost,
    BudgetExhaustedError,
    NoBudgetAllocationError,
)

if TYPE_CHECKING:
    from .session import SessionInterface, SessionState, SessionConfig
    from .sessions.registry import SessionRegistry
from .queries import (
    get_worker,
    update_worker_status,
    get_worker_state,
    create_worker_state,
    update_worker_runtime_status,
    record_worker_heartbeat,
    increment_worker_task_count,
    get_workers_by_manager,
    create_worker,
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


# ===================
# HIRING AUTHORITY
# ===================

@dataclass
class HiringScope:
    """Defines what a worker can hire.

    Represents the authority a worker has to hire new workers,
    including role restrictions and budget constraints.
    """
    allowed_roles: set[str] = field(default_factory=set)
    """Roles this worker can hire (e.g., {"engineer", "analyst"})."""

    max_cost: int = 0
    """Maximum cost score (0-100) for individual hires."""

    max_total_budget: int = 0
    """Total budget for all hires combined."""

    def to_json(self) -> str:
        """Serialize to JSON string for database storage."""
        return json.dumps({
            "allowed_roles": list(self.allowed_roles),
            "max_cost": self.max_cost,
            "max_total_budget": self.max_total_budget,
        })

    @classmethod
    def from_json(cls, json_str: Optional[str]) -> "HiringScope":
        """Deserialize from JSON string."""
        if not json_str:
            return cls()
        data = json.loads(json_str)
        return cls(
            allowed_roles=set(data.get("allowed_roles", [])),
            max_cost=data.get("max_cost", 0),
            max_total_budget=data.get("max_total_budget", 0),
        )

    def can_hire_role(self, role: str) -> bool:
        """Check if this scope allows hiring the given role."""
        return role in self.allowed_roles

    def can_afford_cost(self, cost: int) -> bool:
        """Check if individual hire cost is within limits."""
        return cost <= self.max_cost


class HiringError(Exception):
    """Base exception for hiring-related errors."""
    pass


class InsufficientHiringAuthority(HiringError):
    """Worker lacks authority to make this hire."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class MaxReportsExceeded(HiringError):
    """Worker has reached maximum direct reports."""

    def __init__(self, current: int, maximum: int):
        self.current = current
        self.maximum = maximum
        super().__init__(f"Max reports exceeded: {current}/{maximum}")


class Worker:
    """Worker with dual state machine (lifecycle + runtime).

    Provides methods for managing worker state transitions with validation.
    All state changes are persisted to the database.
    """

    def __init__(
        self,
        db: Database,
        worker_id: str,
        session_registry: Optional["SessionRegistry"] = None,
    ):
        """Initialize worker wrapper.

        Args:
            db: Database instance
            worker_id: Worker ID to manage
            session_registry: Optional SessionRegistry for creating sessions via spawn().
                             If not provided, spawn() will use the default registry.
        """
        self.db = db
        self.id = worker_id
        self._worker_data = None
        self._state_data = None
        self._session: Optional["SessionInterface"] = None
        self._session_registry: Optional["SessionRegistry"] = session_registry

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

    @property
    def team_id(self) -> str:
        """Get worker's team ID."""
        if self._worker_data is None:
            self._load_worker()
        return self._worker_data.team_id

    @property
    def manager_id(self) -> Optional[str]:
        """Get worker's manager ID."""
        if self._worker_data is None:
            self._load_worker()
        return self._worker_data.manager_id

    # ==================
    # HIRING AUTHORITY PROPERTIES
    # ==================

    @property
    def hiring_authority_scope(self) -> HiringScope:
        """Get worker's hiring authority scope.

        Returns:
            HiringScope defining what roles/costs this worker can hire.
        """
        if self._worker_data is None:
            self._load_worker()
        # Get from DB - might be stored as JSON
        scope_json = getattr(self._worker_data, "hiring_authority_scope", None)
        return HiringScope.from_json(scope_json)

    @property
    def delegated_budget(self) -> int:
        """Get worker's delegated hiring budget.

        Returns:
            Budget amount this worker can delegate to hires.
        """
        if self._worker_data is None:
            self._load_worker()
        return getattr(self._worker_data, "delegated_budget", DEFAULT_DELEGATED_BUDGET)

    @property
    def max_reports(self) -> int:
        """Get maximum direct reports allowed for this worker.

        Returns:
            Maximum number of direct reports this worker can have.
        """
        if self._worker_data is None:
            self._load_worker()
        return getattr(self._worker_data, "max_reports", DEFAULT_MAX_REPORTS)

    @property
    def direct_reports_count(self) -> int:
        """Get current count of direct reports.

        Returns:
            Number of workers who report to this worker.
        """
        reports = get_workers_by_manager(self.db, self.id)
        return len(reports)

    # ==================
    # HIRING METHODS
    # ==================

    def can_hire(self, role: str, cost: int) -> tuple[bool, str]:
        """Check if this worker can hire for a given role and cost.

        Validates against:
        - Allowed roles in hiring scope
        - Cost within max_cost limit
        - Total budget constraints
        - Direct reports count vs max_reports

        Args:
            role: Role to hire for
            cost: Cost score (0-100) of the potential hire

        Returns:
            Tuple of (can_hire: bool, reason: str).
            If can_hire is False, reason explains why.
        """
        scope = self.hiring_authority_scope

        # Check if worker has any hiring authority
        if not scope.allowed_roles:
            return False, "No hiring authority - no allowed roles"

        # Check role is allowed
        if not scope.can_hire_role(role):
            return False, f"Role '{role}' not in allowed roles: {scope.allowed_roles}"

        # Check cost is within limits
        if not scope.can_afford_cost(cost):
            return False, f"Cost {cost} exceeds max allowed cost {scope.max_cost}"

        # Check direct reports limit
        current_reports = self.direct_reports_count
        if current_reports >= self.max_reports:
            return False, f"Max reports reached: {current_reports}/{self.max_reports}"

        # Check total budget (sum of existing hire costs + new cost)
        # For now, simplified - just check if cost fits in remaining budget
        # TODO: Track cumulative hire costs when budget tracking is fully implemented

        return True, "OK"

    def hire(
        self,
        name: str,
        role: str,
        skills: dict[str, int],
        cost: int,
    ) -> "Worker":
        """Hire a new worker under this worker.

        Creates a new worker with this worker as manager.
        Validates hiring authority before creating.

        Args:
            name: Name for the new worker
            role: Role for the new worker
            skills: Skills dict for the new worker
            cost: Cost score (0-100) for the new worker

        Returns:
            Worker instance for the newly hired worker

        Raises:
            InsufficientHiringAuthority: If can_hire() fails
            MaxReportsExceeded: If at max direct reports
        """
        # Validate hiring authority
        can_do, reason = self.can_hire(role, cost)
        if not can_do:
            if "Max reports" in reason:
                raise MaxReportsExceeded(self.direct_reports_count, self.max_reports)
            raise InsufficientHiringAuthority(reason)

        # Create the worker in database
        worker_data = create_worker(
            db=self.db,
            name=name,
            role=role,
            team_id=self.team_id,
            cost=cost,
            manager_id=self.id,
            skills=skills,
        )

        # Return Worker instance
        new_worker = Worker(self.db, worker_data.id)
        new_worker._worker_data = worker_data

        # Publish WORKER_HIRED event if events module is available
        try:
            from .events import publish, WORKER_HIRED
            publish(WORKER_HIRED, {
                "worker_id": worker_data.id,
                "name": name,
                "role": role,
                "manager_id": self.id,
                "cost": cost,
            })
        except ImportError:
            pass  # Events module not available yet

        return new_worker

    def delegate_authority(
        self,
        report: "Worker",
        budget: int,
        scope: HiringScope,
    ) -> None:
        """Delegate hiring authority to a direct report.

        Grants a subordinate worker the ability to hire within specified constraints.
        The delegated scope must be a subset of this worker's own authority.

        Args:
            report: Worker to delegate authority to (must be a direct report)
            budget: Budget amount to delegate for hiring
            scope: HiringScope defining allowed roles/costs

        Raises:
            ValueError: If report is not a direct report of this worker
            InsufficientHiringAuthority: If trying to delegate more than own authority
        """
        # Verify report is actually a direct report
        if report.manager_id != self.id:
            raise ValueError(
                f"Worker {report.id} is not a direct report of {self.id}"
            )

        # Verify delegated scope is subset of own scope
        own_scope = self.hiring_authority_scope
        for role in scope.allowed_roles:
            if role not in own_scope.allowed_roles:
                raise InsufficientHiringAuthority(
                    f"Cannot delegate role '{role}' - not in own authority"
                )

        if scope.max_cost > own_scope.max_cost:
            raise InsufficientHiringAuthority(
                f"Cannot delegate max_cost {scope.max_cost} exceeding own {own_scope.max_cost}"
            )

        # Verify budget is within own delegated budget
        if budget > self.delegated_budget:
            raise InsufficientHiringAuthority(
                f"Cannot delegate budget {budget} exceeding own {self.delegated_budget}"
            )

        # Update the report's hiring authority in database
        now = datetime.now()
        self.db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = ?,
                   updated_at = ?
               WHERE id = ?""",
            (scope.to_json(), budget, now, report.id)
        )
        self.db.connection.commit()

        # Invalidate report's cache
        report._worker_data = None

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
            # SessionState enum values match the runtime status strings
            runtime_status = new.value
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
    # REGISTRY SUPPORT
    # ==================

    def set_registry(self, registry: "SessionRegistry") -> None:
        """Set the session registry for this worker.

        Args:
            registry: SessionRegistry instance to use for creating sessions
        """
        self._session_registry = registry

    @property
    def session_registry(self) -> Optional["SessionRegistry"]:
        """Get the session registry (may be None if not set)."""
        return self._session_registry

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
        # Get registry - use instance registry or fall back to default
        registry = self._session_registry
        if registry is None:
            from .sessions.registry import get_default_registry
            registry = get_default_registry()

        # Create session via registry
        session = registry.create(config.provider, config)

        # Delegate to existing spawn_session for budget enforcement, attach, start
        self.spawn_session(session)

        return session

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
