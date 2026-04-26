"""
Test for session spawn state bug (quinnai-nbkes).

Tests the scenario where session spawn fails after worker_state.runtime_status
is set to 'running' but before the session record is created in the sessions table.

Expected behavior: is_session_active should return False and allow re-spawn.
Actual behavior (buggy): is_session_active returns True, blocks re-spawn.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from cli.core.db import init_database, Database
from cli.core.session import SessionConfig, SessionInterface, SessionState
from cli.core.worker import Worker
from cli.core.queries import (
    create_worker,
    create_team,
    get_worker_state,
    update_worker_runtime_status,
    update_worker_status,
)
from cli.core.sessions.persistence import (
    get_session_for_worker,
    create_session_record,
    update_session_state,
    delete_session_for_worker,
)
from shared import SessionSpawnError, ActiveSessionExistsError


@pytest.fixture
def test_db(tmp_path: Path) -> Database:
    """Create test database."""
    db_path = tmp_path / "test.db"
    db = init_database(db_path)

    # Create team first
    create_team(db, name="Test Team", team_id="team-1", parent_team_id=None)

    return db


@pytest.fixture
def test_worker(test_db: Database) -> Worker:
    """Create test worker."""
    worker_id = "worker-1"
    create_worker(
        test_db,
        name="Test Worker",
        role="Engineer",
        team_id="team-1",
        cost=50,
        worker_id=worker_id,
    )
    # Set to active status (workers created in 'pending' by default)
    update_worker_status(test_db, worker_id, "active")
    return Worker(test_db, worker_id)


def test_session_spawn_failure_auto_repairs_state(test_worker: Worker, test_db: Database):
    """Test that session spawn failure auto-repairs inconsistent state.

    This test verifies the fix for quinnai-nbkes where:
    1. Session spawn starts and sets worker_state.runtime_status = 'running'
    2. Session spawn fails before creating session record in DB
    3. worker_state shows 'running' but no session exists
    4. is_session_active detects the inconsistency and auto-repairs by resetting to 'stopped'
    5. Subsequent spawn attempts can proceed (not blocked)
    """
    # Create a mock session that will fail during start()
    mock_session = Mock(spec=SessionInterface)
    mock_session.id = "session-1"
    mock_session.provider_name = "test_provider"
    mock_session.state = SessionState.STARTING
    mock_session.pid = None
    mock_session.platform_session_name = "test-session"
    mock_session.config = SessionConfig(
        worker_id=test_worker.id,
        provider="test_provider",
        command="test",
        args=[],
    )

    # Mock bind_to_worker to succeed
    mock_session.bind_to_worker = Mock()

    # Mock on_state_change to capture the callback
    state_change_callback = None
    def capture_callback(callback):
        nonlocal state_change_callback
        state_change_callback = callback
    mock_session.on_state_change = capture_callback

    # Mock session.start() to:
    # 1. Call the state change callback to simulate session transitioning to RUNNING
    # 2. Then raise SessionSpawnError to simulate spawn failure
    def mock_start():
        # Simulate session state transition that updates worker_state
        if state_change_callback:
            state_change_callback(SessionState.STARTING, SessionState.RUNNING)
        # Then fail
        raise SessionSpawnError(test_worker.id, "Simulated spawn failure")

    mock_session.start = mock_start

    # Mock budget enforcement to succeed (we're testing session spawn, not budget)
    with patch.object(test_worker._budget_mgr, 'enforce_spawn_budget') as mock_budget:
        mock_budget.return_value = Mock(allocation_id="alloc-1")

        # Attempt to spawn session - should fail
        with pytest.raises(SessionSpawnError):
            test_worker.spawn_session(mock_session)

    # VERIFY INCONSISTENT STATE AFTER SPAWN FAILURE:

    # 1. worker_state.runtime_status shows 'running' (because callback was called)
    worker_state = get_worker_state(test_db, test_worker.id)
    assert worker_state is not None
    assert worker_state.runtime_status == "running", "Worker state should show 'running' after callback"

    # 2. But NO session exists in sessions table (because create_session_record was never reached)
    session_record = get_session_for_worker(test_db, test_worker.id)
    assert session_record is None, "No session should exist in DB after spawn failure"

    # VERIFY AUTO-REPAIR FIX:

    # 3. is_session_active detects the inconsistency and auto-repairs
    # It should return False (not True) and reset state to 'stopped'
    assert test_worker.is_session_active is False, (
        "FIXED: is_session_active should auto-repair and return False when no session exists"
    )

    # 4. Verify state was auto-repaired to 'stopped'
    test_worker.refresh()
    worker_state = get_worker_state(test_db, test_worker.id)
    assert worker_state.runtime_status == "stopped", "State should be auto-repaired to 'stopped'"

    # 5. Subsequent spawn attempts are now allowed (not blocked)
    # Simulates what happens in qn org start after the fix
    if not test_worker.is_session_active:
        # SUCCESS: Spawn is no longer blocked
        pass  # Would proceed to spawn new session
    else:
        pytest.fail("Auto-repair failed: is_session_active still returns True")


def test_is_session_active_should_verify_session_exists_EXPECTED_BEHAVIOR(
    test_worker: Worker,
    test_db: Database,
):
    """Test expected behavior: is_session_active should verify session actually exists.

    This test demonstrates what SHOULD happen:
    - If worker_state says 'running' but no session in DB, is_session_active should return False
    - This allows recovery by spawning a new session

    This test will FAIL until the bug is fixed.
    """
    # Manually create the inconsistent state (simulating post-spawn-failure state)
    # 1. Set worker_state to 'running'
    update_worker_runtime_status(test_db, test_worker.id, "running")

    # 2. Verify no session exists in DB
    session_record = get_session_for_worker(test_db, test_worker.id)
    assert session_record is None

    # EXPECTED BEHAVIOR (currently fails):
    # is_session_active should return False because no session exists,
    # even though worker_state.runtime_status is 'running'

    # This assertion will FAIL with the current buggy implementation
    # After fix, this should PASS
    assert test_worker.is_session_active is False, (
        "EXPECTED: is_session_active should return False when no session exists, "
        "even if worker_state shows 'running'"
    )


def test_auto_repair_eliminates_manual_workaround(test_worker: Worker, test_db: Database):
    """Test that auto-repair eliminates the need for manual workaround.

    Before the fix, users had to manually reset worker_state.runtime_status to 'stopped'.
    After the fix, is_session_active auto-repairs the state, eliminating manual intervention.
    """
    # Create the inconsistent state
    update_worker_runtime_status(test_db, test_worker.id, "running")
    assert get_session_for_worker(test_db, test_worker.id) is None

    # With the fix, is_session_active auto-repairs immediately
    # No manual intervention needed
    assert test_worker.is_session_active is False

    # Verify state was auto-repaired
    test_worker.refresh()
    worker_state = get_worker_state(test_db, test_worker.id)
    assert worker_state.runtime_status == "stopped"

    # Spawn can proceed without manual workaround


def _make_mock_session(worker_id: str, session_id: str, state: SessionState = SessionState.RUNNING) -> Mock:
    """Build a mock SessionInterface that succeeds on start()."""
    mock_session = Mock(spec=SessionInterface)
    mock_session.id = session_id
    mock_session.provider_name = "test_provider"
    mock_session.state = state
    mock_session.pid = None
    mock_session.platform_session_name = f"qn-{session_id}"
    mock_session.config = SessionConfig(
        worker_id=worker_id,
        provider="test_provider",
        command="test",
        args=[],
    )
    mock_session.bind_to_worker = Mock()

    state_change_callback = None

    def capture_callback(callback):
        nonlocal state_change_callback
        state_change_callback = callback

    mock_session.on_state_change = capture_callback

    def mock_start():
        if state_change_callback:
            state_change_callback(SessionState.STARTING, state)

    mock_session.start = mock_start
    return mock_session


def test_double_spawn_raises_active_session_error(test_worker: Worker, test_db: Database):
    """Test that spawning for a worker with an existing active session raises an error, not silently succeeds.

    Covers the double-spawn guard: the board UI could trigger start twice in quick
    succession. The second spawn must fail loudly via ActiveSessionExistsError so
    the caller knows the operation was rejected.
    """
    # Arrange: insert a session record in the DB simulating an already-running session
    create_session_record(
        db=test_db,
        session_id="existing-session-1",
        worker_id=test_worker.id,
        provider="test_provider",
        command="test",
        state="running",
    )

    # Confirm the guard sees an active session
    assert test_worker.is_session_active is True

    mock_session = _make_mock_session(test_worker.id, "new-session-1")

    with patch.object(test_worker._budget_mgr, "enforce_spawn_budget") as mock_budget:
        mock_budget.return_value = Mock(allocation_id="alloc-1")

        # Act + Assert: second spawn must raise ActiveSessionExistsError, never silently no-op
        with pytest.raises(ActiveSessionExistsError) as exc_info:
            test_worker.spawn_session(mock_session)

    err = exc_info.value
    assert err.worker_id == test_worker.id
    assert err.existing_session_id == "existing-session-1"

    # The new session must NOT have been written to the DB
    session_in_db = get_session_for_worker(test_db, test_worker.id)
    assert session_in_db is not None
    assert session_in_db["id"] == "existing-session-1", (
        "Only the original session should exist; the duplicate must not have been persisted"
    )


def test_crash_recovery_restart_spawns_fresh_session(test_worker: Worker, test_db: Database):
    """Test that after a worker session is marked 'crashed', cleanup allows a fresh spawn.

    Simulates the board UI restart flow:
    1. A session exists and crashes.
    2. The DB session record is updated to 'crashed' and then removed (cleanup).
    3. A new session can be spawned without hitting the double-spawn guard.
    """
    # Arrange: session exists and is now in crashed state
    create_session_record(
        db=test_db,
        session_id="crashed-session-1",
        worker_id=test_worker.id,
        provider="test_provider",
        command="test",
        state="crashed",
    )
    # Mark worker runtime as crashed too
    update_worker_runtime_status(test_db, test_worker.id, "crashed")
    test_worker._state_data = None  # invalidate cache

    # Verify crashed state is visible
    test_worker.refresh()
    assert test_worker.runtime_status == "crashed"

    # The crashed session record should NOT block a new spawn
    # (only 'starting', 'running', 'idle' block; 'crashed' does not)
    assert test_worker.is_session_active is False, (
        "A crashed session must not block a new spawn"
    )

    # Cleanup: delete the crashed DB record (mirrors what restart does)
    delete_session_for_worker(test_db, test_worker.id)
    # Reset runtime status to stopped so the transition to 'starting' is valid
    update_worker_runtime_status(test_db, test_worker.id, "stopped")
    test_worker._state_data = None

    mock_session = _make_mock_session(test_worker.id, "fresh-session-1", state=SessionState.RUNNING)

    with patch.object(test_worker._budget_mgr, "enforce_spawn_budget") as mock_budget, \
         patch.object(test_worker._budget_mgr, "record_spawn_spend"):
        mock_budget.return_value = Mock(allocation_id="alloc-2")

        # Act: spawn should succeed after crash cleanup
        test_worker.spawn_session(mock_session)

    # Assert: fresh session persisted correctly
    fresh_record = get_session_for_worker(test_db, test_worker.id)
    assert fresh_record is not None
    assert fresh_record["id"] == "fresh-session-1"
    assert fresh_record["state"] == "running"

    # Worker is_session_active now reflects the live session
    assert test_worker.is_session_active is True


def test_runtime_status_set_correctly_after_successful_spawn(test_worker: Worker, test_db: Database):
    """Test that worker runtime_status reflects the spawned session state (not left as 'stopped').

    After a successful spawn, the state-change callback fired by session.start() must
    have updated worker_state.runtime_status to 'running'. If it remains 'stopped',
    the board UI would show the worker as inactive even though a session is live.
    """
    mock_session = _make_mock_session(test_worker.id, "status-check-session-1", state=SessionState.RUNNING)

    with patch.object(test_worker._budget_mgr, "enforce_spawn_budget") as mock_budget, \
         patch.object(test_worker._budget_mgr, "record_spawn_spend"):
        mock_budget.return_value = Mock(allocation_id="alloc-3")

        test_worker.spawn_session(mock_session)

    # Reload state from DB to avoid any in-memory caching masking the real value
    test_worker.refresh()
    worker_state = get_worker_state(test_db, test_worker.id)

    assert worker_state is not None
    assert worker_state.runtime_status == "running", (
        f"runtime_status must be 'running' after a successful spawn, got '{worker_state.runtime_status}'"
    )

    # is_session_active must agree
    assert test_worker.is_session_active is True
