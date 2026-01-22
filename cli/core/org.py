"""
Org lifecycle state machine implementation.

Organizations have a single lifecycle state machine:
- uninitialized → initialized → running ⇄ stopped
"""

from typing import Optional

from .db import Database
from .queries import (
    get_org_state,
    update_org_status,
    create_team,
    create_worker,
    get_worker,
)
from .worker import Worker

# Import shared business logic
from shared import (
    ORG_TRANSITIONS,
    InvalidOrgTransition,
    OrgNotInitialized,
)


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
        return self._state_data.status if self._state_data else "uninitialized"

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
        return self.status == "running"

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

    def init(self, ceo_name: str, ceo_role: str = "CEO") -> Worker:
        """Initialize org with a CEO.

        Creates the root team and CEO worker.

        Args:
            ceo_name: Name for the CEO worker
            ceo_role: Role title for the CEO (default: "CEO")

        Returns:
            The created CEO Worker instance

        Raises:
            InvalidOrgTransition: If org is not uninitialized
        """
        self._validate_transition("initialized")

        # Create root team (Executive)
        team = create_team(self.db, "Executive")

        # Create CEO worker (no manager, high cost)
        ceo_data = create_worker(
            self.db,
            name=ceo_name,
            role=ceo_role,
            team_id=team.id,
            cost=100,  # CEO is highest cost
            manager_id=None,  # No manager - root of hierarchy
        )

        # Update org status
        update_org_status(self.db, "initialized", ceo_data.id)
        self._state_data = None  # Invalidate cache

        return Worker.get(self.db, ceo_data.id)

    def start(self) -> None:
        """Start the org (begin operations).

        Transitions org to running state. From initialized, also
        activates the CEO worker.

        Raises:
            InvalidOrgTransition: If org cannot be started
        """
        current = self.status

        if current == "initialized":
            self._validate_transition("running")

            # Activate CEO
            ceo = self.ceo
            if ceo:
                ceo.start_onboarding()
                ceo.complete_onboarding()

            update_org_status(self.db, "running", self.ceo_worker_id)

        elif current == "stopped":
            self._validate_transition("running")
            update_org_status(self.db, "running", self.ceo_worker_id)

        else:
            # Will raise InvalidOrgTransition
            self._validate_transition("running")

        self._state_data = None  # Invalidate cache

    def stop(self) -> None:
        """Stop the org (pause operations).

        Transitions org to stopped state. Worker sessions should be
        stopped separately before calling this.

        Raises:
            InvalidOrgTransition: If org is not running
        """
        self._validate_transition("stopped")
        update_org_status(self.db, "stopped", self.ceo_worker_id)
        self._state_data = None  # Invalidate cache

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
        """Get count of workers with active sessions."""
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
