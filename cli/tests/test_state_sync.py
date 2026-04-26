"""
Tests for SessionStateSync.

Tests session-to-worker state synchronization, crash detection, and heartbeat monitoring.
"""

import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from cli.core.db import init_database
from cli.core.queries import create_team, create_worker, update_worker_runtime_status
from cli.core.session import SessionState
from cli.core.sessions.binding_manager import SessionBindingManager
from cli.core.sessions.state_sync import (
    SessionStateSync,
    StateSyncConfig,
    DEFAULT_HEARTBEAT_THRESHOLD,
    get_state_sync,
    reset_state_sync,
)


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
def worker(db, team):
    """Create a test worker."""
    return create_worker(db, "Alice", "Developer", team.id, 50)


@pytest.fixture
def binding_manager(db):
    """Create a SessionBindingManager."""
    return SessionBindingManager(db)


@pytest.fixture
def state_sync(db, binding_manager):
    """Create a SessionStateSync."""
    return SessionStateSync(db, binding_manager)


@pytest.fixture
def mock_session():
    """Create a mock session."""
    session = MagicMock()
    session.id = "session-123"
    session.state = SessionState.RUNNING
    session.on_state_change = MagicMock()
    return session


class TestStateSyncConfig:
    """Tests for StateSyncConfig."""

    def test_default_values(self):
        """Should have default configuration values."""
        config = StateSyncConfig()

        assert config.heartbeat_threshold_seconds == DEFAULT_HEARTBEAT_THRESHOLD
        assert config.check_interval_seconds == 10
        assert config.auto_unbind_on_crash is True
        assert config.auto_unbind_on_stop is False


class TestSessionStateSyncInit:
    """Tests for SessionStateSync initialization."""

    def test_init_with_defaults(self, db, binding_manager):
        """Should initialize with default config."""
        sync = SessionStateSync(db, binding_manager)

        assert sync._db is db
        assert sync._binding_manager is binding_manager
        assert isinstance(sync._config, StateSyncConfig)
        assert len(sync._last_states) == 0

    def test_init_with_custom_config(self, db, binding_manager):
        """Should initialize with custom config."""
        config = StateSyncConfig()
        config.heartbeat_threshold_seconds = 120
        config.auto_unbind_on_crash = False

        sync = SessionStateSync(db, binding_manager, config)

        assert sync._config.heartbeat_threshold_seconds == 120
        assert sync._config.auto_unbind_on_crash is False


class TestSessionStateSyncRegister:
    """Tests for session registration."""

    def test_register_session(self, state_sync, worker, mock_session):
        """Should register session for monitoring."""
        state_sync.register_session(mock_session, worker.id)

        # Should set up callback
        mock_session.on_state_change.assert_called_once()

        # Should track initial state
        assert "session-123" in state_sync._last_states
        assert state_sync._last_states["session-123"] == SessionState.RUNNING

    def test_register_multiple_sessions(self, state_sync, db, team):
        """Should register multiple sessions."""
        worker1 = create_worker(db, "Alice", "Dev", team.id, 50)
        worker2 = create_worker(db, "Bob", "Dev", team.id, 50)

        session1 = MagicMock()
        session1.id = "session-1"
        session1.state = SessionState.RUNNING
        session1.on_state_change = MagicMock()

        session2 = MagicMock()
        session2.id = "session-2"
        session2.state = SessionState.IDLE
        session2.on_state_change = MagicMock()

        state_sync.register_session(session1, worker1.id)
        state_sync.register_session(session2, worker2.id)

        assert len(state_sync._last_states) == 2


