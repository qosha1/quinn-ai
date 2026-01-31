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

from core.db import init_database, Database
from core.session import SessionConfig, SessionInterface, SessionState
from core.worker import Worker
from core.queries import (
    create_worker,
    create_team,
    get_worker_state,
    update_worker_runtime_status,
    update_worker_status,
)
from core.sessions.persistence import get_session_for_worker
from shared import SessionSpawnError


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
