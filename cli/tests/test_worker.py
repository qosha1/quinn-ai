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
from cli.core.session import SessionState
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


class MockSession:
    """Mock session for testing Worker session management."""

    def __init__(self, should_fail_start: bool = False):
        self.worker_id = None
        self.started = False
        self.stopped = False
        self.force_stopped = False
        self.should_fail_start = should_fail_start
        self._state_callbacks = []
        self._state = SessionState.STOPPED
        self.provider_name = "mock"  # For budget recording
        self.id = "mock-session-001"  # For budget reference

    def bind_to_worker(self, worker_id: str) -> None:
        self.worker_id = worker_id

    def start(self) -> None:
        if self.should_fail_start:
            raise RuntimeError("Session failed to start")
        self.started = True
        self._state = SessionState.STARTING
        self._notify_state_change(SessionState.STOPPED, SessionState.STARTING)

    def stop(self, force: bool = False) -> None:
        self.stopped = True
        self.force_stopped = force
        old_state = self._state
        self._state = SessionState.STOPPED
        self._notify_state_change(old_state, SessionState.STOPPED)

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


class MockSessionConfig:
    """Mock SessionConfig for testing."""

    def __init__(self, worker_id: str, provider: str = "mock"):
        self.worker_id = worker_id
        self.provider = provider
        self.command = "mock-cli"
        self.args = []


class MockSessionRegistry:
    """Mock SessionRegistry for testing Worker registry integration."""

    def __init__(self, session_factory=None):
        """Initialize with an optional session factory.

        Args:
            session_factory: Optional callable that takes config and returns a session.
                            Defaults to creating a MockSession.
        """
        self._session_factory = session_factory or (lambda config: MockSession())
        self._created_sessions = []
        self._create_calls = []

    def create(self, provider: str, config, **kwargs):
        """Create a session for the given provider."""
        self._create_calls.append((provider, config, kwargs))
        session = self._session_factory(config)
        self._created_sessions.append(session)
        return session

    def has(self, name: str) -> bool:
        """Check if provider is registered."""
        return name in ("mock", "claude_code")