class TestSessionStateSyncStateChange:
    """Tests for state change handling."""

    def test_state_change_creates_worker_state_if_missing(self, state_sync, db, worker, mock_session):
        """Should create worker_state row on first state change if it doesn't exist.

        This test reproduces the bug where update_worker_runtime_status() tries to
        UPDATE a non-existent row, causing get_worker_state() to return None.
        """
        from cli.core.queries import get_worker_state

        # Verify no worker_state exists yet
        assert get_worker_state(db, worker.id) is None

        state_sync.register_session(mock_session, worker.id)

        # Get the callback
        callback = mock_session.on_state_change.call_args[0][0]

        # Simulate state change - this should CREATE the worker_state row
        callback(SessionState.STARTING, SessionState.RUNNING)

        # Now worker_state should exist and have the correct status
        worker_state = get_worker_state(db, worker.id)
        assert worker_state is not None, "worker_state should be created on first update"
        assert worker_state.runtime_status == "running"

    def test_state_change_updates_worker(self, state_sync, db, worker, mock_session):
        """Should update worker runtime status on state change."""
        from cli.core.queries import get_worker_state

        state_sync.register_session(mock_session, worker.id)

        # Get the callback
        callback = mock_session.on_state_change.call_args[0][0]

        # Simulate state change
        callback(SessionState.STARTING, SessionState.RUNNING)

        # Check worker state was updated
        worker_state = get_worker_state(db, worker.id)
        assert worker_state.runtime_status == "running"

    def test_state_change_updates_tracking(self, state_sync, worker, mock_session):
        """Should update last known state tracking."""
        state_sync.register_session(mock_session, worker.id)
        callback = mock_session.on_state_change.call_args[0][0]

        callback(SessionState.STARTING, SessionState.RUNNING)

        assert state_sync._last_states["session-123"] == SessionState.RUNNING

    def test_state_change_to_crashed_triggers_callback(self, state_sync, worker, mock_session):
        """Should trigger crash callbacks on CRASHED state."""
        crash_callback = Mock()
        state_sync.on_crash(crash_callback)

        state_sync.register_session(mock_session, worker.id)
        callback = mock_session.on_state_change.call_args[0][0]

        callback(SessionState.RUNNING, SessionState.CRASHED)

        crash_callback.assert_called_once_with(worker.id, "session-123")

    def test_state_change_crashed_auto_unbinds(self, state_sync, binding_manager, worker, mock_session):
        """Should auto-unbind on crash when configured."""
        binding_manager.bind(worker.id, "session-123", session=mock_session)
        state_sync.register_session(mock_session, worker.id)

        callback = mock_session.on_state_change.call_args[0][0]
        callback(SessionState.RUNNING, SessionState.CRASHED)

        assert not binding_manager.is_worker_bound(worker.id)

    def test_state_change_crashed_no_auto_unbind(self, db, binding_manager, worker, mock_session):
        """Should not auto-unbind when disabled."""
        config = StateSyncConfig()
        config.auto_unbind_on_crash = False
        sync = SessionStateSync(db, binding_manager, config)

        binding_manager.bind(worker.id, "session-123", session=mock_session)
        sync.register_session(mock_session, worker.id)

        callback = mock_session.on_state_change.call_args[0][0]
        callback(SessionState.RUNNING, SessionState.CRASHED)

        assert binding_manager.is_worker_bound(worker.id)

    def test_state_change_stopped_auto_unbind_when_configured(self, db, binding_manager, worker, mock_session):
        """Should auto-unbind on stop when configured."""
        config = StateSyncConfig()
        config.auto_unbind_on_stop = True
        sync = SessionStateSync(db, binding_manager, config)

        binding_manager.bind(worker.id, "session-123", session=mock_session)
        sync.register_session(mock_session, worker.id)

        callback = mock_session.on_state_change.call_args[0][0]
        callback(SessionState.RUNNING, SessionState.STOPPED)

        assert not binding_manager.is_worker_bound(worker.id)

    def test_crash_callback_error_handling(self, state_sync, worker, mock_session):
        """Should handle errors in crash callbacks gracefully."""
        bad_callback = Mock(side_effect=Exception("callback error"))
        good_callback = Mock()

        state_sync.on_crash(bad_callback)
        state_sync.on_crash(good_callback)

        state_sync.register_session(mock_session, worker.id)
        callback = mock_session.on_state_change.call_args[0][0]

        # Should not raise
        callback(SessionState.RUNNING, SessionState.CRASHED)

        # Good callback should still be called
        good_callback.assert_called_once()


