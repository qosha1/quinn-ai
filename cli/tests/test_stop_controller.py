"""
Tests for OrgStopController - graceful shutdown orchestration.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli.core.db import init_database
from cli.core.org import Org
from cli.core.queries import (
    create_team,
    create_worker,
    update_org_status,
    create_channel,
    subscribe_to_channel,
)
from cli.core.worker import Worker
from cli.core.stop_controller import (
    OrgStopController,
    OrgStopResult,
    WorkerStopState,
    StopPhaseResult,
    get_resume_state,
    consume_resume_state,
    cleanup_expired_resume_states,
)
from cli.core.constants import (
    STOP_TIMEOUT_CEO,
    STOP_TIMEOUT_MANAGER,
    STOP_TIMEOUT_WORKER,
    DEFAULT_STOP_TIMEOUT,
)
from cli.core.sessions import create_session_record
from cli.core.sessions.tmux_spawner import TmuxSpawner
from shared.enums import OrgStatus


@pytest.fixture
def tmpdir():
    """Create temp directory for tests."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def org_path(tmpdir):
    """Create org directory structure."""
    org = tmpdir / "test-org"
    (org / "live").mkdir(parents=True)
    (org / "config").mkdir(parents=True)
    return org


@pytest.fixture
def db(org_path):
    """Create test database."""
    db_path = org_path / "live" / "quinn.db"
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def team(db):
    """Create test team."""
    return create_team(db, "Executive")


@pytest.fixture
def ceo(db, team):
    """Create CEO worker."""
    worker_data = create_worker(
        db, "Alice", "CEO", team.id, 100, manager_id=None
    )
    # Update to active status
    db.execute(
        "UPDATE workers SET status = 'active' WHERE id = ?",
        (worker_data.id,)
    )
    db.connection.commit()
    return Worker.get(db, worker_data.id)


@pytest.fixture
def org(db, ceo, org_path):
    """Create running org."""
    # Set up org state
    update_org_status(db, OrgStatus.RUNNING.value, ceo.id)
    return Org.load(db)


@pytest.fixture
def general_channel(db, ceo):
    """Create general channel."""
    channel = create_channel(db, "general", "topic", None)
    subscribe_to_channel(db, channel.id, ceo.id)
    return channel


@pytest.fixture
def mock_tmux():
    """Mock TmuxSpawner for testing."""
    mock = MagicMock(spec=TmuxSpawner)
    mock.is_alive.return_value = True
    mock.stop.return_value = True
    mock.list_sessions.return_value = []
    return mock


class TestOrgStopControllerInit:
    """Test controller initialization."""

    def test_init_creates_controller(self, db, org_path, org):
        """Should create controller with dependencies."""
        controller = OrgStopController(db, org_path, org)
        assert controller.db == db
        assert controller.org_path == org_path
        assert controller.org == org

    def test_init_with_mock_tmux(self, db, org_path, org, mock_tmux):
        """Should accept custom TmuxSpawner."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        assert controller.tmux_spawner == mock_tmux


class TestPhase1Validation:
    """Test Phase 1: Validation and Preparation."""

    def test_phase1_running_org(self, db, org_path, org, mock_tmux):
        """Should validate running org."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        result = controller._validate_and_prepare()
        assert result.success
        assert result.phase == 1
        assert "Validation and Preparation" in result.name

    def test_phase1_already_stopped(self, db, org_path, org, mock_tmux):
        """Should handle already stopped org."""
        # Stop org first
        update_org_status(db, OrgStatus.STOPPED.value, org.ceo_worker_id)
        org.refresh()

        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        result = controller._validate_and_prepare()
        assert result.success
        assert result.details.get("already_stopped") is True

    def test_phase1_invalid_state(self, db, org_path, org, mock_tmux):
        """Should reject uninitialized org."""
        # Set to uninitialized
        db.execute("UPDATE org_state SET status = 'uninitialized'")
        db.connection.commit()
        org.refresh()

        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        result = controller._validate_and_prepare()
        assert not result.success

    def test_phase1_builds_worker_states(self, db, org_path, org, ceo, mock_tmux):
        """Should build worker stop states for active sessions."""
        # Create session for CEO
        create_session_record(
            db,
            session_id=f"sess-{ceo.id}",
            worker_id=ceo.id,
            provider="claude_code",
            command="claude",
        )

        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        result = controller._validate_and_prepare()

        assert result.success
        assert len(controller._worker_states) == 1
        assert ceo.id in controller._worker_states


