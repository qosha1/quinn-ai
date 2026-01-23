"""
Org lifecycle state machine implementation.

Organizations have a single lifecycle state machine:
- uninitialized → initialized → running ⇄ stopped
"""

from typing import Optional

from datetime import datetime, timedelta

from .constants import DEFAULT_CEO_COST
from .db import Database
from .logging import get_logger, log_org_state_change
from .queries import (
    get_org_state,
    update_org_status,
    create_team,
    create_worker,
    create_budget_pool,
    create_budget_allocation,
    create_channel,
    subscribe_to_channel,
    get_team_channel,
    add_team_member,
)
from .worker import Worker

# Import shared business logic
from shared import (
    ORG_TRANSITIONS,
    InvalidOrgTransition,
)
from shared.enums import OrgStatus

_logger = get_logger(__name__)


class Org:
    """Organization with lifecycle state machine.

    Provides methods for managing org state transitions with validation.
    All state changes are persisted to the database.
    """

    def __init__(self, db: Database):
        """Initialize org wrapper.

        Args:
            db: Database instance
        """
        self.db = db
        self._state_data = None

    def _load_state(self) -> None:
        """Load org state from database."""
        self._state_data = get_org_state(self.db)

    def refresh(self) -> None:
        """Refresh state from database."""
        self._load_state()

    # ==================
    # PROPERTIES
    # ==================

    @property
    def status(self) -> str:
        """Get current org lifecycle status."""
        if self._state_data is None:
            self._load_state()
        return self._state_data.status if self._state_data else OrgStatus.UNINITIALIZED.value

    @property
    def ceo_worker_id(self) -> Optional[str]:
        """Get CEO worker ID, or None."""
        if self._state_data is None:
            self._load_state()
        return self._state_data.ceo_worker_id if self._state_data else None

    @property
    def ceo(self) -> Optional[Worker]:
        """Get CEO Worker instance, or None."""
        ceo_id = self.ceo_worker_id
        if ceo_id is None:
            return None
        return Worker.get(self.db, ceo_id)

    @property
    def is_operational(self) -> bool:
        """Check if org is operational (running)."""
        return self.status == OrgStatus.RUNNING.value

    @property
    def started_at(self):
        """Get last start time."""
        if self._state_data is None:
            self._load_state()
        return self._state_data.started_at if self._state_data else None

    @property
    def stopped_at(self):
        """Get last stop time."""
        if self._state_data is None:
            self._load_state()
        return self._state_data.stopped_at if self._state_data else None

    # ==================
    # LIFECYCLE TRANSITIONS
    # ==================

    def _validate_transition(self, new_status: str) -> None:
        """Validate org state transition.

        Args:
            new_status: Attempted new status

        Raises:
            InvalidOrgTransition: If transition is not allowed
        """
        current = self.status
        valid = ORG_TRANSITIONS.get(current, [])
        if new_status not in valid:
            raise InvalidOrgTransition(current, new_status, valid)

    def init(
        self,
        ceo_name: str,
        ceo_role: str = "CEO",
        initial_budget: float = 1000.0,
    ) -> Worker:
        """Initialize org with a CEO.

        Creates the root team, CEO worker, and initial budget allocation.

        Args:
            ceo_name: Name for the CEO worker
            ceo_role: Role title for the CEO (default: "CEO")
            initial_budget: Initial budget in dollars (default: $1000)

        Returns:
            The created CEO Worker instance

        Raises:
            InvalidOrgTransition: If org is not uninitialized
        """
        self._validate_transition(OrgStatus.INITIALIZED.value)

        # Create root team (Executive)
        team = create_team(self.db, "Executive")

        # Create CEO worker (no manager, high cost)
        ceo_data = create_worker(
            self.db,
            name=ceo_name,
            role=ceo_role,
            team_id=team.id,
            cost=DEFAULT_CEO_COST,
            manager_id=None,  # No manager - root of hierarchy
        )

        # Add CEO to team_members table (org-chart sync)
        add_team_member(self.db, team.id, ceo_data.id, role="lead")

        # Create budget pool and allocation for CEO
        now = datetime.now()
        period_end = now + timedelta(days=30)  # Monthly budget cycle
        pool = create_budget_pool(
            self.db,
            name="org-main",
            total_credits=initial_budget,
            period_start=now,
            period_end=period_end,
        )
        create_budget_allocation(
            self.db,
            worker_id=ceo_data.id,
            allocated_credits=initial_budget,
            period_start=now,
            period_end=period_end,
            pool_id=pool.id,
            can_delegate=True,  # CEO can delegate budget to reports
            delegation_limit=initial_budget * 0.5,  # Max 50% to single subordinate
        )

        # Subscribe CEO to their team channel (created automatically by create_team)
        team_channel = get_team_channel(self.db, team.id)
        if team_channel:
            subscribe_to_channel(self.db, team_channel.id, ceo_data.id)

        # Create default org-wide channels
        # #general - org-wide topic channel for announcements
        general_channel = create_channel(
            self.db,
            name="general",
            channel_type="topic",
            team_id=None,  # Org-wide, not tied to a specific team
        )
        subscribe_to_channel(self.db, general_channel.id, ceo_data.id)

        # #escalations - channel for escalation messages
        escalations_channel = create_channel(
            self.db,
            name="escalations",
            channel_type="topic",
            team_id=None,  # Org-wide for escalations
        )
        subscribe_to_channel(self.db, escalations_channel.id, ceo_data.id)

        # Initialize beads database for work tracking
        self._init_beads()

        # Update org status
        old_status = OrgStatus.UNINITIALIZED.value
        update_org_status(self.db, OrgStatus.INITIALIZED.value, ceo_data.id)
        self._state_data = None  # Invalidate cache

        log_org_state_change(_logger, old_status, OrgStatus.INITIALIZED.value)

        return Worker.get(self.db, ceo_data.id)

    def start(self) -> None:
        """Start the org (begin operations).

        Transitions org to running state. From initialized, also
        activates the CEO worker.

        Raises:
            InvalidOrgTransition: If org cannot be started
        """
        current = self.status

        if current == OrgStatus.INITIALIZED.value:
            self._validate_transition(OrgStatus.RUNNING.value)

            # Activate CEO
            ceo = self.ceo
            if ceo:
                ceo.start_onboarding()
                ceo.complete_onboarding()

            update_org_status(self.db, OrgStatus.RUNNING.value, self.ceo_worker_id)
            log_org_state_change(_logger, current, OrgStatus.RUNNING.value)

        elif current == OrgStatus.STOPPED.value:
            self._validate_transition(OrgStatus.RUNNING.value)
            update_org_status(self.db, OrgStatus.RUNNING.value, self.ceo_worker_id)
            log_org_state_change(_logger, current, OrgStatus.RUNNING.value)

        else:
            # Will raise InvalidOrgTransition
            self._validate_transition(OrgStatus.RUNNING.value)

        self._state_data = None  # Invalidate cache

    def _init_beads(self) -> None:
        """Initialize beads database for work tracking.

        Creates .beads directory and initializes bd with the org prefix.
        This is called during org init to set up work tracking.
        """
        import subprocess
        from pathlib import Path
        from .bd_wrapper import get_bundled_bd_path, get_org_beads_dir

        # Get org path from database path
        db_path = Path(self.db.db_path)
        org_path = db_path.parent.parent  # live/quinn.db -> org_path

        # Ensure .beads directory exists
        beads_dir = get_org_beads_dir(org_path)
        beads_dir.mkdir(parents=True, exist_ok=True)

        # Initialize beads with org prefix
        # Run from org directory so bd init creates database in the right place
        try:
            bd_path = get_bundled_bd_path()
            subprocess.run(
                [str(bd_path), "init", "--prefix", "quinnai"],
                cwd=str(org_path),
                capture_output=True,
                text=True,
            )
            # Ignore errors - may already be initialized
        except (FileNotFoundError, subprocess.SubprocessError):
            # FileNotFoundError: bd not installed, SubprocessError: init failed
            # Beads init is optional - org can function without it
            pass

    def stop(self) -> None:
        """Stop the org (pause operations).

        Transitions org to stopped state. Worker sessions should be
        stopped separately before calling this.

        Raises:
            InvalidOrgTransition: If org is not running
        """
        old_status = self.status
        self._validate_transition(OrgStatus.STOPPED.value)
        update_org_status(self.db, OrgStatus.STOPPED.value, self.ceo_worker_id)
        self._state_data = None  # Invalidate cache
        log_org_state_change(_logger, old_status, OrgStatus.STOPPED.value)

    # ==================
    # QUERY HELPERS
    # ==================

    @property
    def worker_count(self) -> int:
        """Get total number of workers in the org."""
        row = self.db.fetchone("SELECT COUNT(*) as count FROM workers")
        return row["count"] if row else 0

    @property
    def active_session_count(self) -> int:
        """Get count of active sessions from the sessions table.

        Falls back to worker_state if sessions table has no records.
        Active sessions are those in 'starting', 'running', or 'idle' state.
        """
        # First try the sessions table (new)
        row = self.db.fetchone(
            """SELECT COUNT(*) as count FROM sessions
               WHERE state IN ('starting', 'running', 'idle')"""
        )
        if row and row["count"] > 0:
            return row["count"]

        # Fall back to worker_state for backwards compatibility
        row = self.db.fetchone(
            """SELECT COUNT(*) as count FROM worker_state
               WHERE runtime_status IN ('starting', 'running', 'idle')"""
        )
        return row["count"] if row else 0

    @property
    def active_worker_count(self) -> int:
        """Get count of workers in active lifecycle state."""
        row = self.db.fetchone(
            "SELECT COUNT(*) as count FROM workers WHERE status = 'active'"
        )
        return row["count"] if row else 0

    # ==================
    # CLASS METHODS
    # ==================

    @classmethod
    def load(cls, db: Database) -> "Org":
        """Load org from database.

        Args:
            db: Database instance

        Returns:
            Org instance with state loaded
        """
        org = cls(db)
        org._load_state()
        return org
