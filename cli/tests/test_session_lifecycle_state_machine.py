"""
Session Lifecycle State Machine Validation Tests.

Tests validate actual implementation against STATEMACHINES.md specification.
EXPECTED FAILURES: Missing 'working' and 'blocked' states, no automatic callbacks.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

from cli.core.db import init_database
from cli.core.queries import (
    create_team,
    create_worker,
    create_budget_pool,
    create_budget_allocation,
    get_worker_state,
)
from cli.core.worker import Worker
from shared import InvalidStateTransition, RUNTIME_TRANSITIONS
from shared.state_machines import RUNTIME_STATES


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def team(db):
    """Create a test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def worker_with_budget(db, team):
    """Create a worker with budget allocation."""
    from datetime import datetime, timedelta

    worker = create_worker(db, "Alice", "Developer", team.id, 50)

    # Create budget pool and allocation
    now = datetime.now()
    period_end = now + timedelta(days=30)

    pool = create_budget_pool(
        db,
        name="Test Pool",
        total_credits=1000.0,
        period_start=now,
        period_end=period_end
    )

    create_budget_allocation(
        db,
        pool_id=pool.id,
        worker_id=worker.id,
        allocated_credits=500.0,
        period_start=now,
        period_end=period_end,
        can_delegate=False
    )

    return worker


@pytest.fixture
def active_worker(db, worker_with_budget):
    """Create an active worker."""
    worker = Worker(db, worker_with_budget.id)
    worker.start_onboarding()
    worker.complete_onboarding()
    return worker


def create_mock_session(worker_id: str) -> MagicMock:
    """Create a properly configured mock session for testing.

    Args:
        worker_id: ID of the worker this session belongs to

    Returns:
        MagicMock configured with all required session attributes
    """
    from cli.core.session import SessionConfig, SessionState

    mock_session = MagicMock()
    mock_session.config = SessionConfig(
        worker_id=worker_id,
        provider="claude-code",
        command="/usr/bin/claude"
    )
    mock_session.provider_name = "claude-code"
    mock_session.model = "claude-sonnet-4-5"
    mock_session.id = "test-session-123"
    mock_session.platform_session_name = "test-tmux-session"
    mock_session.state = SessionState.IDLE
    mock_session.pid = None
    return mock_session


class TestSessionStates:
    """Validate session states match STATEMACHINES.md."""

    def test_states_match_specification(self):
        """States in code must match STATEMACHINES.md.

        Documented: starting, running, idle, working, blocked, stopped, crashed
        (plus implicit not_spawned = NULL)
        """
        expected = {"starting", "running", "idle", "working", "blocked", "stopped", "crashed"}
        assert RUNTIME_STATES == expected, \
            f"RUNTIME_STATES {RUNTIME_STATES} doesn't match spec {expected}"


