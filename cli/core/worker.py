"""
Worker state machine implementation.

Workers have dual state machines:
- Lifecycle: HR/org-chart state (pending → onboarding → active → offboarding → terminated)
- Runtime: Process/session state (starting → running ⇄ idle → stopped/crashed)
"""

import json
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
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
    BudgetCheckResult,
)
from .logging import (
    get_logger,
    log_session_spawn,
    log_session_stop,
    log_worker_lifecycle,
)

_logger = get_logger(__name__)

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
    get_team_channel,
    subscribe_to_channel,
    unsubscribe_from_all_channels,
    create_channel,
    create_message,
    generate_id,
)
from .storage import StorageManager, WorkerStorageNotFound, StorageAlreadyFrozen
from .notifications import create_notification_bead
from .sessions.persistence import (
    create_session_record,
    update_session_state,
    update_session_pid,
    update_session_tmux_name,
    get_session_for_worker,
    delete_session_for_worker,
)

# Import bd client for creating beads (legacy, used by standalone functions)
from shared.bd.client import BdClient, BdCommandError

# Import beads client abstraction for Worker class
from .adapters.beads import BeadsClient, SubprocessBeadsClient

# Import messaging service
from .messaging import MessagingService

# Import shared business logic
from shared import (
    LIFECYCLE_TRANSITIONS,
    RUNTIME_TRANSITIONS,
    SESSION_ALLOWED_LIFECYCLES,
    InvalidStateTransition,
    WorkerNotFound,
    InvalidLifecycleState,
    ActiveSessionExistsError,
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
        org_path: Optional["Path"] = None,
        beads_client: Optional[BeadsClient] = None,
        messaging_service: Optional[MessagingService] = None,
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
        self._session: Optional["SessionInterface"] = None
        self._session_registry: Optional["SessionRegistry"] = session_registry
        self._org_path: Optional["Path"] = org_path
        self._beads_client: Optional[BeadsClient] = beads_client
        self._messaging_service: Optional[MessagingService] = messaging_service

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

    def _get_org_path(self) -> Path:
        """Get the org path from the database path.

        Derives org_path from db.db_path (quinn.db is at org_path/live/quinn.db).

        Returns:
            Path to the org folder

        Raises:
            ValueError: If org_path not set and cannot derive from db
        """
        if self._org_path is not None:
            return self._org_path
        # Derive from db path: org_path/live/quinn.db -> org_path
        return self.db.db_path.parent.parent

    def _get_storage_manager(self) -> StorageManager:
        """Get a StorageManager for this worker's org.

        Returns:
            StorageManager instance configured for this org
        """
        org_path = self._get_org_path()
        return StorageManager(org_path, self.db)

    def _get_beads_client(self) -> BeadsClient:
        """Get the BeadsClient for bead operations.

        Returns the injected client if available, otherwise creates a default
        SubprocessBeadsClient using the org's beads directory.

        Returns:
            BeadsClient instance
        """
        if self._beads_client is not None:
            return self._beads_client

        # Create default client using org's beads directory
        from .bd_wrapper import get_bundled_bd_path, get_org_beads_dir

        try:
            bd_path = get_bundled_bd_path()
            org_path = self._get_org_path()
            beads_dir = get_org_beads_dir(org_path)
            self._beads_client = SubprocessBeadsClient(bd_path, beads_dir)
        except FileNotFoundError:
            # bd binary not available - return a client that will fail gracefully
            from pathlib import Path
            self._beads_client = SubprocessBeadsClient(Path("/usr/bin/false"), None)

        return self._beads_client

    def _get_messaging_service(self) -> MessagingService:
        """Get the MessagingService for messaging operations.

        Returns the injected service if available, otherwise creates a default one.

        Returns:
            MessagingService instance
        """
        if self._messaging_service is not None:
            return self._messaging_service

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

        # Create worker storage folder (mirrors org-chart hierarchy)
        storage = self._get_storage_manager()
        storage.ensure_worker_storage(worker_data.id, reports_to=self.id)

        # Subscribe new worker to team channel
        team_channel = get_team_channel(self.db, self.team_id)
        if team_channel:
            subscribe_to_channel(self.db, team_channel.id, worker_data.id)

        # Return Worker instance
        new_worker = Worker(self.db, worker_data.id, org_path=self._get_org_path())
        new_worker._worker_data = worker_data

        # Update org-chart to reflect the new hire
        try:
            from .org_chart import update_org_chart, git_commit_org_chart

            org_path = self._get_org_path()
            update_org_chart(self.db, org_path)
            # Commit to git (best-effort, gracefully handles non-git repos)
            git_commit_org_chart(
                org_path=org_path,
                change_type="hired",
                worker_name=name,
                worker_role=role,
                details=f"Manager: {self.name} ({self.id})",
            )
        except (ImportError, OSError, subprocess.SubprocessError):
            # Intentionally swallowed: org-chart update is best-effort.
            # ImportError: org_chart module not available
            # OSError: file system issues, SubprocessError: git command failed
            pass

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
        old_status = self.lifecycle_status
        self._validate_lifecycle_transition("onboarding")
        update_worker_status(self.db, self.id, "onboarding")
        self._worker_data = None  # Invalidate cache
        log_worker_lifecycle(_logger, self.id, self.name, old_status, "onboarding")

    def complete_onboarding(self) -> None:
        """Transition from onboarding to active."""
        old_status = self.lifecycle_status
        self._validate_lifecycle_transition("active")
        update_worker_status(self.db, self.id, "active")
        self._worker_data = None
        log_worker_lifecycle(_logger, self.id, self.name, old_status, "active")

    def fail_onboarding(self) -> None:
        """Transition from onboarding to terminated (failed onboarding).

        Cleans up worker storage directory since worker never became active.
        Unlike normal termination, no review/archive is needed for failed onboarding.
        """
        old_status = self.lifecycle_status
        self._validate_lifecycle_transition("terminated")

        # Clean up worker storage - no review needed for failed onboarding
        try:
            storage = self._get_storage_manager()
            storage.delete_worker_storage(self.id)
        except WorkerStorageNotFound:
            # Storage doesn't exist yet - OK to continue
            pass

        update_worker_status(self.db, self.id, "terminated")
        self._worker_data = None
        log_worker_lifecycle(_logger, self.id, self.name, old_status, "terminated")

    def start_offboarding(self) -> None:
        """Transition from active to offboarding.

        Per CLAUDE.md: "On fire: freeze -> ask bead for review -> teammate
        saves useful to shared/ -> delete."

        When entering OFFBOARDING state:
        1. Freeze worker storage (mark read-only)
        2. Create a review bead assigned to manager for work handoff

        The manager will review frozen storage and archive useful files
        before the worker is terminated.
        """
        old_status = self.lifecycle_status
        self._validate_lifecycle_transition("offboarding")

        # Freeze worker storage for review (if exists)
        try:
            storage = self._get_storage_manager()
            storage.freeze_worker(self.id)
        except (WorkerStorageNotFound, StorageAlreadyFrozen):
            # Storage doesn't exist or already frozen - OK to continue
            pass

        # Create review bead for manager if worker has a manager
        if self.manager_id:
            self._create_offboarding_review_bead()

        update_worker_status(self.db, self.id, "offboarding")
        self._worker_data = None
        log_worker_lifecycle(_logger, self.id, self.name, old_status, "offboarding")

    def _create_offboarding_review_bead(self) -> None:
        """Create a review notification bead for the manager.

        Uses MessagingService to create a direct channel between the
        offboarding worker and their manager, send a handoff message,
        and create a notification bead for the review.
        """
        if not self.manager_id:
            return

        try:
            messaging = self._get_messaging_service()
            result = messaging.send_offboarding_notification(
                worker_id=self.id,
                worker_name=self.name,
                worker_role=self.role,
                manager_id=self.manager_id,
            )
            # Result is best-effort - we don't raise on failure
            if not result.success:
                _logger.debug(f"Offboarding notification failed: {result.error}")
        except Exception:
            # Intentionally swallowed: notification is best-effort during offboarding.
            # ImportError: messaging module not available
            # sqlite3.Error: database issues, ValueError: invalid data
            pass

        # Also create an 'ask' bead for tracking the review workflow
        self._create_offboarding_ask_bead()

    def _create_offboarding_ask_bead(self) -> Optional[str]:
        """Create an 'ask' bead for offboarding storage review.

        Per README workflow:
        1. Worker folder frozen (read-only) - done in start_offboarding
        2. System creates 'ask' bead: 'Offboard storage review: {worker-id}'
        3. Assigned teammate reviews, moves useful -> shared/, deletes rest
        4. On ask completion, system deletes worker folder

        Returns:
            Created bead ID, or None if creation failed.
        """
        if not self.manager_id:
            return None

        try:
            beads_client = self._get_beads_client()

            # Create the 'ask' bead with metadata linking to worker
            result = beads_client.create(
                title=f"Offboard storage review: {self.id}",
                type="ask",
                priority="P1",  # High priority
                description=(
                    f"Review frozen storage for terminated worker {self.name} ({self.id}).\n\n"
                    f"Role: {self.role}\n\n"
                    f"Actions required:\n"
                    f"1. Review files in frozen storage\n"
                    f"2. Move useful files to shared/archive/{self.id}/\n"
                    f"3. Close this bead when review is complete\n"
                    f"4. System will delete worker folder on bead closure"
                ),
                assignee=self.manager_id,
                metadata={
                    "worker_id": self.id,
                    "worker_name": self.name,
                    "manager_id": self.manager_id,
                    "workflow": "offboarding_storage_review",
                },
            )

            bead_id = result.bead_id if result.success else None
            if bead_id:
                # Store the bead ID in worker metadata for later lookup
                self._store_offboarding_ask_bead_id(bead_id)

            return bead_id

        except (BdCommandError, Exception):
            # Intentionally swallowed: bead creation is best-effort during offboarding.
            return None
        except (FileNotFoundError, OSError):
            # FileNotFoundError: bd CLI not installed
            # OSError: other file system issues with bd
            return None

    def _store_offboarding_ask_bead_id(self, bead_id: str) -> None:
        """Store the offboarding ask bead ID in worker metadata.

        Args:
            bead_id: The created bead ID
        """
        try:
            # Store in a metadata column or a separate table
            # For now, use worker_state's metadata or a simple approach
            now = datetime.now()
            self.db.execute(
                """UPDATE workers
                   SET offboarding_ask_bead_id = ?, updated_at = ?
                   WHERE id = ?""",
                (bead_id, now, self.id)
            )
            self.db.connection.commit()

            # Publish OFFBOARDING_ASK_CREATED event
            try:
                from .events import EventBus, EventType

                bus = EventBus(self.db)
                bus.publish(
                    EventType.OFFBOARDING_ASK_CREATED,
                    "offboarding",
                    bead_id,
                    {
                        "worker_id": self.id,
                        "worker_name": self.name,
                        "manager_id": self.manager_id,
                        "bead_id": bead_id,
                    },
                )
            except (ImportError, sqlite3.Error):
                # Intentionally swallowed: event publishing is best-effort.
                pass
        except sqlite3.Error:
            # Intentionally swallowed: storing bead ID is best-effort.
            pass

    def get_offboarding_ask_bead_id(self) -> Optional[str]:
        """Get the offboarding ask bead ID for this worker.

        Returns:
            The bead ID if set, None otherwise.
        """
        row = self.db.fetchone(
            "SELECT offboarding_ask_bead_id FROM workers WHERE id = ?",
            (self.id,)
        )
        if row and row["offboarding_ask_bead_id"]:
            return row["offboarding_ask_bead_id"]
        return None

    def terminate(self) -> None:
        """Terminate worker - freeze storage, update org-chart, fire event.

        Performs a full termination workflow:
        1. Stop session if running
        2. Freeze worker storage
        3. Unsubscribe from all channels
        4. Update lifecycle status to terminated
        5. Update org-chart
        6. Publish WORKER_FIRED event

        Raises:
            InvalidStateTransition: If not in a state that can transition to terminated
        """
        old_status = self.lifecycle_status

        # Stop session first if any
        self.terminate_session(force=True)

        # Freeze worker storage for review (if exists)
        try:
            storage = self._get_storage_manager()
            storage.freeze_worker(self.id)
        except (WorkerStorageNotFound, StorageAlreadyFrozen):
            # Storage doesn't exist or already frozen - OK to continue
            pass

        # Unsubscribe from all channels
        unsubscribe_from_all_channels(self.db, self.id)

        # Validate and update lifecycle status
        self._validate_lifecycle_transition("terminated")
        update_worker_status(self.db, self.id, "terminated")
        log_worker_lifecycle(_logger, self.id, self.name, old_status, "terminated")

        # Update org-chart
        try:
            from .org_chart import update_org_chart, git_commit_org_chart

            org_path = self._get_org_path()
            update_org_chart(self.db, org_path)
            # Commit to git (best-effort, gracefully handles non-git repos)
            git_commit_org_chart(
                org_path=org_path,
                change_type="terminated",
                worker_name=self.name,
                worker_role=self.role,
            )
        except (ImportError, OSError, subprocess.SubprocessError):
            # Intentionally swallowed: org-chart update is best-effort.
            # ImportError: org_chart module not available
            # OSError: file system issues, SubprocessError: git command failed
            pass

        # Publish WORKER_FIRED event
        try:
            from .events import EventBus, EventType

            bus = EventBus(self.db)
            bus.publish(
                EventType.WORKER_FIRED,
                "worker",
                self.id,
                {
                    "name": self.name,
                    "role": self.role,
                },
            )
        except (ImportError, sqlite3.Error):
            # Intentionally swallowed: event publishing is best-effort.
            pass

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
        budget_check = self._enforce_spawn_budget(session)

        # Phase 3: Attach and start session
        self._start_session(session)

        # Phase 4: Record spend and persist
        self._finalize_spawn(session, budget_check)

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
        # Check for existing active session before spawning
        # This prevents duplicate sessions for the same worker
        existing_session = get_session_for_worker(self.db, self.id)
        if existing_session is not None:
            # Only block if session is in an active state
            active_states = ("starting", "running", "idle")
            if existing_session.get("state") in active_states:
                raise ActiveSessionExistsError(
                    worker_id=self.id,
                    existing_session_id=existing_session["id"],
                )

        # Ensure worker_state row exists before session state callbacks fire.
        # The attach_session callback calls update_worker_runtime_status which
        # only does UPDATE (not INSERT), so the row must exist first.
        if self._state_data is None:
            self._load_state()
        if self._state_data is None:
            create_worker_state(self.db, self.id, pid=None)
            self._state_data = None  # Will be reloaded on next access

    def _enforce_spawn_budget(self, session: "SessionInterface") -> BudgetCheckResult:
        """Estimate cost and enforce budget constraints.

        Calculates the estimated cost of spawning this session based on
        the worker's cost tier, then verifies sufficient budget is available.

        Args:
            session: The session to be spawned (used for type consistency)

        Returns:
            BudgetCheckResult with allocation details for recording spend

        Raises:
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

        return budget_check

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
        except Exception:
            # If start fails, detach the session before re-raising
            self._session = None
            raise

    def _finalize_spawn(
        self,
        session: "SessionInterface",
        budget_check: BudgetCheckResult,
    ) -> None:
        """Record spend and persist session record.

        Records the session spawn cost against the budget allocation and
        persists the session record to the database for crash recovery.
        Handles race conditions where another process created a session
        between our precondition check and the database insert.

        Args:
            session: The started session to finalize
            budget_check: Budget check result from enforcement phase

        Raises:
            ActiveSessionExistsError: If race condition detected during persist
        """
        # Estimate cost again for recording (same calculation as enforcement)
        estimated_cost = estimate_cost(
            model_tier=self.cost_tier,
            input_tokens=DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
            output_tokens=DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
        )

        try:
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

            # Persist session record to database
            config = session.config
            working_dir = str(config.working_directory) if config.working_directory else None

            # Get tmux session name if available (from spawn result metadata)
            tmux_session_name = None
            if hasattr(session, '_spawn_result') and session._spawn_result:
                tmux_session_name = session._spawn_result.metadata.get('session_name')

            try:
                create_session_record(
                    db=self.db,
                    session_id=str(session.id),
                    worker_id=self.id,
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
                update_session_pid(self.db, str(session.id), session.pid)

            # Log successful session spawn
            log_session_spawn(
                _logger,
                worker_id=self.id,
                worker_name=self.name,
                provider=session.provider_name,
                session_id=str(session.id),
            )

        except Exception:
            # If finalization fails, detach the session
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
        existing = get_session_for_worker(self.db, self.id)
        existing_id = existing["id"] if existing else "unknown"
        raise ActiveSessionExistsError(
            worker_id=self.id,
            existing_session_id=existing_id,
        )

    def terminate_session(self, force: bool = False) -> None:
        """Terminate the current session.

        Stops the session, updates database record, and detaches from worker.

        Args:
            force: If True, force kill without cleanup
        """
        if self._session is None:
            return

        session_id = str(self._session.id)

        try:
            self._session.stop(force=force)
        finally:
            # Update session state in database to 'stopped'
            update_session_state(
                db=self.db,
                session_id=session_id,
                state="stopped",
                stopped_at=datetime.now(),
            )
            # Log session stop
            log_session_stop(_logger, self.id, self.name, force=force)
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


# ===================
# TERMINATION CLEANUP
# ===================


def check_offboarding_ask_completed(
    db: Database,
    worker_id: str,
    bd_client: Optional[BdClient] = None,
) -> bool:
    """Check if the offboarding ask bead for a worker is completed.

    Per README workflow:
    1. Worker folder frozen (read-only)
    2. System creates 'ask' bead: 'Offboard storage review: {worker-id}'
    3. Assigned teammate reviews, moves useful -> shared/, deletes rest
    4. On ask completion, system deletes worker folder

    This function checks step 4 - whether the ask bead has been closed.

    Args:
        db: Database instance
        worker_id: Worker ID to check
        bd_client: Optional BdClient instance (creates default if None)

    Returns:
        True if ask bead is closed, False otherwise (or if no bead exists)
    """
    # Get the worker's offboarding ask bead ID
    row = db.fetchone(
        "SELECT offboarding_ask_bead_id FROM workers WHERE id = ?",
        (worker_id,)
    )

    if not row or not row["offboarding_ask_bead_id"]:
        return False

    bead_id = row["offboarding_ask_bead_id"]

    # Check bead status via bd client
    if bd_client is None:
        bd_client = BdClient()

    try:
        issue = bd_client.get_issue(bead_id)
        if issue and issue.get("status") == "closed":
            return True
    except BdCommandError:
        pass

    return False


def process_offboarding_cleanup(
    db: Database,
    worker_id: str,
    storage_manager: StorageManager,
    bd_client: Optional[BdClient] = None,
    files_to_archive: Optional[list[Path]] = None,
) -> Optional[dict]:
    """Process offboarding cleanup if the ask bead is completed.

    This is the hook that should be called (e.g., by a cron job or event handler)
    to check if a worker's offboarding review has been completed and trigger
    the storage cleanup.

    Per README workflow:
    1. Worker folder frozen (read-only) - already done
    2. System creates 'ask' bead - already done
    3. Assigned teammate reviews, moves useful -> shared/, deletes rest
    4. On ask completion, system deletes worker folder <- this function does this

    Args:
        db: Database instance
        worker_id: Worker ID to process
        storage_manager: StorageManager for the org
        bd_client: Optional BdClient instance
        files_to_archive: Optional list of files to archive (if None, archives all)

    Returns:
        Cleanup result dict if cleanup was performed, None if not ready
    """
    # Check if worker is in terminated state
    worker_data = get_worker(db, worker_id)
    if worker_data is None or worker_data.status != "terminated":
        return None

    # Check if the ask bead is completed
    if not check_offboarding_ask_completed(db, worker_id, bd_client):
        return None

    # Publish OFFBOARDING_ASK_COMPLETED event
    bead_id = db.fetchone(
        "SELECT offboarding_ask_bead_id FROM workers WHERE id = ?",
        (worker_id,)
    )
    if bead_id and bead_id["offboarding_ask_bead_id"]:
        try:
            from .events import EventBus, EventType

            bus = EventBus(db)
            bus.publish(
                EventType.OFFBOARDING_ASK_COMPLETED,
                "offboarding",
                bead_id["offboarding_ask_bead_id"],
                {
                    "worker_id": worker_id,
                    "bead_id": bead_id["offboarding_ask_bead_id"],
                },
            )
        except (ImportError, sqlite3.Error):
            # Intentionally swallowed: event publishing is best-effort.
            pass

    # Bead is completed - run cleanup
    result = cleanup_terminated_worker(
        db=db,
        worker_id=worker_id,
        storage_manager=storage_manager,
        files_to_archive=files_to_archive,
    )

    # Publish OFFBOARDING_CLEANUP_DONE event
    if result:
        try:
            from .events import EventBus, EventType

            bus = EventBus(db)
            bus.publish(
                EventType.OFFBOARDING_CLEANUP_DONE,
                "offboarding",
                worker_id,
                {
                    "worker_id": worker_id,
                    "files_archived": result.get("files_archived", 0),
                    "archived_to": result.get("archived_to"),
                    "storage_deleted": result.get("storage_deleted", False),
                },
            )
        except (ImportError, sqlite3.Error):
            # Intentionally swallowed: event publishing is best-effort.
            pass

    return result


def cleanup_terminated_worker(
    db: Database,
    worker_id: str,
    storage_manager: StorageManager,
    files_to_archive: Optional[list[Path]] = None,
) -> dict:
    """Clean up a terminated worker's data.

    Per CLAUDE.md: "On fire: freeze -> ask bead for review -> teammate
    saves useful to shared/ -> delete."

    This function completes the termination workflow:
    1. Archive useful files to shared/archive/{worker_id}/
    2. Delete worker session data (frozen storage)
    3. Keep worker record in DB (for audit trail)

    The worker must already be in TERMINATED state. Use Worker.terminate()
    to transition a worker to terminated state and freeze their storage.

    Args:
        db: Database instance
        worker_id: Worker ID to clean up
        storage_manager: StorageManager for the org
        files_to_archive: List of file paths to archive from worker storage.
                         If None, archives all files. Paths should be relative
                         to worker storage root.

    Returns:
        Dict with cleanup results:
        - archived_to: Path to archive directory (or None if no files)
        - files_archived: Number of files archived
        - storage_deleted: Whether storage was deleted

    Raises:
        WorkerNotFound: If worker doesn't exist
        ValueError: If worker is not in TERMINATED state

    Example:
        # After manager reviews frozen storage and identifies useful files
        result = cleanup_terminated_worker(
            db=db,
            worker_id="worker-abc123",
            storage_manager=storage,
            files_to_archive=[Path("important-doc.md"), Path("config.yaml")],
        )
        print(f"Archived {result['files_archived']} files to {result['archived_to']}")
    """
    # Verify worker exists and is terminated
    worker_data = get_worker(db, worker_id)
    if worker_data is None:
        raise WorkerNotFound(worker_id)

    if worker_data.status != "terminated":
        raise ValueError(
            f"Worker {worker_id} is not terminated (status: {worker_data.status}). "
            "Use Worker.terminate() first."
        )

    result = {
        "archived_to": None,
        "files_archived": 0,
        "storage_deleted": False,
    }

    # Archive files if storage exists
    try:
        # Get list of files that exist
        existing_files = storage_manager.list_worker_files(worker_id)

        if existing_files:
            # Archive specified files or all files
            archive_files = files_to_archive if files_to_archive is not None else existing_files
            archive_path = storage_manager.archive_worker_files(worker_id, archive_files)
            result["archived_to"] = str(archive_path)
            result["files_archived"] = len(archive_files)

        # Delete worker storage
        if storage_manager.delete_worker_storage(worker_id):
            result["storage_deleted"] = True

    except WorkerStorageNotFound:
        # No storage to clean up - that's OK
        pass

    return result