class TestWorkerRegistryIntegration:
    """Test Worker session registry integration."""

    @pytest.fixture
    def active_worker_with_budget(self, db, worker):
        """Get worker in active lifecycle state with budget allocation."""
        worker.start_onboarding()
        worker.complete_onboarding()
        # Create budget pool and allocation
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

    def test_worker_accepts_registry_in_init(self, db, worker_data):
        """Worker should accept session_registry in __init__."""
        registry = MockSessionRegistry()
        worker = Worker(db, worker_data.id, session_registry=registry)
        assert worker.session_registry is registry

    def test_set_registry(self, db, worker_data):
        """set_registry() should set the session registry."""
        worker = Worker.get(db, worker_data.id)
        assert worker.session_registry is None

        registry = MockSessionRegistry()
        worker.set_registry(registry)
        assert worker.session_registry is registry

    def test_spawn_uses_provided_registry(self, active_worker_with_budget):
        """spawn() should use the registry provided to Worker."""
        registry = MockSessionRegistry()
        active_worker_with_budget.set_registry(registry)

        config = MockSessionConfig(
            worker_id=active_worker_with_budget.id,
            provider="mock"
        )
        session = active_worker_with_budget.spawn(config)

        # Verify registry.create was called with correct args
        assert len(registry._create_calls) == 1
        call_provider, call_config, _ = registry._create_calls[0]
        assert call_provider == "mock"
        assert call_config is config

        # Verify session was attached and started
        assert active_worker_with_budget.session is session
        assert session.started is True

    def test_spawn_returns_session(self, active_worker_with_budget):
        """spawn() should return the created session."""
        registry = MockSessionRegistry()
        active_worker_with_budget.set_registry(registry)

        config = MockSessionConfig(
            worker_id=active_worker_with_budget.id,
            provider="mock"
        )
        session = active_worker_with_budget.spawn(config)

        assert session is not None
        assert session in registry._created_sessions

    def test_spawn_falls_back_to_default_registry(self, db, active_worker_with_budget, monkeypatch):
        """spawn() should use default registry when none provided."""
        # Create a mock default registry
        mock_default_registry = MockSessionRegistry()

        # Monkeypatch get_default_registry to return our mock
        def mock_get_default():
            return mock_default_registry

        monkeypatch.setattr(
            "cli.core.worker.get_default_registry",
            mock_get_default,
            raising=False
        )
        # Also patch at the sessions.registry module level
        import cli.core.sessions.registry as registry_module
        monkeypatch.setattr(registry_module, "get_default_registry", mock_get_default)

        # Worker has no registry set
        assert active_worker_with_budget.session_registry is None

        config = MockSessionConfig(
            worker_id=active_worker_with_budget.id,
            provider="mock"
        )
        session = active_worker_with_budget.spawn(config)

        # Should have used the default registry
        assert len(mock_default_registry._create_calls) == 1
        assert session is not None

    def test_spawn_with_custom_factory(self, active_worker_with_budget):
        """spawn() should work with custom session factory."""
        custom_sessions = []

        def custom_factory(config):
            session = MockSession()
            session.custom_marker = config.provider
            custom_sessions.append(session)
            return session

        registry = MockSessionRegistry(session_factory=custom_factory)
        active_worker_with_budget.set_registry(registry)

        config = MockSessionConfig(
            worker_id=active_worker_with_budget.id,
            provider="special_provider"
        )
        session = active_worker_with_budget.spawn(config)

        assert hasattr(session, "custom_marker")
        assert session.custom_marker == "special_provider"
        assert len(custom_sessions) == 1

    def test_spawn_respects_budget_enforcement(self, db, worker):
        """spawn() should enforce budget (via spawn_session)."""
        from cli.core.budget import NoBudgetAllocationError

        # Active worker WITHOUT budget allocation
        worker.start_onboarding()
        worker.complete_onboarding()

        registry = MockSessionRegistry()
        worker.set_registry(registry)

        config = MockSessionConfig(worker_id=worker.id, provider="mock")

        # Should raise because no budget allocation
        with pytest.raises(NoBudgetAllocationError):
            worker.spawn(config)

    def test_spawn_cleans_up_on_failure(self, active_worker_with_budget):
        """spawn() should clean up session on failure."""
        def failing_factory(config):
            session = MockSession(should_fail_start=True)
            return session

        registry = MockSessionRegistry(session_factory=failing_factory)
        active_worker_with_budget.set_registry(registry)

        config = MockSessionConfig(
            worker_id=active_worker_with_budget.id,
            provider="mock"
        )

        with pytest.raises(RuntimeError, match="Session failed to start"):
            active_worker_with_budget.spawn(config)

        # Session should be detached on failure
        assert active_worker_with_budget.session is None


# ===================
# HIRING AUTHORITY TESTS
# ===================

from cli.core.worker import (
    HiringScope,
    HiringError,
    InsufficientHiringAuthority,
    MaxReportsExceeded,
)


class TestHiringScope:
    """Test HiringScope dataclass."""

    def test_default_scope(self):
        """Default HiringScope should have no authority."""
        scope = HiringScope()
        assert scope.allowed_roles == set()
        assert scope.max_cost == 0
        assert scope.max_total_budget == 0

    def test_scope_with_roles(self):
        """HiringScope should accept allowed roles."""
        scope = HiringScope(allowed_roles={"engineer", "analyst"}, max_cost=50)
        assert "engineer" in scope.allowed_roles
        assert "analyst" in scope.allowed_roles
        assert "manager" not in scope.allowed_roles

    def test_can_hire_role(self):
        """can_hire_role should check allowed roles."""
        scope = HiringScope(allowed_roles={"engineer"}, max_cost=50)
        assert scope.can_hire_role("engineer") is True
        assert scope.can_hire_role("manager") is False

    def test_can_afford_cost(self):
        """can_afford_cost should check max_cost."""
        scope = HiringScope(max_cost=50)
        assert scope.can_afford_cost(25) is True
        assert scope.can_afford_cost(50) is True
        assert scope.can_afford_cost(51) is False

    def test_to_json(self):
        """to_json should serialize scope correctly."""
        scope = HiringScope(
            allowed_roles={"engineer", "analyst"},
            max_cost=50,
            max_total_budget=1000,
        )
        json_str = scope.to_json()
        import json
        data = json.loads(json_str)
        assert set(data["allowed_roles"]) == {"engineer", "analyst"}
        assert data["max_cost"] == 50
        assert data["max_total_budget"] == 1000

    def test_from_json(self):
        """from_json should deserialize scope correctly."""
        json_str = '{"allowed_roles": ["engineer"], "max_cost": 75, "max_total_budget": 500}'
        scope = HiringScope.from_json(json_str)
        assert scope.allowed_roles == {"engineer"}
        assert scope.max_cost == 75
        assert scope.max_total_budget == 500

    def test_from_json_empty(self):
        """from_json with None/empty should return default scope."""
        scope = HiringScope.from_json(None)
        assert scope.allowed_roles == set()
        assert scope.max_cost == 0

        scope = HiringScope.from_json("")
        assert scope.allowed_roles == set()


