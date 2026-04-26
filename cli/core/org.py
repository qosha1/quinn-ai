"""
Org lifecycle state machine implementation.

Organizations have a single lifecycle state machine:
- uninitialized → initialized → running ⇄ stopped
"""

from typing import Optional
from pathlib import Path

from datetime import datetime, timedelta

from .constants import DEFAULT_CEO_COST, DEFAULT_DELEGATION_LIMIT_PERCENT
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

    def __init__(self, db: Database, org_path: Optional[Path] = None):
        """Initialize org wrapper.

        Args:
            db: Database instance
            org_path: Optional org path (derived from db if not provided)
        """
        self.db = db
        self._state_data = None
        self._escalation_monitor = None
        self._activity_reporter = None
        self._session_capture = None

        # Derive org_path from db if not provided
        if org_path:
            self._org_path = org_path
        else:
            db_path = Path(self.db.db_path)
            self._org_path = db_path.parent.parent  # live/quinn.db -> org_path

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
    def org_path(self) -> Path:
        """Get organization path."""
        return self._org_path

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
        import json

        self._validate_transition(OrgStatus.INITIALIZED.value)

        # Create root team (Executive)
        team = create_team(self.db, "Executive")

        # Configure CEO hiring authority - can hire anyone
        hiring_authority_scope = json.dumps({
            "allowed_roles": ["*"],  # Can hire any role
            "max_cost": 100,         # Can hire up to max cost level
        })

        # Create CEO worker (no manager, high cost, full hiring authority)
        ceo_data = create_worker(
            self.db,
            name=ceo_name,
            role=ceo_role,
            team_id=team.id,
            cost=DEFAULT_CEO_COST,
            manager_id=None,  # No manager - root of hierarchy
            hiring_authority_scope=hiring_authority_scope,
            delegated_budget=int(initial_budget * 1000),  # Convert to credits, ample for hiring
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
            delegation_limit=initial_budget * DEFAULT_DELEGATION_LIMIT_PERCENT,
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

        # #board-channel - channel for board communications and escalations
        board_channel = create_channel(
            self.db,
            name="board-channel",
            channel_type="topic",
            team_id=None,  # Org-wide for board communications
        )
        subscribe_to_channel(self.db, board_channel.id, ceo_data.id)

        # Initialize beads database for work tracking
        self._init_beads()

        # Update org status
        old_status = OrgStatus.UNINITIALIZED.value
        update_org_status(self.db, OrgStatus.INITIALIZED.value, ceo_data.id)
        self._state_data = None  # Invalidate cache

        log_org_state_change(_logger, old_status, OrgStatus.INITIALIZED.value)

        return Worker.get(self.db, ceo_data.id)

    def start(self) -> tuple[str, str]:
        """Start the org (begin operations).

        Transitions org to running state. From initialized, also
        activates the CEO worker.

        Returns:
            Tuple of (old_status, new_status) for rollback support

        Raises:
            InvalidOrgTransition: If org cannot be started
        """
        old_status = self.status

        if old_status == OrgStatus.INITIALIZED.value:
            self._validate_transition(OrgStatus.RUNNING.value)

            # Activate CEO
            ceo = self.ceo
            if ceo:
                ceo.start_onboarding()
                ceo.complete_onboarding()

            # Deliver CEO briefing if it exists
            briefing_path = self._get_briefing_path()
            if briefing_path.exists():
                self._deliver_ceo_briefing(ceo.id, briefing_path)

            update_org_status(self.db, OrgStatus.RUNNING.value, self.ceo_worker_id)
            log_org_state_change(_logger, old_status, OrgStatus.RUNNING.value)

        elif old_status == OrgStatus.STOPPED.value:
            self._validate_transition(OrgStatus.RUNNING.value)
            update_org_status(self.db, OrgStatus.RUNNING.value, self.ceo_worker_id)
            log_org_state_change(_logger, old_status, OrgStatus.RUNNING.value)

        else:
            # Will raise InvalidOrgTransition
            self._validate_transition(OrgStatus.RUNNING.value)

        self._state_data = None  # Invalidate cache
        new_status = self.status

        # NOTE: Monitoring services (escalation_monitor, session_capture, activity_reporter)
        # are NOT started here. These services die when the CLI process exits, making them
        # ineffective when started from `qn org start`. Only Board UI should manage monitors
        # since it has persistent process lifecycle. See quinnai-3gqq for design rationale.

        return (old_status, new_status)

    def rollback_to_status(self, target_status: str) -> None:
        """Rollback org to previous status (for error recovery).

        Args:
            target_status: Status to rollback to
        """
        current_status = self.status
        update_org_status(self.db, target_status, self.ceo_worker_id)
        log_org_state_change(_logger, current_status, target_status)
        _logger.info(f"Rolled back org status after error: {current_status} -> {target_status}")
        self._state_data = None  # Invalidate cache

    def _get_briefing_path(self) -> Path:
        """Get path to CEO briefing markdown file."""
        db_path = Path(self.db.db_path)
        org_path = db_path.parent.parent  # live/quinn.db -> org_path
        return org_path / "config" / "ceo_briefing.md"

    def _deliver_ceo_briefing(self, ceo_id: str, briefing_path: Path) -> None:
        """Deliver CEO briefing as initial message with notification.

        Args:
            ceo_id: CEO worker ID
            briefing_path: Path to briefing markdown file
        """
        from .queries import create_message, generate_id
        from .notifications import create_notification_bead

        briefing_content = briefing_path.read_text()

        # Get board-channel ID
        channel_row = self.db.fetchone(
            "SELECT id FROM channels WHERE name = 'board-channel'"
        )
        if not channel_row:
            return  # Board channel doesn't exist yet

        # Check if briefing already delivered (prevent duplicates on restart)
        existing = self.db.fetchone(
            """SELECT id FROM messages
               WHERE channel_id = ? AND content LIKE '# CEO Briefing%'""",
            (channel_row["id"],)
        )
        if existing:
            return  # Already delivered

        # Create message from CEO
        message = create_message(
            db=self.db,
            channel_id=channel_row["id"],
            from_worker_id=ceo_id,
            content=f"# CEO Briefing\n\n{briefing_content}",
            priority=0,  # Highest priority
            time_sensitivity="immediate",
            message_id=generate_id("msg"),
        )

        # Create notification for CEO (normally sender doesn't get notified)
        # But for briefing, we want the CEO to see it as a notification
        create_notification_bead(
            db=self.db,
            worker_id=ceo_id,
            message_id=message.id,
            channel_id=channel_row["id"],
            priority=0,
        )

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

        # Stop monitoring services before stopping org
        self._stop_escalation_monitor()
        self._stop_session_capture()
        self._stop_activity_reporter()

        update_org_status(self.db, OrgStatus.STOPPED.value, self.ceo_worker_id)
        self._state_data = None  # Invalidate cache
        log_org_state_change(_logger, old_status, OrgStatus.STOPPED.value)

    def _start_escalation_monitor(self) -> None:
        """Start the continuation engine for graduated worker nudging.

        Replaces the old EscalationMonitor with the new ContinuationEngine
        that uses ActivitySensor and SessionPrompter for graduated prompts.

        This is called automatically by start_with_session().
        """
        if self._escalation_monitor is not None and self._escalation_monitor.is_running():
            _logger.debug("Continuation engine already running")
            return

        from cli.core.continuation_engine import ContinuationEngine
        from cli.core.constants import CONTINUATION_ENGINE_POLL_INTERVAL

        self._escalation_monitor = ContinuationEngine(
            self._org_path,
            poll_interval=CONTINUATION_ENGINE_POLL_INTERVAL
        )
        self._escalation_monitor.start()
        _logger.info("Continuation engine started")

    def _stop_escalation_monitor(self) -> None:
        """Stop the continuation engine.

        This is called automatically by stop().
        """
        if self._escalation_monitor is None:
            return

        if self._escalation_monitor.is_running():
            self._escalation_monitor.stop()
            _logger.info("Continuation engine stopped")

        self._escalation_monitor = None

    def _start_activity_reporter(self) -> None:
        """Start the activity reporter for worker session tracking.

        This is called automatically by start().
        """
        if self._activity_reporter is not None and self._activity_reporter.is_running():
            _logger.debug("Activity reporter already running")
            return

        from cli.core.activity_reporter import ActivityReporter
        from cli.core.constants import (
            DEFAULT_ACTIVITY_REPORT_INTERVAL,
            DEFAULT_ACTIVITY_CREATE_BEADS,
        )

        # Create and start activity reporter
        self._activity_reporter = ActivityReporter(
            org_path=self._org_path,
            report_interval=DEFAULT_ACTIVITY_REPORT_INTERVAL,
            create_beads=DEFAULT_ACTIVITY_CREATE_BEADS,
        )
        self._activity_reporter.start()
        _logger.info("Activity reporter started")

    def _stop_activity_reporter(self) -> None:
        """Stop the activity reporter.

        This is called automatically by stop().
        """
        if self._activity_reporter is None:
            return

        if self._activity_reporter.is_running():
            self._activity_reporter.stop()
            _logger.info("Activity reporter stopped")

        self._activity_reporter = None

    def _start_session_capture(self) -> None:
        """Start the session capture service for worker activity tracking.

        This is called automatically by start().
        """
        if self._session_capture is not None and self._session_capture.is_running():
            _logger.debug("Session capture service already running")
            return

        from cli.core.session_capture import SessionCaptureService
        from cli.core.constants import DEFAULT_SESSION_CAPTURE_INTERVAL

        # Create and start session capture
        self._session_capture = SessionCaptureService(
            org_path=self._org_path,
            capture_interval=DEFAULT_SESSION_CAPTURE_INTERVAL,
        )
        self._session_capture.start()
        _logger.info("Session capture service started")

    def _stop_session_capture(self) -> None:
        """Stop the session capture service.

        This is called automatically by stop().
        """
        if self._session_capture is None:
            return

        if self._session_capture.is_running():
            self._session_capture.stop()
            _logger.info("Session capture service stopped")

        self._session_capture = None

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