class TestSessionT1NotSpawnedToStarting:
    """Test T1: not_spawned → starting."""

    def test_t1_transitions_to_starting(self, active_worker):
        """Worker.spawn_session() should transition to 'starting'."""
        mock_session = create_mock_session(active_worker.id)
        active_worker.spawn_session(mock_session)

        worker_state = get_worker_state(active_worker.db, active_worker.id)
        assert worker_state.runtime_status == "starting"

    def test_t1_enforces_budget(self, db, team):
        """T1 must check budget before spawning."""
        from cli.core.budget import NoBudgetAllocationError

        # Worker with no budget allocation
        worker = create_worker(db, "Broke Worker", "Dev", team.id, 50)
        worker_obj = Worker(db, worker.id)
        worker_obj.start_onboarding()
        worker_obj.complete_onboarding()

        mock_session = create_mock_session(worker_obj.id)

        with pytest.raises(NoBudgetAllocationError):
            worker_obj.spawn_session(mock_session)

    def test_t1_checks_existing_session(self, active_worker):
        """T1 must raise if active session already exists."""
        from cli.core.worker import ActiveSessionExistsError
        from datetime import datetime

        # Create existing active session record in sessions table
        active_worker.db.execute(
            """INSERT INTO sessions (id, worker_id, provider, command, state, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("test-session-123", active_worker.id, "claude-code", "/usr/bin/claude", "running", datetime.now())
        )
        active_worker.db.connection.commit()

        mock_session = create_mock_session(active_worker.id)

        with pytest.raises(ActiveSessionExistsError):
            active_worker.spawn_session(mock_session)

    @pytest.mark.xfail(reason="T1 has no rollback - budget deducted before spawn")
    def test_t1_rollback_on_spawn_failure(self, active_worker, monkeypatch):
        """T1 should rollback budget if spawn fails.

        EXPECTED TO FAIL: Documented violation in validation report.
        Budget is deducted before spawn attempt. If spawn fails, budget is lost.
        """
        from cli.core.queries.budget import get_current_allocation

        allocation = get_current_allocation(active_worker.db, active_worker.id)
        initial_spent = allocation.spent_credits

        # Mock spawn to fail
        def fail_start(self):
            raise Exception("Spawn failed")

        mock_session = MagicMock()
        mock_session.start = fail_start

        with pytest.raises(Exception):
            active_worker.spawn_session(mock_session)

        # Budget should be refunded (rollback)
        allocation = get_current_allocation(active_worker.db, active_worker.id)
        assert allocation.spent_credits == initial_spent, \
            "Budget should be rolled back on spawn failure"


class TestSessionT2StartingToRunning:
    """Test T2: starting → running."""

    def test_t2_transition_to_running(self, active_worker):
        """Worker.session_ready() should transition to 'running'."""
        from cli.core.queries import update_worker_runtime_status

        # Set up starting state
        update_worker_runtime_status(active_worker.db, active_worker.id, "starting")

        active_worker.session_ready()

        worker_state = get_worker_state(active_worker.db, active_worker.id)
        assert worker_state.runtime_status == "running"

    @pytest.mark.xfail(reason="Session adapters don't call session_ready() automatically")
    def test_t2_automatic_callback(self):
        """Session adapters should call session_ready() automatically.

        EXPECTED TO FAIL: Critical violation from validation report.
        session_ready() exists but is never called automatically.
        Session state changes don't propagate to worker_state table.
        """
        # This would require integration test with real session adapter
        # Currently session adapters DON'T call worker methods on state change
        pass


class TestSessionT3RunningIdleTransitions:
    """Test T3: running ⇄ idle."""

    def test_t3_running_to_idle(self, active_worker):
        """Worker.finish_work() should transition to 'idle'."""
        from cli.core.queries import update_worker_runtime_status

        # Set up running state
        update_worker_runtime_status(active_worker.db, active_worker.id, "running")

        active_worker.finish_work()

        worker_state = get_worker_state(active_worker.db, active_worker.id)
        assert worker_state.runtime_status == "idle"

    def test_t3_idle_to_running(self, active_worker):
        """Worker.begin_work() should transition to 'running'."""
        from cli.core.queries import update_worker_runtime_status

        # Set up idle state
        update_worker_runtime_status(active_worker.db, active_worker.id, "idle")

        active_worker.begin_work(task_id="task-123")

        worker_state = get_worker_state(active_worker.db, active_worker.id)
        assert worker_state.runtime_status == "running"

    @pytest.mark.xfail(reason="T3 is manual only - no automatic triggers")
    def test_t3_automatic_triggers(self):
        """T3 transitions should happen automatically on task events.

        EXPECTED TO FAIL: Documented in validation report.
        finish_work() and begin_work() are manual calls only.
        No automatic triggers from task system.
        """
        pass


class TestSessionT4RunningToWorking:
    """Test T4: running → working (MISSING)."""

    @pytest.mark.xfail(reason="State 'working' doesn't exist in RUNTIME_STATES")
    def test_t4_transition_to_working(self, active_worker):
        """Worker should transition to 'working' on task assignment.

        EXPECTED TO FAIL: State 'working' not in RUNTIME_STATES.
        """
        from cli.core.queries import update_worker_runtime_status

        update_worker_runtime_status(active_worker.db, active_worker.id, "running")

        # This method doesn't exist
        active_worker.assign_task(task_id="task-123")

        worker_state = get_worker_state(active_worker.db, active_worker.id)
        assert worker_state.runtime_status == "working"


class TestSessionT5WorkingToBlocked:
    """Test T5: working → blocked (MISSING)."""

    @pytest.mark.xfail(reason="States 'working' and 'blocked' don't exist")
    def test_t5_transition_to_blocked(self):
        """Worker should transition to 'blocked' on escalation.

        EXPECTED TO FAIL: States 'working' and 'blocked' not in RUNTIME_STATES.
        """
        pass


class TestSessionT6BlockedToWorking:
    """Test T6: blocked → working (MISSING)."""

    @pytest.mark.xfail(reason="States 'working' and 'blocked' don't exist")
    def test_t6_transition_to_working(self):
        """Worker should transition back to 'working' when unblocked.

        EXPECTED TO FAIL: States 'working' and 'blocked' not in RUNTIME_STATES.
        """
        pass


class TestSessionT7AnyToStopped:
    """Test T7: any → stopped."""

    def test_t7_transition_to_stopped(self, active_worker):
        """Worker.stop_session() should transition to 'stopped'."""
        from cli.core.queries import update_worker_runtime_status

        # Set up running state
        update_worker_runtime_status(active_worker.db, active_worker.id, "running")

        active_worker.stop_session()

        worker_state = get_worker_state(active_worker.db, active_worker.id)
        assert worker_state.runtime_status == "stopped"


class TestSessionT8AnyToCrashed:
    """Test T8: any → crashed."""

    def test_t8_transition_to_crashed(self, active_worker):
        """Worker.mark_crashed() should transition to 'crashed'."""
        from cli.core.queries import update_worker_runtime_status

        # Set up running state
        update_worker_runtime_status(active_worker.db, active_worker.id, "running")

        active_worker.mark_crashed()

        worker_state = get_worker_state(active_worker.db, active_worker.id)
        assert worker_state.runtime_status == "crashed"

    @pytest.mark.xfail(reason="mark_crashed() may not be called on actual crashes")
    def test_t8_automatic_on_crash(self):
        """T8 should trigger automatically on session crash.

        EXPECTED TO FAIL: Documented in validation report.
        Crash detection may not trigger mark_crashed().
        """
        pass


class TestSessionTransitionTable:
    """Validate transition table matches STATEMACHINES.md."""

    def test_transition_table_matches_spec(self):
        """RUNTIME_TRANSITIONS must match the documented spec.

        Transitions (current canonical, see cli/docs/worker-state-design.md
        and shared/state_machines.py):
        - starting → [running, crashed, stopped]   # cancel before ready
        - running → [idle, working, stopped, crashed]
        - idle → [running, stopped]
        - working → [blocked, idle, stopped, crashed]
        - blocked → [working, stopped, crashed]
        - stopped → [starting]                     # allow restart
        - crashed → [starting]                     # allow restart
        """
        expected = {
            "starting": ["running", "crashed", "stopped"],
            "running": ["idle", "working", "stopped", "crashed"],
            "idle": ["running", "stopped"],
            "working": ["blocked", "idle", "stopped", "crashed"],
            "blocked": ["working", "stopped", "crashed"],
            "stopped": ["starting"],
            "crashed": ["starting"],
        }

        assert RUNTIME_TRANSITIONS == expected, \
            f"RUNTIME_TRANSITIONS {RUNTIME_TRANSITIONS} doesn't match spec"


class TestSessionStatusSyncPropagation:
    """Validate automatic status sync from session to database."""

    @pytest.mark.xfail(reason="Session adapters don't call Worker methods - CRITICAL")
    def test_session_state_change_updates_database(self):
        """Session state changes should automatically update worker_state table.

        EXPECTED TO FAIL: Critical violation from validation report.

        Problem: Session adapters change state internally but DON'T call Worker methods.
        Current flow:
            Session State Change (in adapter) → ❌ NO CALLBACK →
            Worker methods NOT called → worker_state NOT updated

        Required flow:
            Session State Change → _on_state_change(old, new) →
            update_worker_runtime_status(db, worker_id, status) →
            worker_state UPDATED

        Fix needed in:
        - cli/core/sessions/claude_code.py
        - cli/core/sessions/gemini.py
        """
        # This requires integration test with real session adapter
        # Cannot test with current implementation
        pass

    @pytest.mark.xfail(reason="Latency requirement not met - no automatic updates")
    def test_status_sync_latency_under_500ms(self):
        """Session state change should propagate to database < 500ms.

        EXPECTED TO FAIL: Documented latency requirement in STATEMACHINES.md.
        Current: ∞ (never updates automatically)
        Target: < 500ms
        """
        pass


class TestSessionDependencies:
    """Validate session lifecycle dependencies."""

    def test_session_spawn_requires_worker_active(self, db, worker_with_budget):
        """T1 requires worker lifecycle = 'active'."""
        from shared.state_machines import SESSION_ALLOWED_LIFECYCLES

        worker = Worker(db, worker_with_budget.id)

        # Pending worker cannot spawn
        assert worker.lifecycle_status == "pending"
        assert worker.lifecycle_status not in SESSION_ALLOWED_LIFECYCLES

        # Must activate first
        worker.start_onboarding()
        worker.complete_onboarding()
        assert worker.lifecycle_status in SESSION_ALLOWED_LIFECYCLES

    def test_session_spawn_gates_on_budget(self, db, team):
        """T1 enforces budget check before spawning."""
        from cli.core.budget import NoBudgetAllocationError

        worker = create_worker(db, "No Budget", "Dev", team.id, 50)
        worker_obj = Worker(db, worker.id)
        worker_obj.start_onboarding()
        worker_obj.complete_onboarding()

        mock_session = create_mock_session(worker_obj.id)

        with pytest.raises(NoBudgetAllocationError):
            worker_obj.spawn_session(mock_session)