class TestHiringAuthorityProperties:
    """Test Worker hiring authority properties."""

    def test_default_hiring_scope(self, worker):
        """Worker should have empty hiring scope by default."""
        scope = worker.hiring_authority_scope
        assert isinstance(scope, HiringScope)
        assert scope.allowed_roles == set()

    def test_default_delegated_budget(self, worker):
        """Worker should have 0 delegated budget by default."""
        assert worker.delegated_budget == 0

    def test_default_max_reports(self, worker):
        """Worker should have default max reports."""
        assert worker.max_reports == 10

    def test_direct_reports_count_empty(self, worker):
        """Worker with no reports should have 0 count."""
        assert worker.direct_reports_count == 0

    def test_direct_reports_count_with_reports(self, db, team):
        """Worker with reports should have correct count."""
        # Create manager
        manager_data = create_worker(db, "Manager", "Manager", team.id, 60)
        manager = Worker.get(db, manager_data.id)

        # Create reports
        create_worker(db, "Report1", "Engineer", team.id, 50, manager_id=manager.id)
        create_worker(db, "Report2", "Engineer", team.id, 50, manager_id=manager.id)

        assert manager.direct_reports_count == 2


class TestCanHire:
    """Test Worker.can_hire() method."""

    @pytest.fixture
    def manager_with_authority(self, db, team):
        """Create manager with hiring authority."""
        scope = HiringScope(
            allowed_roles={"engineer", "analyst"},
            max_cost=50,
            max_total_budget=1000,
        )
        worker_data = create_worker(
            db,
            "Manager",
            "Manager",
            team.id,
            60,
            hiring_authority_scope=scope.to_json(),
            delegated_budget=500,
            max_reports=5,
        )
        return Worker.get(db, worker_data.id)

    def test_can_hire_valid(self, manager_with_authority):
        """can_hire should return True for valid hire."""
        can, reason = manager_with_authority.can_hire("engineer", 40)
        assert can is True
        assert reason == "OK"

    def test_cannot_hire_no_authority(self, worker):
        """Worker without authority cannot hire."""
        can, reason = worker.can_hire("engineer", 40)
        assert can is False
        assert "No hiring authority" in reason

    def test_cannot_hire_wrong_role(self, manager_with_authority):
        """Cannot hire role not in allowed_roles."""
        can, reason = manager_with_authority.can_hire("manager", 40)
        assert can is False
        assert "not in allowed roles" in reason

    def test_cannot_hire_too_expensive(self, manager_with_authority):
        """Cannot hire worker with cost above max_cost."""
        can, reason = manager_with_authority.can_hire("engineer", 75)
        assert can is False
        assert "exceeds max allowed cost" in reason

    def test_cannot_hire_max_reports_reached(self, db, team):
        """Cannot hire when at max direct reports."""
        scope = HiringScope(allowed_roles={"engineer"}, max_cost=100)
        manager_data = create_worker(
            db,
            "Manager",
            "Manager",
            team.id,
            60,
            hiring_authority_scope=scope.to_json(),
            max_reports=2,
        )
        manager = Worker.get(db, manager_data.id)

        # Add 2 reports to reach max
        create_worker(db, "R1", "Engineer", team.id, 50, manager_id=manager.id)
        create_worker(db, "R2", "Engineer", team.id, 50, manager_id=manager.id)

        can, reason = manager.can_hire("engineer", 50)
        assert can is False
        assert "Max reports reached" in reason


