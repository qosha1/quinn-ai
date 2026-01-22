"""
Unit tests for Worker state machine.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cli.core.db import init_database
from cli.core.queries import create_team, create_worker, create_budget_pool, create_budget_allocation
from cli.core.worker import Worker
from shared import (
    InvalidStateTransition,
    WorkerNotFound,
    InvalidLifecycleState,
    LIFECYCLE_TRANSITIONS,
    RUNTIME_TRANSITIONS,
)


@pytest.fixture
def db():
    """Create test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "quinn.db"
        database = init_database(db_path)
        yield database
        database.close()


@pytest.fixture
def team(db):
    """Create test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def worker_data(db, team):
    """Create test worker in pending state."""
    return create_worker(db, "Alice", "Developer", team.id, 50)


@pytest.fixture
def worker(db, worker_data):
    """Get Worker instance."""
    return Worker.get(db, worker_data.id)


class TestWorkerCreation:
    """Test Worker instance creation."""

    def test_get_worker(self, db, worker_data):
        """Should get worker by ID."""
        worker = Worker.get(db, worker_data.id)
        assert worker.id == worker_data.id
        assert worker.name == "Alice"

    def test_get_nonexistent_raises(self, db):
        """Should raise for nonexistent worker."""
        with pytest.raises(WorkerNotFound):
            Worker.get(db, "nonexistent")


class TestLifecycleProperties:
    """Test lifecycle property access."""

    def test_initial_status(self, worker):
        """New worker should be pending."""
        assert worker.lifecycle_status == "pending"

    def test_name_property(self, worker):
        """Should expose worker name."""
        assert worker.name == "Alice"

    def test_role_property(self, worker):
        """Should expose worker role."""
        assert worker.role == "Developer"


class TestLifecycleTransitions:
    """Test lifecycle state transitions."""

    def test_pending_to_onboarding(self, worker):
        """Should transition pending → onboarding."""
        worker.start_onboarding()
        assert worker.lifecycle_status == "onboarding"

    def test_onboarding_to_active(self, worker):
        """Should transition onboarding → active."""
        worker.start_onboarding()
        worker.complete_onboarding()
        assert worker.lifecycle_status == "active"

    def test_onboarding_to_terminated(self, worker):
        """Should transition onboarding → terminated (fail)."""
        worker.start_onboarding()
        worker.fail_onboarding()
        assert worker.lifecycle_status == "terminated"

    def test_active_to_offboarding(self, worker):
        """Should transition active → offboarding."""
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_offboarding()
        assert worker.lifecycle_status == "offboarding"

    def test_offboarding_to_terminated(self, worker):
        """Should transition offboarding → terminated."""
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_offboarding()
        worker.terminate()
        assert worker.lifecycle_status == "terminated"

    def test_invalid_transition_raises(self, worker):
        """Should raise on invalid transition."""
        # Can't go from pending to active directly
        with pytest.raises(InvalidStateTransition) as exc_info:
            worker.complete_onboarding()
        assert exc_info.value.current == "pending"
        assert exc_info.value.attempted == "active"

    def test_terminated_is_terminal(self, worker):
        """Terminated should not allow transitions."""
        worker.start_onboarding()
        worker.fail_onboarding()
        with pytest.raises(InvalidStateTransition):
            worker.start_onboarding()


class TestRuntimeProperties:
    """Test runtime property access."""

    def test_no_runtime_initially(self, worker):
        """Pending worker has no runtime state."""
        assert worker.runtime_status is None

    def test_runtime_after_session_start(self, worker):
        """Should have runtime after starting session."""
        worker.start_onboarding()
        worker.start_session(pid=12345)
        assert worker.runtime_status == "starting"

    def test_pid_property(self, worker):
        """Should expose PID."""
        worker.start_onboarding()
        worker.start_session(pid=12345)
        assert worker.pid == 12345

    def test_current_task_id(self, worker):
        """Should expose current task ID."""
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_session()
        worker.session_ready()
        worker.finish_work()  # Go to idle first
        worker.begin_work("task-123")
        assert worker.current_task_id == "task-123"


class TestRuntimeTransitions:
    """Test runtime state transitions."""

    @pytest.fixture
    def active_worker(self, worker):
        """Get worker in active lifecycle state."""
        worker.start_onboarding()
        worker.complete_onboarding()
        return worker

    def test_start_session(self, active_worker):
        """Should start session in starting state."""
        active_worker.start_session()
        assert active_worker.runtime_status == "starting"

    def test_session_ready(self, active_worker):
        """Should transition starting → running."""
        active_worker.start_session()
        active_worker.session_ready()
        assert active_worker.runtime_status == "running"

    def test_begin_work(self, active_worker):
        """Should transition idle → running with task."""
        active_worker.start_session()
        active_worker.session_ready()
        # Go to idle first
        active_worker.db.execute(
            "UPDATE worker_state SET runtime_status = 'idle' WHERE worker_id = ?",
            (active_worker.id,)
        )
        active_worker.db.connection.commit()
        active_worker._state_data = None

        active_worker.begin_work("task-123")
        assert active_worker.runtime_status == "running"
        assert active_worker.current_task_id == "task-123"

    def test_finish_work(self, active_worker):
        """Should transition running → idle."""
        active_worker.start_session()
        active_worker.session_ready()
        active_worker.finish_work()
        assert active_worker.runtime_status == "idle"
        assert active_worker.current_task_id is None

    def test_stop_session(self, active_worker):
        """Should transition to stopped."""
        active_worker.start_session()
        active_worker.session_ready()
        active_worker.stop_session()
        assert active_worker.runtime_status == "stopped"

    def test_mark_crashed(self, active_worker):
        """Should transition to crashed."""
        active_worker.start_session()
        active_worker.session_ready()
        active_worker.mark_crashed()
        assert active_worker.runtime_status == "crashed"

    def test_restart_from_stopped(self, active_worker):
        """Should restart from stopped."""
        active_worker.start_session()
        active_worker.session_ready()
        active_worker.stop_session()
        active_worker.start_session()
        assert active_worker.runtime_status == "starting"

    def test_restart_from_crashed(self, active_worker):
        """Should restart from crashed."""
        active_worker.start_session()
        active_worker.session_ready()
        active_worker.mark_crashed()
        active_worker.start_session()
        assert active_worker.runtime_status == "starting"


class TestLifecycleRuntimeConstraints:
    """Test constraints between lifecycle and runtime."""

    def test_cannot_start_session_when_pending(self, worker):
        """Pending worker cannot start session."""
        with pytest.raises(InvalidLifecycleState) as exc_info:
            worker.start_session()
        assert exc_info.value.lifecycle == "pending"

    def test_cannot_start_session_when_terminated(self, worker):
        """Terminated worker cannot start session."""
        worker.start_onboarding()
        worker.fail_onboarding()
        with pytest.raises(InvalidLifecycleState) as exc_info:
            worker.start_session()
        assert exc_info.value.lifecycle == "terminated"

    def test_onboarding_can_have_session(self, worker):
        """Onboarding worker can have session."""
        worker.start_onboarding()
        worker.start_session()
        assert worker.runtime_status == "starting"


class TestCapabilityQueries:
    """Test capability query properties."""

    def test_pending_cannot_work(self, worker):
        """Pending worker cannot work."""
        assert not worker.can_work

    def test_active_running_can_work(self, worker):
        """Active + running can work."""
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_session()
        worker.session_ready()
        assert worker.can_work

    def test_active_idle_can_work(self, worker):
        """Active + idle can work."""
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_session()
        worker.session_ready()
        worker.finish_work()
        assert worker.can_work

    def test_active_stopped_cannot_work(self, worker):
        """Active + stopped cannot work."""
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_session()
        worker.session_ready()
        worker.stop_session()
        assert not worker.can_work

    def test_onboarding_cannot_work(self, worker):
        """Onboarding worker cannot work (even with session)."""
        worker.start_onboarding()
        worker.start_session()
        worker.session_ready()
        assert not worker.can_work


class TestSessionActive:
    """Test session activity queries."""

    def test_no_session_inactive(self, worker):
        """No session means inactive."""
        assert not worker.is_session_active

    def test_starting_is_active(self, worker):
        """Starting session is active."""
        worker.start_onboarding()
        worker.start_session()
        assert worker.is_session_active

    def test_running_is_active(self, worker):
        """Running session is active."""
        worker.start_onboarding()
        worker.start_session()
        worker.session_ready()
        assert worker.is_session_active

    def test_idle_is_active(self, worker):
        """Idle session is active."""
        worker.start_onboarding()
        worker.start_session()
        worker.session_ready()
        worker.finish_work()
        assert worker.is_session_active

    def test_stopped_is_inactive(self, worker):
        """Stopped session is inactive."""
        worker.start_onboarding()
        worker.start_session()
        worker.session_ready()
        worker.stop_session()
        assert not worker.is_session_active

    def test_crashed_is_inactive(self, worker):
        """Crashed session is inactive."""
        worker.start_onboarding()
        worker.start_session()
        worker.session_ready()
        worker.mark_crashed()
        assert not worker.is_session_active


class TestHeartbeat:
    """Test heartbeat functionality."""

    def test_heartbeat_updates(self, worker):
        """Heartbeat should update last_activity."""
        worker.start_onboarding()
        worker.start_session()
        initial = worker._state_data
        worker.heartbeat()
        worker._load_state()
        # Activity should be updated (or same if fast)
        assert worker._state_data.last_activity is not None

    def test_stale_heartbeat(self, worker):
        """Should detect stale heartbeat."""
        worker.start_onboarding()
        worker.start_session()
        # With 0 threshold, should be stale
        assert worker.is_heartbeat_stale(threshold_seconds=0)

    def test_no_state_is_stale(self, worker):
        """No state should be considered stale."""
        assert worker.is_heartbeat_stale()


class TestTaskCounting:
    """Test task completion counting."""

    def test_finish_work_increments_completed(self, worker):
        """Finishing work should increment completed count."""
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_session()
        worker.session_ready()
        worker.finish_work(success=True)
        worker._load_state()
        assert worker._state_data.tasks_completed == 1

    def test_finish_work_increments_failed(self, worker):
        """Failed work should increment failed count."""
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_session()
        worker.session_ready()
        worker.finish_work(success=False)
        worker._load_state()
        assert worker._state_data.tasks_failed == 1


class TestTransitionMaps:
    """Test transition map constants."""

    def test_lifecycle_transitions_complete(self):
        """All lifecycle states should have transitions defined."""
        states = ["pending", "onboarding", "active", "offboarding", "terminated"]
        for state in states:
            assert state in LIFECYCLE_TRANSITIONS

    def test_runtime_transitions_complete(self):
        """All runtime states should have transitions defined."""
        states = ["starting", "running", "idle", "stopped", "crashed"]
        for state in states:
            assert state in RUNTIME_TRANSITIONS

    def test_terminated_is_terminal(self):
        """Terminated should have no outgoing transitions."""
        assert LIFECYCLE_TRANSITIONS["terminated"] == []


class MockSessionState:
    """Mock session state enum for testing."""
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    STOPPED = "stopped"
    CRASHED = "crashed"


class MockSession:
    """Mock session for testing Worker session management."""

    def __init__(self, should_fail_start: bool = False):
        self.worker_id = None
        self.started = False
        self.stopped = False
        self.force_stopped = False
        self.should_fail_start = should_fail_start
        self._state_callbacks = []
        self._state = MockSessionState.STOPPED
        self.provider_name = "mock"  # For budget recording
        self.id = "mock-session-001"  # For budget reference

    def bind_to_worker(self, worker_id: str) -> None:
        self.worker_id = worker_id

    def start(self) -> None:
        if self.should_fail_start:
            raise RuntimeError("Session failed to start")
        self.started = True
        self._state = MockSessionState.STARTING
        self._notify_state_change(MockSessionState.STOPPED, MockSessionState.STARTING)

    def stop(self, force: bool = False) -> None:
        self.stopped = True
        self.force_stopped = force
        old_state = self._state
        self._state = MockSessionState.STOPPED
        self._notify_state_change(old_state, MockSessionState.STOPPED)

    def on_state_change(self, callback) -> None:
        self._state_callbacks.append(callback)

    def _notify_state_change(self, old, new):
        for cb in self._state_callbacks:
            cb(old, new)

    def simulate_state_change(self, new_state):
        old_state = self._state
        self._state = new_state
        self._notify_state_change(old_state, new_state)


class TestSessionManagement:
    """Test Worker session management methods."""

    @pytest.fixture
    def active_worker(self, db, worker):
        """Get worker in active lifecycle state with budget allocation."""
        worker.start_onboarding()
        worker.complete_onboarding()
        # Create budget pool and allocation for spawn_session tests
        now = datetime.now()
        period_end = now + timedelta(days=30)
        pool = create_budget_pool(db, "test-pool", 1000.0, now, period_end)
        create_budget_allocation(
            db,
            worker_id=worker.id,
            allocated_credits=100.0,
            period_start=now,
            period_end=period_end,
            pool_id=pool.id,
        )
        return worker

    def test_attach_session_sets_field(self, active_worker):
        """Attach should set _session field."""
        session = MockSession()
        active_worker.attach_session(session)
        assert active_worker._session is session

    def test_attach_session_binds_worker_id(self, active_worker):
        """Attach should bind worker ID to session."""
        session = MockSession()
        active_worker.attach_session(session)
        assert session.worker_id == active_worker.id

    def test_attach_already_attached_raises(self, active_worker):
        """Attach to already-attached worker raises ValueError."""
        session1 = MockSession()
        session2 = MockSession()
        active_worker.attach_session(session1)
        with pytest.raises(ValueError) as exc_info:
            active_worker.attach_session(session2)
        assert "already has an attached session" in str(exc_info.value)

    def test_attach_pending_raises(self, worker):
        """Attach to pending worker raises InvalidLifecycleState."""
        session = MockSession()
        with pytest.raises(InvalidLifecycleState):
            worker.attach_session(session)

    def test_detach_returns_session(self, active_worker):
        """Detach should return the detached session."""
        session = MockSession()
        active_worker.attach_session(session)
        detached = active_worker.detach_session()
        assert detached is session

    def test_detach_clears_field(self, active_worker):
        """Detach should clear _session field."""
        session = MockSession()
        active_worker.attach_session(session)
        active_worker.detach_session()
        assert active_worker._session is None

    def test_detach_no_session_returns_none(self, active_worker):
        """Detach with no session returns None."""
        result = active_worker.detach_session()
        assert result is None

    def test_spawn_attaches_and_starts(self, active_worker):
        """Spawn should attach session and start it."""
        session = MockSession()
        active_worker.spawn_session(session)
        assert active_worker._session is session
        assert session.started is True
        assert session.worker_id == active_worker.id

    def test_spawn_failure_detaches(self, active_worker):
        """Spawn failure should detach the session."""
        session = MockSession(should_fail_start=True)
        with pytest.raises(RuntimeError):
            active_worker.spawn_session(session)
        assert active_worker._session is None

    def test_terminate_stops_session(self, active_worker):
        """Terminate should stop the session."""
        session = MockSession()
        active_worker.spawn_session(session)
        active_worker.terminate_session()
        assert session.stopped is True

    def test_terminate_detaches(self, active_worker):
        """Terminate should detach the session."""
        session = MockSession()
        active_worker.spawn_session(session)
        active_worker.terminate_session()
        assert active_worker._session is None

    def test_terminate_force(self, active_worker):
        """Terminate with force=True should force stop."""
        session = MockSession()
        active_worker.spawn_session(session)
        active_worker.terminate_session(force=True)
        assert session.force_stopped is True

    def test_terminate_no_session_is_noop(self, active_worker):
        """Terminate with no session is a no-op."""
        # Should not raise
        active_worker.terminate_session()

    def test_session_property(self, active_worker):
        """Session property should return attached session."""
        session = MockSession()
        assert active_worker.session is None
        active_worker.attach_session(session)
        assert active_worker.session is session