class TestSessionStateSyncCheckAll:
    """Tests for checking all sessions for crashes."""

    @patch("os.kill")
    def test_check_all_healthy_sessions(self, mock_kill, state_sync, binding_manager, worker):
        """Should identify healthy sessions."""
        mock_kill.return_value = None  # Process exists

        binding_manager.bind(worker.id, "session-123", pid=12345)

        results = state_sync.check_all()

        assert (worker.id, "session-123") in results["healthy"]
        assert len(results["crashed"]) == 0

    @patch("os.kill")
    def test_check_all_crashed_by_pid(self, mock_kill, state_sync, binding_manager, worker):
        """Should detect crashed sessions via PID."""
        mock_kill.side_effect = OSError("No such process")

        binding_manager.bind(worker.id, "session-123", pid=12345)

        results = state_sync.check_all()

        assert (worker.id, "session-123") in results["crashed"]
        assert len(results["healthy"]) == 0

    def test_check_all_with_session_instance_running(self, state_sync, binding_manager, worker, mock_session):
        """Should check session state directly when instance available."""
        mock_session.state = SessionState.RUNNING

        binding_manager.bind(worker.id, "session-123", session=mock_session)

        results = state_sync.check_all()

        assert (worker.id, "session-123") in results["healthy"]

    def test_check_all_with_session_instance_crashed(self, state_sync, binding_manager, worker, mock_session):
        """Should detect crashed sessions via session state."""
        mock_session.state = SessionState.CRASHED

        binding_manager.bind(worker.id, "session-123", session=mock_session)

        results = state_sync.check_all()

        assert (worker.id, "session-123") in results["crashed"]

    def test_check_all_unknown_state(self, state_sync, binding_manager, worker):
        """Should mark sessions as unknown when no PID or instance."""
        binding_manager.bind(worker.id, "session-123", pid=None)

        results = state_sync.check_all()

        assert (worker.id, "session-123") in results["unknown"]

    @patch("os.kill")
    def test_check_all_marks_crashed_in_db(self, mock_kill, state_sync, db, binding_manager, worker):
        """Should mark worker as crashed in database."""
        from cli.core.queries import get_worker_state

        mock_kill.side_effect = OSError("No such process")

        binding_manager.bind(worker.id, "session-123", pid=12345)

        state_sync.check_all()

        worker_state = get_worker_state(db, worker.id)
        assert worker_state.runtime_status == "crashed"

    @patch("os.kill")
    def test_check_all_triggers_crash_callback(self, mock_kill, state_sync, binding_manager, worker):
        """Should trigger crash callbacks for detected crashes."""
        mock_kill.side_effect = OSError("No such process")
        crash_callback = Mock()
        state_sync.on_crash(crash_callback)

        binding_manager.bind(worker.id, "session-123", pid=12345)

        state_sync.check_all()

        crash_callback.assert_called_once_with(worker.id, "session-123")

    def test_check_all_multiple_sessions(self, state_sync, binding_manager, db, team):
        """Should check multiple sessions."""
        worker1 = create_worker(db, "Alice", "Dev", team.id, 50)
        worker2 = create_worker(db, "Bob", "Dev", team.id, 50)

        session1 = MagicMock()
        session1.id = "session-1"
        session1.state = SessionState.RUNNING

        session2 = MagicMock()
        session2.id = "session-2"
        session2.state = SessionState.CRASHED

        binding_manager.bind(worker1.id, "session-1", session=session1)
        binding_manager.bind(worker2.id, "session-2", session=session2)

        results = state_sync.check_all()

        assert (worker1.id, "session-1") in results["healthy"]
        assert (worker2.id, "session-2") in results["crashed"]


class TestSessionStateSyncHeartbeat:
    """Tests for heartbeat checking."""

    def test_check_heartbeats_active(self, state_sync, db, binding_manager, worker):
        """Should identify active workers."""
        from cli.core.queries import update_worker_runtime_status

        # Update worker activity to now
        update_worker_runtime_status(db, worker.id, "running")

        binding_manager.bind(worker.id, "session-123")

        results = state_sync.check_heartbeats()

        assert worker.id in results["active"]
        assert len(results["stale"]) == 0

    def test_check_heartbeats_stale(self, state_sync, db, binding_manager, worker):
        """Should identify stale workers."""
        # Set last_activity to old timestamp
        db.execute(
            """UPDATE worker_state
               SET last_activity = ?
               WHERE worker_id = ?""",
            (datetime.now() - timedelta(seconds=120), worker.id),
        )
        db.connection.commit()

        binding_manager.bind(worker.id, "session-123")

        results = state_sync.check_heartbeats()

        assert worker.id in results["stale"]
        assert len(results["active"]) == 0

    def test_check_heartbeats_no_last_activity(self, state_sync, db, binding_manager, worker):
        """Should mark as stale when no last_activity."""
        # Clear last_activity
        db.execute(
            """UPDATE worker_state
               SET last_activity = NULL
               WHERE worker_id = ?""",
            (worker.id,),
        )
        db.connection.commit()

        binding_manager.bind(worker.id, "session-123")

        results = state_sync.check_heartbeats()

        assert worker.id in results["stale"]

    def test_check_heartbeats_custom_threshold(self, db, binding_manager, worker):
        """Should use custom heartbeat threshold."""
        config = StateSyncConfig()
        config.heartbeat_threshold_seconds = 30
        sync = SessionStateSync(db, binding_manager, config)

        # Set activity 45 seconds ago
        db.execute(
            """UPDATE worker_state
               SET last_activity = ?
               WHERE worker_id = ?""",
            (datetime.now() - timedelta(seconds=45), worker.id),
        )
        db.connection.commit()

        binding_manager.bind(worker.id, "session-123")

        results = sync.check_heartbeats()

        assert worker.id in results["stale"]

    def test_check_heartbeats_multiple_workers(self, state_sync, db, team, binding_manager):
        """Should check multiple workers."""
        from cli.core.queries import update_worker_runtime_status

        worker1 = create_worker(db, "Alice", "Dev", team.id, 50)
        worker2 = create_worker(db, "Bob", "Dev", team.id, 50)

        # Worker1 active
        update_worker_runtime_status(db, worker1.id, "running")

        # Worker2 stale
        db.execute(
            """UPDATE worker_state
               SET last_activity = ?
               WHERE worker_id = ?""",
            (datetime.now() - timedelta(seconds=120), worker2.id),
        )
        db.connection.commit()

        binding_manager.bind(worker1.id, "session-1")
        binding_manager.bind(worker2.id, "session-2")

        results = state_sync.check_heartbeats()

        assert worker1.id in results["active"]
        assert worker2.id in results["stale"]