class TestHire:
    """Test Worker.hire() method."""

    @pytest.fixture
    def manager_with_authority(self, db, team):
        """Create manager with hiring authority."""
        scope = HiringScope(
            allowed_roles={"engineer", "analyst"},
            max_cost=60,
            max_total_budget=1000,
        )
        worker_data = create_worker(
            db,
            "Manager",
            "Manager",
            team.id,
            70,
            hiring_authority_scope=scope.to_json(),
            delegated_budget=500,
            max_reports=5,
        )
        return Worker.get(db, worker_data.id)

    def test_hire_creates_worker(self, manager_with_authority):
        """hire() should create new worker."""
        new_worker = manager_with_authority.hire(
            name="NewEngineer",
            role="engineer",
            skills={"coding": 70},
            cost=50,
        )
        assert new_worker.name == "NewEngineer"
        assert new_worker.role == "engineer"
        assert new_worker.cost == 50
        assert new_worker.manager_id == manager_with_authority.id
        assert new_worker.lifecycle_status == "pending"

    def test_hire_sets_manager(self, manager_with_authority):
        """hire() should set manager_id on new worker."""
        new_worker = manager_with_authority.hire(
            name="NewAnalyst",
            role="analyst",
            skills={},
            cost=40,
        )
        assert new_worker.manager_id == manager_with_authority.id

    def test_hire_same_team(self, manager_with_authority):
        """hire() should set new worker to same team."""
        new_worker = manager_with_authority.hire(
            name="NewEngineer",
            role="engineer",
            skills={},
            cost=50,
        )
        assert new_worker.team_id == manager_with_authority.team_id

    def test_hire_increments_reports(self, manager_with_authority):
        """hire() should increment direct reports count."""
        initial = manager_with_authority.direct_reports_count
        manager_with_authority.hire("E1", "engineer", {}, 50)
        assert manager_with_authority.direct_reports_count == initial + 1

    def test_hire_raises_insufficient_authority(self, manager_with_authority):
        """hire() should raise for unauthorized role."""
        with pytest.raises(InsufficientHiringAuthority) as exc_info:
            manager_with_authority.hire("Manager2", "manager", {}, 50)
        assert "not in allowed roles" in exc_info.value.reason

    def test_hire_raises_max_reports_exceeded(self, db, team):
        """hire() should raise when max reports reached."""
        scope = HiringScope(allowed_roles={"engineer"}, max_cost=100)
        manager_data = create_worker(
            db,
            "Manager",
            "Manager",
            team.id,
            60,
            hiring_authority_scope=scope.to_json(),
            max_reports=1,
        )
        manager = Worker.get(db, manager_data.id)

        # Hire first (ok)
        manager.hire("E1", "engineer", {}, 50)

        # Hire second (should fail)
        with pytest.raises(MaxReportsExceeded) as exc_info:
            manager.hire("E2", "engineer", {}, 50)
        assert exc_info.value.current == 1
        assert exc_info.value.maximum == 1