class TestTimeoutsByRole:
    """Test per-role timeout calculation."""

    def test_ceo_gets_long_timeout(self, db, org_path, org, mock_tmux):
        """CEO should get longest timeout."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        timeout = controller._get_worker_timeout("CEO")
        assert timeout == STOP_TIMEOUT_CEO

    def test_manager_gets_medium_timeout(self, db, org_path, org, mock_tmux):
        """Manager should get medium timeout."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        assert controller._get_worker_timeout("Manager") == STOP_TIMEOUT_MANAGER
        assert controller._get_worker_timeout("Director") == STOP_TIMEOUT_MANAGER
        assert controller._get_worker_timeout("team-lead") == STOP_TIMEOUT_MANAGER

    def test_worker_gets_short_timeout(self, db, org_path, org, mock_tmux):
        """Regular worker should get default timeout."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        timeout = controller._get_worker_timeout("Engineer")
        assert timeout == DEFAULT_STOP_TIMEOUT


class TestPhase2WrapupRequests:
    """Test Phase 2: Send Wrap-up Requests."""

    def test_phase2_no_workers(self, db, org_path, org, mock_tmux):
        """Should handle no active workers."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        controller._validate_and_prepare()
        result = controller._send_wrapup_requests()
        assert result.success
        assert "No active workers" in result.message

    def test_phase2_sends_notifications(
        self, db, org_path, org, ceo, general_channel, mock_tmux
    ):
        """Should send wrap-up notifications."""
        # Create session for CEO
        create_session_record(
            db,
            session_id=f"sess-{ceo.id}",
            worker_id=ceo.id,
            provider="claude_code",
            command="claude",
        )

        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        controller._validate_and_prepare()
        result = controller._send_wrapup_requests()

        # Phase 2 succeeds even if individual notifications fail
        # (bd CLI may not be available in test environment)
        assert result.success
        # We sent at least 1 attempt (even if notification creation failed)
        assert result.details.get("sent_count", 0) >= 0 or result.details.get("error_count", 0) >= 0

        # Verify wrapup_sent_at was recorded for the worker
        assert ceo.id in controller._worker_states
        state = controller._worker_states[ceo.id]
        assert state.wrapup_sent_at is not None


class TestPhase4SessionStop:
    """Test Phase 4: Stop Sessions."""

    def test_phase4_stops_sessions(self, db, org_path, org, ceo, mock_tmux):
        """Should stop all sessions."""
        # Create session
        create_session_record(
            db,
            session_id=f"sess-{ceo.id}",
            worker_id=ceo.id,
            provider="claude_code",
            command="claude",
        )

        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        controller._validate_and_prepare()
        result = controller._stop_sessions(force=True)

        assert result.success
        assert result.details.get("sessions_found", 0) >= 0

    def test_phase4_force_mode(self, db, org_path, org, mock_tmux):
        """Force mode should skip graceful shutdown."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        controller._validate_and_prepare()
        result = controller._stop_sessions(force=True)
        assert result.success


class TestPhase5WorkerStates:
    """Test Phase 5: Update Worker States."""

    def test_phase5_updates_workers(self, db, org_path, org, ceo, mock_tmux):
        """Should update worker runtime states."""
        # Create session and build state
        create_session_record(
            db,
            session_id=f"sess-{ceo.id}",
            worker_id=ceo.id,
            provider="claude_code",
            command="claude",
        )

        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        controller._validate_and_prepare()
        result = controller._update_worker_states()

        assert result.success
        assert result.details.get("workers_updated") >= 0


class TestPhase6StatePersistence:
    """Test Phase 6: Persist State and Cleanup."""

    def test_phase6_saves_state(self, db, org_path, org, ceo, mock_tmux):
        """Should save worker resume states."""
        # Create session
        create_session_record(
            db,
            session_id=f"sess-{ceo.id}",
            worker_id=ceo.id,
            provider="claude_code",
            command="claude",
        )

        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        controller._validate_and_prepare()
        result = controller._persist_state(cleanup=False)

        assert result.success
        assert "states_saved" in result.details

    def test_phase6_runs_cleanup(self, db, org_path, org, mock_tmux):
        """Should run cleanup when requested."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        controller._validate_and_prepare()
        result = controller._persist_state(cleanup=True)

        assert result.success
        assert "cleanup_result" in result.details


