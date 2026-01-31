"""
Worker base class - composition of all manager classes.

This is the main Worker class that delegates to specialized managers for
each concern (storage, budget, hiring, delegation, lifecycle, session).
"""

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..db import Database
from ..queries import get_worker, get_worker_state
from shared import WorkerNotFound

# Import managers
from .storage_manager import WorkerStorageManager
from .budget_manager import WorkerBudgetManager
from .hiring import WorkerHiringManager, HiringScope
from .delegation import WorkerDelegationManager
from .lifecycle_manager import WorkerLifecycleManager
from .session_manager import WorkerSessionManager

if TYPE_CHECKING:
    from ..session import SessionInterface, SessionConfig
    from ..sessions.registry import SessionRegistry
    from ..adapters.beads import BeadsClient
    from ..messaging import MessagingService


class Worker:
    """Worker with dual state machine (lifecycle + runtime).

    Provides methods for managing worker state transitions with validation.
    All state changes are persisted to the database.

    This class uses composition to delegate responsibilities to specialized managers:
    - WorkerStorageManager: Storage operations
    - WorkerBudgetManager: Budget management
    - WorkerHiringManager: Hiring operations
    - WorkerDelegationManager: Delegation operations
    - WorkerLifecycleManager: Lifecycle transitions
    - WorkerSessionManager: Session management
    """

    def __init__(
        self,
        db: Database,
        worker_id: str,
        session_registry: Optional["SessionRegistry"] = None,
        org_path: Optional["Path"] = None,
        beads_client: Optional["BeadsClient"] = None,
        messaging_service: Optional["MessagingService"] = None,
    ):
        """Initialize worker wrapper.

        Args:
            db: Database instance
            worker_id: Worker ID to manage
            session_registry: Optional SessionRegistry for creating sessions via spawn().
                             If not provided, spawn() will use the default registry.
            org_path: Optional path to org folder. Required for terminate() to
                     freeze storage and update org-chart.
            beads_client: Optional BeadsClient for bead operations. If not provided,
                         a default SubprocessBeadsClient will be created on demand.
            messaging_service: Optional MessagingService for messaging operations.
                              If not provided, a default will be created on demand.
        """
        self.db = db
        self.id = worker_id
        self._worker_data = None
        self._state_data = None
        self._org_path: Optional["Path"] = org_path
        self._beads_client: Optional["BeadsClient"] = beads_client
        self._messaging_service: Optional["MessagingService"] = messaging_service

        # Initialize managers (composition pattern)
        self._storage_mgr = WorkerStorageManager(self)
        self._budget_mgr = WorkerBudgetManager(self)
        self._hiring_mgr = WorkerHiringManager(self)
        self._delegation_mgr = WorkerDelegationManager(self)
        self._lifecycle_mgr = WorkerLifecycleManager(self)
        self._session_mgr = WorkerSessionManager(self)

        # Set session registry if provided
        if session_registry is not None:
            self._session_mgr.set_registry(session_registry)

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

    def _get_beads_client(self) -> "BeadsClient":
        """Get the BeadsClient for bead operations.

        Returns the injected client if available, otherwise creates a default
        SubprocessBeadsClient using the org's beads directory.

        Returns:
            BeadsClient instance
        """
        if self._beads_client is not None:
            return self._beads_client

        # Create default client using org's beads directory
        from ..bd_wrapper import get_bundled_bd_path, get_org_beads_dir
        from ..adapters.beads import SubprocessBeadsClient

        try:
            bd_path = get_bundled_bd_path()
            org_path = self._storage_mgr.get_org_path()
            beads_dir = get_org_beads_dir(org_path)
            self._beads_client = SubprocessBeadsClient(bd_path, beads_dir)
        except FileNotFoundError:
            # bd binary not available - return a client that will fail gracefully
            self._beads_client = SubprocessBeadsClient(Path("/usr/bin/false"), None)

        return self._beads_client

    def _get_messaging_service(self) -> "MessagingService":
        """Get the MessagingService for messaging operations.

        Returns the injected service if available, otherwise creates a default one.

        Returns:
            MessagingService instance
        """
        if self._messaging_service is not None:
            return self._messaging_service

        from ..messaging import MessagingService
        self._messaging_service = MessagingService(self.db)
        return self._messaging_service

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

    @property
    def preferred_provider(self) -> Optional[str]:
        """Get worker's preferred CLI provider.

        Returns the worker's preferred provider name (e.g., 'claude_code', 'cursor'),
        or None if no preference is set (uses org default).
        """
        if self._worker_data is None:
            self._load_worker()
        return self._worker_data.preferred_provider

    # ==================
    # HIRING AUTHORITY PROPERTIES (delegate to hiring manager)
    # ==================

    @property
    def hiring_authority_scope(self) -> HiringScope:
        """Get worker's hiring authority scope."""
        return self._hiring_mgr.get_hiring_authority_scope()

    @property
    def delegated_budget(self) -> int:
        """Get worker's delegated hiring budget."""
        return self._hiring_mgr.get_delegated_budget()

    @property
    def max_reports(self) -> int:
        """Get maximum direct reports allowed for this worker."""
        return self._hiring_mgr.get_max_reports()

    @property
    def direct_reports_count(self) -> int:
        """Get current count of direct reports."""
        return self._hiring_mgr.get_direct_reports_count()

    # ==================
    # RUNTIME PROPERTIES (delegate to session manager)
    # ==================

    @property
    def runtime_status(self) -> Optional[str]:
        """Get current runtime status, or None if no session."""
        return self._session_mgr.runtime_status

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

        Returns True if lifecycle is 'active' AND runtime is not 'stopped' or 'crashed'.
        Workers can accept work if active and either:
        - No session (runtime_status is None)
        - Session is running/idle (runtime_status in ['starting', 'running', 'idle'])
        """
        if self.lifecycle_status != "active":
            return False

        # If no runtime state, worker can accept work (session can be spawned)
        runtime = self.runtime_status
        if runtime is None:
            return True

        # Worker cannot accept work if session is stopped or crashed
        return runtime not in ("stopped", "crashed")

    @property
    def cost_tier(self) -> str:
        """Get worker's cost tier based on cost score."""
        return self._budget_mgr.get_cost_tier()

    @property
    def is_session_active(self) -> bool:
        """Check if worker session is active."""
        return self._session_mgr.is_session_active

    @property
    def session(self) -> Optional["SessionInterface"]:
        """Get the current session instance, if any."""
        return self._session_mgr.session

    @property
    def _session(self) -> Optional["SessionInterface"]:
        """Get the current session instance (private accessor for backward compatibility)."""
        return self._session_mgr._session

    # ==================
    # HIRING METHODS (delegate to hiring manager)
    # ==================

    def can_hire(self, role: str, cost: int) -> tuple[bool, str]:
        """Check if this worker can hire for a given role and cost."""
        return self._hiring_mgr.can_hire(role, cost)

    def hire(
        self,
        name: str,
        role: str,
        skills: dict[str, int],
        cost: int,
    ) -> "Worker":
        """Hire a new worker under this worker."""
        return self._hiring_mgr.hire(name, role, skills, cost)

    # ==================
    # DELEGATION METHODS (delegate to delegation manager)
    # ==================

    def delegate_authority(
        self,
        report: "Worker",
        budget: int,
        scope: HiringScope,
        granted_by_cli_user: Optional[str] = None,
        expires_at: Optional = None,
    ):
        """Delegate hiring authority to a direct report."""
        return self._delegation_mgr.delegate_authority(
            report, budget, scope, granted_by_cli_user, expires_at
        )

    def revoke_authority(
        self,
        delegate: "Worker",
        cascade: bool = False,
        reason: Optional[str] = None,
    ):
        """Revoke hiring authority from a delegate."""
        return self._delegation_mgr.revoke_authority(delegate, cascade, reason)

    # ==================
    # LIFECYCLE TRANSITIONS (delegate to lifecycle manager)
    # ==================

    def _validate_lifecycle_transition(self, new_status: str) -> None:
        """Validate lifecycle state transition (exposed for backward compatibility)."""
        self._lifecycle_mgr._validate_lifecycle_transition(new_status)

    def start_onboarding(self) -> None:
        """Transition from pending to onboarding."""
        self._lifecycle_mgr.start_onboarding()

    def complete_onboarding(self) -> None:
        """Transition from onboarding to active."""
        self._lifecycle_mgr.complete_onboarding()

    def fail_onboarding(self) -> None:
        """Transition from onboarding to terminated (failed onboarding)."""
        self._lifecycle_mgr.fail_onboarding()

    def start_offboarding(self) -> None:
        """Transition from active to offboarding."""
        self._lifecycle_mgr.start_offboarding()

    def get_offboarding_ask_bead_id(self) -> Optional[str]:
        """Get the offboarding ask bead ID for this worker."""
        return self._lifecycle_mgr.get_offboarding_ask_bead_id()

    def suspend(self, force: bool = False) -> None:
        """Suspend worker - temporarily inactive."""
        self._lifecycle_mgr.suspend(force)

    def unsuspend(self) -> None:
        """Resume suspended worker - return to active state."""
        self._lifecycle_mgr.unsuspend()

    def terminate(self) -> None:
        """Terminate worker - freeze storage, update org-chart, fire event."""
        self._lifecycle_mgr.terminate()

    # ==================
    # RUNTIME TRANSITIONS (delegate to session manager)
    # ==================

    def start_session(self, pid: Optional[int] = None) -> None:
        """Start a new session (starting state)."""
        self._session_mgr.start_session(pid)

    def session_ready(self) -> None:
        """Mark session as ready (running state)."""
        self._session_mgr.session_ready()

    def begin_work(self, task_id: str) -> None:
        """Begin working on a task."""
        self._session_mgr.begin_work(task_id)

    def finish_work(self, success: bool = True) -> None:
        """Finish current work and return to idle."""
        self._session_mgr.finish_work(success)

    def stop_session(self) -> None:
        """Gracefully stop session."""
        self._session_mgr.stop_session()

    def mark_crashed(self) -> None:
        """Mark session as crashed."""
        self._session_mgr.mark_crashed()

    # ==================
    # HEARTBEAT (delegate to session manager)
    # ==================

    def heartbeat(self) -> None:
        """Record heartbeat to indicate liveness."""
        self._session_mgr.heartbeat()

    def is_heartbeat_stale(self, threshold_seconds: int = None) -> bool:
        """Check if heartbeat is stale."""
        if threshold_seconds is None:
            from ..constants import DEFAULT_HEARTBEAT_THRESHOLD
            threshold_seconds = DEFAULT_HEARTBEAT_THRESHOLD
        return self._session_mgr.is_heartbeat_stale(threshold_seconds)

    # ==================
    # SESSION MANAGEMENT (delegate to session manager)
    # ==================

    def attach_session(self, session: "SessionInterface") -> None:
        """Attach a session instance to this worker."""
        self._session_mgr.attach_session(session)

    def detach_session(self) -> Optional["SessionInterface"]:
        """Detach the current session from this worker."""
        return self._session_mgr.detach_session()

    def spawn_session(self, session: "SessionInterface") -> None:
        """Spawn a session for this worker."""
        self._session_mgr.spawn_session(session)

    def terminate_session(self, force: bool = False) -> None:
        """Terminate the current session."""
        self._session_mgr.terminate_session(force)

    # ==================
    # REGISTRY SUPPORT (delegate to session manager)
    # ==================

    def set_registry(self, registry: "SessionRegistry") -> None:
        """Set the session registry for this worker."""
        self._session_mgr.set_registry(registry)

    @property
    def session_registry(self) -> Optional["SessionRegistry"]:
        """Get the session registry (may be None if not set)."""
        return self._session_mgr._session_registry

    def spawn(self, config: "SessionConfig") -> "SessionInterface":
        """Spawn a session for this worker using the registry."""
        return self._session_mgr.spawn(config)

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