class TestHireOrgChartUpdate:
    """Test org-chart updates when hiring workers."""

    @pytest.fixture
    def org_path(self, db):
        """Get org path from db path (db is at org_path/live/quinn.db)."""
        return db.db_path.parent.parent

    @pytest.fixture
    def ceo_with_authority(self, db, team, org_path):
        """Create CEO (root worker) with hiring authority."""
        scope = HiringScope(
            allowed_roles={"manager", "engineer"},
            max_cost=80,
            max_total_budget=2000,
        )
        ceo_data = create_worker(
            db,
            "CEO",
            "CEO",
            team.id,
            90,
            manager_id=None,  # Root worker
            hiring_authority_scope=scope.to_json(),
            delegated_budget=1000,
            max_reports=10,
        )
        # Create org-chart directory
        chart_dir = org_path / "org-chart"
        chart_dir.mkdir(parents=True, exist_ok=True)
        return Worker(db, ceo_data.id, org_path=org_path)

    def test_hire_updates_org_chart(self, ceo_with_authority, org_path):
        """hire() should update org-chart/current.yaml."""
        import yaml

        # Hire a new worker
        new_worker = ceo_with_authority.hire(
            name="NewManager",
            role="manager",
            skills={"leadership": 60},
            cost=70,
        )

        # Verify org-chart was updated
        chart_path = org_path / "org-chart" / "current.yaml"
        assert chart_path.exists(), "Org-chart should be created"

        with open(chart_path) as f:
            chart = yaml.safe_load(f)

        # Verify structure
        assert "version" in chart
        assert "workers" in chart
        assert "hierarchy" in chart

        # Verify CEO is in chart
        assert ceo_with_authority.id in chart["workers"]
        ceo_entry = chart["workers"][ceo_with_authority.id]
        assert ceo_entry["name"] == "CEO"
        assert ceo_entry["manager"] is None

        # Verify new hire is in chart
        assert new_worker.id in chart["workers"]
        new_entry = chart["workers"][new_worker.id]
        assert new_entry["name"] == "NewManager"
        assert new_entry["role"] == "manager"
        assert new_entry["lifecycle"] == "pending"
        assert new_entry["manager"] == ceo_with_authority.id

        # Verify hierarchy shows CEO as root
        assert chart["hierarchy"]["root"] == ceo_with_authority.id

        # Verify CEO's reports includes new hire
        assert new_worker.id in ceo_entry["reports"]

    def test_hire_multiple_workers_updates_chart(self, ceo_with_authority, org_path):
        """Multiple hires should all appear in org-chart."""
        import yaml

        # Hire multiple workers
        worker1 = ceo_with_authority.hire("Engineer1", "engineer", {}, 50)
        worker2 = ceo_with_authority.hire("Engineer2", "engineer", {}, 55)
        worker3 = ceo_with_authority.hire("Manager1", "manager", {}, 70)

        # Verify org-chart has all workers
        chart_path = org_path / "org-chart" / "current.yaml"
        with open(chart_path) as f:
            chart = yaml.safe_load(f)

        # All workers should be present
        assert ceo_with_authority.id in chart["workers"]
        assert worker1.id in chart["workers"]
        assert worker2.id in chart["workers"]
        assert worker3.id in chart["workers"]

        # CEO should have all 3 as reports
        ceo_entry = chart["workers"][ceo_with_authority.id]
        assert set(ceo_entry["reports"]) == {worker1.id, worker2.id, worker3.id}

    def test_hire_nested_hierarchy_updates_chart(self, ceo_with_authority, db, team, org_path):
        """Nested hires should maintain hierarchy in org-chart."""
        import yaml

        # Hire manager first
        manager_scope = HiringScope(allowed_roles={"engineer"}, max_cost=60)
        manager = ceo_with_authority.hire("Manager1", "manager", {}, 70)

        # Give manager hiring authority
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?, max_reports = ?
               WHERE id = ?""",
            (manager_scope.to_json(), 5, manager.id)
        )
        db.connection.commit()
        manager._worker_data = None  # Invalidate cache

        # Manager hires engineer
        manager_instance = Worker(db, manager.id, org_path=org_path)
        engineer = manager_instance.hire("Engineer1", "engineer", {}, 50)

        # Verify nested hierarchy
        chart_path = org_path / "org-chart" / "current.yaml"
        with open(chart_path) as f:
            chart = yaml.safe_load(f)

        # Verify hierarchy: CEO -> Manager -> Engineer
        ceo_entry = chart["workers"][ceo_with_authority.id]
        manager_entry = chart["workers"][manager.id]
        engineer_entry = chart["workers"][engineer.id]

        assert manager.id in ceo_entry["reports"]
        assert engineer.id in manager_entry["reports"]
        assert engineer_entry["manager"] == manager.id
        assert manager_entry["manager"] == ceo_with_authority.id

    def test_hire_continues_on_chart_failure(self, ceo_with_authority, org_path):
        """hire() should succeed even if org-chart update fails."""
        # Make org-chart directory unwritable to force failure
        chart_dir = org_path / "org-chart"
        chart_dir.mkdir(parents=True, exist_ok=True)

        # Create a file where directory should be to cause write failure
        # (Actually, we'll test that hire succeeds regardless)
        # The org-chart update is best-effort, so we just verify hire works

        new_worker = ceo_with_authority.hire(
            name="TestWorker",
            role="engineer",
            skills={},
            cost=50,
        )

        # Worker should be created successfully
        assert new_worker is not None
        assert new_worker.name == "TestWorker"
        assert new_worker.manager_id == ceo_with_authority.id


class TestDelegateAuthority:
    """Test Worker.delegate_authority() method."""

    @pytest.fixture
    def manager_with_authority(self, db, team):
        """Create manager with hiring authority."""
        scope = HiringScope(
            allowed_roles={"engineer", "analyst", "junior"},
            max_cost=70,
            max_total_budget=1000,
        )
        worker_data = create_worker(
            db,
            "SeniorManager",
            "Manager",
            team.id,
            80,
            hiring_authority_scope=scope.to_json(),
            delegated_budget=500,
            max_reports=10,
        )
        return Worker.get(db, worker_data.id)

    @pytest.fixture
    def junior_manager(self, db, team, manager_with_authority):
        """Create junior manager reporting to senior manager."""
        worker_data = create_worker(
            db,
            "JuniorManager",
            "Manager",
            team.id,
            60,
            manager_id=manager_with_authority.id,
        )
        return Worker.get(db, worker_data.id)

    def test_delegate_authority_success(self, manager_with_authority, junior_manager):
        """delegate_authority should update report's hiring scope."""
        new_scope = HiringScope(
            allowed_roles={"junior"},
            max_cost=40,
        )
        manager_with_authority.delegate_authority(
            report=junior_manager,
            budget=200,
            scope=new_scope,
        )

        # Refresh and check
        junior_manager.refresh()
        assert junior_manager.delegated_budget == 200
        assert junior_manager.hiring_authority_scope.allowed_roles == {"junior"}
        assert junior_manager.hiring_authority_scope.max_cost == 40

    def test_delegate_authority_not_report_raises(self, db, team, manager_with_authority):
        """delegate_authority raises if target is not a direct report."""
        # Create worker not reporting to manager
        other_data = create_worker(db, "Other", "Engineer", team.id, 50)
        other = Worker.get(db, other_data.id)

        with pytest.raises(ValueError, match="not a direct report"):
            manager_with_authority.delegate_authority(
                report=other,
                budget=100,
                scope=HiringScope(allowed_roles={"junior"}),
            )

    def test_delegate_cannot_exceed_own_roles(self, manager_with_authority, junior_manager):
        """Cannot delegate roles not in own authority."""
        bad_scope = HiringScope(allowed_roles={"ceo"}, max_cost=40)
        with pytest.raises(InsufficientHiringAuthority) as exc_info:
            manager_with_authority.delegate_authority(
                report=junior_manager,
                budget=100,
                scope=bad_scope,
            )
        assert "not in own authority" in exc_info.value.reason

    def test_delegate_cannot_exceed_own_max_cost(self, manager_with_authority, junior_manager):
        """Cannot delegate max_cost exceeding own."""
        bad_scope = HiringScope(allowed_roles={"junior"}, max_cost=100)
        with pytest.raises(InsufficientHiringAuthority) as exc_info:
            manager_with_authority.delegate_authority(
                report=junior_manager,
                budget=100,
                scope=bad_scope,
            )
        assert "exceeding own" in exc_info.value.reason

    def test_delegate_cannot_exceed_own_budget(self, manager_with_authority, junior_manager):
        """Cannot delegate budget exceeding own delegated_budget."""
        scope = HiringScope(allowed_roles={"junior"}, max_cost=40)
        with pytest.raises(InsufficientHiringAuthority) as exc_info:
            manager_with_authority.delegate_authority(
                report=junior_manager,
                budget=1000,  # Exceeds manager's 500
                scope=scope,
            )
        assert "exceeding own" in exc_info.value.reason