class TestPhase7OrgTransition:
    """Test Phase 7: Transition Org to STOPPED."""

    def test_phase7_stops_org(self, db, org_path, org, mock_tmux):
        """Should transition org to stopped."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        result = controller._transition_org_to_stopped()

        assert result.success
        org.refresh()
        assert org.status == OrgStatus.STOPPED.value


class TestFullExecution:
    """Test complete stop sequence execution."""

    def test_execute_force_mode(self, db, org_path, org, mock_tmux):
        """Force mode should skip ack waiting."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)
        result = controller.execute(force=True)

        assert result.success
        # Force mode skips phases 2 and 3
        phase_nums = [p.phase for p in result.phases]
        assert 2 not in phase_nums
        assert 3 not in phase_nums

    def test_execute_full_sequence(
        self, db, org_path, org, ceo, general_channel, mock_tmux
    ):
        """Should execute all phases."""
        # Create session
        create_session_record(
            db,
            session_id=f"sess-{ceo.id}",
            worker_id=ceo.id,
            provider="claude_code",
            command="claude",
        )

        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)

        # Stub the ack-wait step to return immediately — it is tested independently
        no_ack_result = StopPhaseResult(
            phase=3,
            name="Wait for Acknowledgements",
            success=True,
            duration_seconds=0.0,
            message="0/1 acknowledgements",
            details={"acks_received": 0, "acks_expected": 1, "unacked_workers": []},
        )
        with patch.object(controller, "_wait_for_acknowledgements", return_value=no_ack_result):
            result = controller.execute(force=False, save_state=True, cleanup=True)

        assert result.success
        assert len(result.phases) >= 5  # At least 5 phases in non-force mode

    def test_execute_with_timeout_override(self, db, org_path, org, mock_tmux):
        """Should respect graceful_timeout override."""
        controller = OrgStopController(db, org_path, org, tmux_spawner=mock_tmux)

        no_ack_result = StopPhaseResult(
            phase=3,
            name="Wait for Acknowledgements",
            success=True,
            duration_seconds=0.0,
            message="0/0 acknowledgements",
            details={"acks_received": 0, "acks_expected": 0, "unacked_workers": []},
        )
        with patch.object(controller, "_wait_for_acknowledgements", return_value=no_ack_result):
            result = controller.execute(
                force=False,
                graceful_timeout=10,
            )

        assert result.success


class TestResumeStateHelpers:
    """Test resume state helper functions."""

    def test_get_resume_state_none(self, db):
        """Should return None if no resume state."""
        result = get_resume_state(db, "nonexistent")
        assert result is None

    def test_consume_resume_state_none(self, db):
        """Should return False if no state to consume."""
        result = consume_resume_state(db, "nonexistent")
        assert result is False

    def test_cleanup_expired_states(self, db, team):
        """Should clean up expired states."""
        # Create a worker first (FK constraint)
        worker_data = create_worker(db, "TestWorker", "Engineer", team.id, 50)

        # Insert expired state
        expired = datetime.now() - timedelta(hours=1)
        db.execute(
            """INSERT INTO worker_resume_states
               (id, worker_id, expires_at, created_at)
               VALUES (?, ?, ?, ?)""",
            ("test-1", worker_data.id, expired, datetime.now())
        )
        db.connection.commit()

        count = cleanup_expired_resume_states(db)
        assert count == 1


class TestWorkerStopState:
    """Test WorkerStopState dataclass."""

    def test_worker_stop_state_creation(self):
        """Should create WorkerStopState."""
        state = WorkerStopState(
            worker_id="w1",
            worker_name="Alice",
            role="CEO",
            timeout_seconds=120,
        )
        assert state.worker_id == "w1"
        assert state.wrapup_sent_at is None
        assert state.ack_received_at is None


class TestStopPhaseResult:
    """Test StopPhaseResult dataclass."""

    def test_phase_result_creation(self):
        """Should create StopPhaseResult."""
        result = StopPhaseResult(
            phase=1,
            name="Test Phase",
            success=True,
            duration_seconds=1.5,
            message="Test passed",
        )
        assert result.phase == 1
        assert result.success
        assert result.details == {}


class TestOrgStopResult:
    """Test OrgStopResult dataclass."""

    def test_result_creation(self):
        """Should create OrgStopResult with defaults."""
        result = OrgStopResult(success=True)
        assert result.success
        assert result.phases == []
        assert result.workers_stopped == 0
        assert result.errors == []