class TestSessionStateSyncDefaults:
    """Tests for default state sync functions."""

    def setup_method(self):
        """Reset state sync before each test."""
        reset_state_sync()

    def teardown_method(self):
        """Reset state sync after each test."""
        reset_state_sync()

    def test_get_state_sync_lazy_init(self, db, binding_manager):
        """Should lazily initialize default sync."""
        sync = get_state_sync(db, binding_manager)

        assert sync is not None
        assert isinstance(sync, SessionStateSync)

    def test_get_state_sync_singleton(self, db, binding_manager):
        """Should return same instance on subsequent calls."""
        sync1 = get_state_sync(db, binding_manager)
        sync2 = get_state_sync(db, binding_manager)

        assert sync1 is sync2

    def test_reset_state_sync(self, db, binding_manager):
        """Should reset to None."""
        initial = get_state_sync(db, binding_manager)

        reset_state_sync()

        new = get_state_sync(db, binding_manager)
        assert new is not initial


class TestSessionStateSyncThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_register(self, state_sync, db, team):
        """Should handle concurrent session registration."""
        import threading

        workers = [create_worker(db, f"Worker{i}", "Dev", team.id, 50) for i in range(10)]
        sessions = []
        for i in range(10):
            session = MagicMock()
            session.id = f"session-{i}"
            session.state = SessionState.RUNNING
            session.on_state_change = MagicMock()
            sessions.append(session)

        def register(session, worker):
            state_sync.register_session(session, worker.id)

        threads = [
            threading.Thread(target=register, args=(sessions[i], workers[i]))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(state_sync._last_states) == 10


class TestSessionStateSyncIntegration:
    """Integration tests for SessionStateSync."""

    def test_full_session_lifecycle(self, state_sync, binding_manager, db, worker, mock_session):
        """Test complete session lifecycle monitoring."""
        from cli.core.queries import get_worker_state

        # Bind and register
        binding_manager.bind(worker.id, "session-123", pid=12345, session=mock_session)
        state_sync.register_session(mock_session, worker.id)

        # Get callback
        callback = mock_session.on_state_change.call_args[0][0]

        # Session starts
        callback(SessionState.STOPPED, SessionState.STARTING)
        worker_state = get_worker_state(db, worker.id)
        assert worker_state.runtime_status == "starting"

        # Session runs
        callback(SessionState.STARTING, SessionState.RUNNING)
        worker_state = get_worker_state(db, worker.id)
        assert worker_state.runtime_status == "running"

        # Session goes idle
        callback(SessionState.RUNNING, SessionState.IDLE)
        worker_state = get_worker_state(db, worker.id)
        assert worker_state.runtime_status == "idle"

        # Session crashes
        crash_callback = Mock()
        state_sync.on_crash(crash_callback)

        callback(SessionState.IDLE, SessionState.CRASHED)
        worker_state = get_worker_state(db, worker.id)
        assert worker_state.runtime_status == "crashed"

        # Crash callback was triggered
        crash_callback.assert_called_once_with(worker.id, "session-123")

        # Auto-unbind happened
        assert not binding_manager.is_worker_bound(worker.id)

    @patch("os.kill")
    def test_crash_detection_via_pid(self, mock_kill, state_sync, binding_manager, db, worker):
        """Test crash detection via PID monitoring."""
        from cli.core.queries import get_worker_state

        crash_callback = Mock()
        state_sync.on_crash(crash_callback)

        # Bind with PID
        binding_manager.bind(worker.id, "session-123", pid=12345)

        # Process is alive
        mock_kill.return_value = None
        results = state_sync.check_all()
        assert (worker.id, "session-123") in results["healthy"]

        # Process dies
        mock_kill.side_effect = OSError("No such process")
        results = state_sync.check_all()

        # Detected as crashed
        assert (worker.id, "session-123") in results["crashed"]

        # Worker marked crashed
        worker_state = get_worker_state(db, worker.id)
        assert worker_state.runtime_status == "crashed"

        # Callback triggered
        crash_callback.assert_called_once_with(worker.id, "session-123")