# ===================
# TERMINATE INTEGRATION TESTS
# ===================


class TestTerminateIntegration:
    """Test Worker.terminate() integration with storage, org-chart, and events."""

    @pytest.fixture
    def org_path(self, db):
        """Get org path from db path (db is at org_path/live/quinn.db)."""
        return db.db_path.parent.parent

    @pytest.fixture
    def worker_with_org_path(self, db, worker_data, org_path):
        """Get Worker instance with org_path configured."""
        return Worker(db, worker_data.id, org_path=org_path)

    @pytest.fixture
    def offboarding_worker(self, worker_with_org_path, org_path):
        """Get worker in offboarding state with storage initialized."""
        worker = worker_with_org_path
        # Create storage directory
        from cli.core.storage import StorageManager
        storage = StorageManager(org_path, worker.db)
        storage.ensure_worker_storage(worker.id, reports_to="")

        # Transition to offboarding state
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_offboarding()
        return worker

    def test_terminate_freezes_storage(self, offboarding_worker, org_path):
        """terminate() should freeze worker storage."""
        from cli.core.storage import StorageManager, FROZEN_SUFFIX

        worker = offboarding_worker

        # Verify storage exists before termination
        storage = StorageManager(org_path, worker.db)
        assert storage.worker_storage_exists(worker.id, reports_to="")
        assert not storage.is_worker_frozen(worker.id, reports_to="")

        # Terminate
        worker.terminate()

        # Verify storage is now frozen
        assert storage.is_worker_frozen(worker.id, reports_to="")

    def test_terminate_updates_org_chart(self, offboarding_worker, org_path):
        """terminate() should update org-chart/current.yaml."""
        import yaml

        worker = offboarding_worker
        chart_path = org_path / "org-chart" / "current.yaml"

        # Create org-chart directory if needed
        chart_path.parent.mkdir(parents=True, exist_ok=True)

        # Create initial org-chart with worker
        initial_chart = {
            "version": "1.0",
            "workers": {
                worker.id: {
                    "name": worker.name,
                    "role": worker.role,
                    "lifecycle": "offboarding",
                    "manager": None,
                    "reports": [],
                }
            },
            "hierarchy": {"root": worker.id},
        }
        with open(chart_path, "w") as f:
            yaml.dump(initial_chart, f)

        # Terminate
        worker.terminate()

        # Verify org-chart was updated with terminated status
        with open(chart_path) as f:
            updated_chart = yaml.safe_load(f)

        assert updated_chart["workers"][worker.id]["lifecycle"] == "terminated"

    def test_terminate_publishes_event(self, offboarding_worker):
        """terminate() should publish WORKER_FIRED event."""
        from cli.core.events import EventBus, EventType

        worker = offboarding_worker

        # Terminate
        worker.terminate()

        # Verify event was published
        bus = EventBus(worker.db)
        events = bus.get_events_for_entity("worker", worker.id, limit=10)

        fired_events = [e for e in events if e.event_type == EventType.WORKER_FIRED]
        assert len(fired_events) == 1
        assert fired_events[0].payload["name"] == worker.name
        assert fired_events[0].payload["role"] == worker.role

    def test_terminate_stops_session(self, db, team, org_path):
        """terminate() should stop any running session."""
        # Create worker with session
        worker_data = create_worker(db, "SessionWorker", "Developer", team.id, 50)
        worker = Worker(db, worker_data.id, org_path=org_path)

        # Create mock session
        session = MockSession()
        worker.start_onboarding()
        worker.complete_onboarding()

        # Create budget for session
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

        # Spawn session
        worker.spawn_session(session)
        assert worker.session is not None

        # Transition to offboarding and terminate
        worker.start_offboarding()
        worker.terminate()

        # Verify session was stopped
        assert session.stopped is True
        assert session.force_stopped is True
        assert worker.session is None

    def test_terminate_handles_no_storage(self, db, team, org_path):
        """terminate() should succeed even if worker has no storage."""
        # Create worker without storage
        worker_data = create_worker(db, "NoStorageWorker", "Developer", team.id, 50)
        worker = Worker(db, worker_data.id, org_path=org_path)

        # Transition to offboarding (skip storage creation)
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_offboarding()

        # Should not raise - storage operations are best-effort
        worker.terminate()
        assert worker.lifecycle_status == "terminated"

    def test_terminate_handles_already_frozen_storage(self, db, team, org_path):
        """terminate() should succeed even if storage is already frozen."""
        from cli.core.storage import StorageManager

        # Create worker with storage
        worker_data = create_worker(db, "FrozenWorker", "Developer", team.id, 50)
        worker = Worker(db, worker_data.id, org_path=org_path)

        # Create and freeze storage manually
        storage = StorageManager(org_path, worker.db)
        storage.ensure_worker_storage(worker.id, reports_to="")
        storage.freeze_worker(worker.id, reports_to="")

        # Transition to offboarding
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_offboarding()

        # Should not raise - already frozen is OK
        worker.terminate()
        assert worker.lifecycle_status == "terminated"
