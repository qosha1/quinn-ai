"""
Tests for SessionStateSync.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from cli.core.sessions import (
    SessionBindingManager,
    SessionStateSync,
    StateSyncConfig,
    get_state_sync,
    reset_state_sync,
    reset_binding_manager,
)


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    return db


@pytest.fixture
def binding_manager():
    """Create a fresh binding manager."""
    return SessionBindingManager()


@pytest.fixture
def state_sync(mock_db, binding_manager):
    """Create a state sync instance."""
    return SessionStateSync(mock_db, binding_manager)


@pytest.fixture(autouse=True)
def reset_defaults():
    """Reset defaults after each test."""
    yield
    reset_state_sync()
    reset_binding_manager()


class TestSessionStateSync:
    """Tests for SessionStateSync."""

    def test_register_session_sets_up_callback(
        self, state_sync, binding_manager
    ):
        """Should register state change callback on session."""
        from cli.core.session import SessionState

        mock_session = MagicMock()
        mock_session.id = "session-a"
        mock_session.state = SessionState.IDLE
        mock_session.on_state_change = MagicMock()

        state_sync.register_session(mock_session, "worker-1")

        mock_session.on_state_change.assert_called_once()

    def test_state_change_updates_worker_state(
        self, state_sync, mock_db, binding_manager
    ):
        """Should update worker runtime state on session state change."""
        from cli.core.session import SessionState

        mock_session = MagicMock()
        mock_session.id = "session-a"
        mock_session.state = SessionState.IDLE
        callback_holder = []
        mock_session.on_state_change = lambda cb: callback_holder.append(cb)

        state_sync.register_session(mock_session, "worker-1")

        # Trigger state change callback
        callback = callback_holder[0]
        with patch(
            "cli.core.queries.update_worker_runtime_status"
        ) as mock_update:
            callback(SessionState.IDLE, SessionState.RUNNING)
            mock_update.assert_called_with(mock_db, "worker-1", "running")

    def test_on_crash_callback_called_on_crash(
        self, state_sync, binding_manager
    ):
        """Should call crash callbacks when session crashes."""
        from cli.core.session import SessionState

        crash_events = []
        state_sync.on_crash(
            lambda worker_id, session_id: crash_events.append(
                (worker_id, session_id)
            )
        )

        mock_session = MagicMock()
        mock_session.id = "session-a"
        mock_session.state = SessionState.IDLE
        callback_holder = []
        mock_session.on_state_change = lambda cb: callback_holder.append(cb)

        state_sync.register_session(mock_session, "worker-1")

        # Trigger crash
        callback = callback_holder[0]
        with patch("cli.core.queries.update_worker_runtime_status"):
            callback(SessionState.RUNNING, SessionState.CRASHED)

        assert ("worker-1", "session-a") in crash_events


class TestCheckAll:
    """Tests for check_all method."""

    def test_check_all_with_no_bindings(self, state_sync):
        """Should handle empty binding list."""
        results = state_sync.check_all()

        assert results["healthy"] == []
        assert results["crashed"] == []
        assert results["unknown"] == []

    def test_check_all_with_running_session(
        self, state_sync, binding_manager
    ):
        """Should report running session as healthy."""
        from cli.core.session import SessionState

        mock_session = MagicMock()
        mock_session.id = "session-a"
        mock_session.state = SessionState.RUNNING
        mock_session.on_state_change = MagicMock()

        binding_manager.bind("worker-1", "session-a", session=mock_session)

        results = state_sync.check_all()

        assert ("worker-1", "session-a") in results["healthy"]

    def test_check_all_with_crashed_session(
        self, state_sync, binding_manager
    ):
        """Should report crashed session as crashed."""
        from cli.core.session import SessionState

        mock_session = MagicMock()
        mock_session.id = "session-a"
        mock_session.state = SessionState.CRASHED
        mock_session.on_state_change = MagicMock()

        binding_manager.bind("worker-1", "session-a", session=mock_session)

        results = state_sync.check_all()

        assert ("worker-1", "session-a") in results["crashed"]

    @patch.object(SessionStateSync, "_is_process_alive")
    def test_check_all_with_dead_pid(
        self, mock_alive, state_sync, binding_manager, mock_db
    ):
        """Should detect crashed session via dead PID."""
        mock_alive.return_value = False

        binding_manager.bind("worker-1", "session-a", pid=12345)

        with patch("cli.core.queries.update_worker_runtime_status"):
            results = state_sync.check_all()

        assert ("worker-1", "session-a") in results["crashed"]

    @patch.object(SessionStateSync, "_is_process_alive")
    def test_check_all_with_alive_pid(
        self, mock_alive, state_sync, binding_manager
    ):
        """Should report alive PID as healthy."""
        mock_alive.return_value = True

        binding_manager.bind("worker-1", "session-a", pid=12345)

        results = state_sync.check_all()

        assert ("worker-1", "session-a") in results["healthy"]


class TestCheckHeartbeats:
    """Tests for check_heartbeats method."""

    def test_check_heartbeats_with_recent_activity(
        self, state_sync, binding_manager
    ):
        """Should report recent activity as active."""
        mock_state = MagicMock()
        mock_state.last_activity = datetime.now()

        binding_manager.bind("worker-1", "session-a")

        with patch("cli.core.queries.get_worker_state", return_value=mock_state):
            results = state_sync.check_heartbeats()

        assert "worker-1" in results["active"]

    def test_check_heartbeats_with_stale_activity(
        self, state_sync, binding_manager
    ):
        """Should report stale activity as stale."""
        mock_state = MagicMock()
        mock_state.last_activity = datetime.now() - timedelta(minutes=10)

        binding_manager.bind("worker-1", "session-a")

        with patch("cli.core.queries.get_worker_state", return_value=mock_state):
            results = state_sync.check_heartbeats()

        assert "worker-1" in results["stale"]

    def test_check_heartbeats_with_no_state(self, state_sync, binding_manager):
        """Should report missing state as stale."""
        binding_manager.bind("worker-1", "session-a")

        with patch("cli.core.queries.get_worker_state", return_value=None):
            results = state_sync.check_heartbeats()

        assert "worker-1" in results["stale"]


class TestAutoUnbind:
    """Tests for auto-unbind on crash/stop."""

    def test_auto_unbind_on_crash(self, mock_db, binding_manager):
        """Should auto-unbind when session crashes."""
        from cli.core.session import SessionState

        config = StateSyncConfig()
        config.auto_unbind_on_crash = True
        state_sync = SessionStateSync(mock_db, binding_manager, config)

        mock_session = MagicMock()
        mock_session.id = "session-a"
        mock_session.state = SessionState.IDLE
        callback_holder = []
        mock_session.on_state_change = lambda cb: callback_holder.append(cb)

        # Don't pass session to bind - state_sync handles the callback separately
        binding_manager.bind("worker-1", "session-a")
        state_sync.register_session(mock_session, "worker-1")

        # Trigger crash via state_sync's callback
        callback = callback_holder[0]
        with patch("cli.core.queries.update_worker_runtime_status"):
            callback(SessionState.RUNNING, SessionState.CRASHED)

        assert not binding_manager.is_worker_bound("worker-1")

    def test_no_auto_unbind_when_disabled(self, mock_db, binding_manager):
        """Should not auto-unbind when disabled."""
        from cli.core.session import SessionState

        config = StateSyncConfig()
        config.auto_unbind_on_crash = False
        state_sync = SessionStateSync(mock_db, binding_manager, config)

        mock_session = MagicMock()
        mock_session.id = "session-a"
        mock_session.state = SessionState.IDLE
        callback_holder = []
        mock_session.on_state_change = lambda cb: callback_holder.append(cb)

        # Don't pass session to bind - state_sync handles the callback separately
        binding_manager.bind("worker-1", "session-a")
        state_sync.register_session(mock_session, "worker-1")

        # Trigger crash via state_sync's callback
        callback = callback_holder[0]
        with patch("cli.core.queries.update_worker_runtime_status"):
            callback(SessionState.RUNNING, SessionState.CRASHED)

        assert binding_manager.is_worker_bound("worker-1")


class TestDefaultStateSync:
    """Tests for default state sync singleton."""

    def test_get_state_sync_returns_instance(self, mock_db, binding_manager):
        """Should return a state sync instance."""
        sync = get_state_sync(mock_db, binding_manager)

        assert sync is not None
        assert isinstance(sync, SessionStateSync)

    def test_get_state_sync_returns_same_instance(
        self, mock_db, binding_manager
    ):
        """Should return same instance on repeated calls."""
        sync1 = get_state_sync(mock_db, binding_manager)
        sync2 = get_state_sync(mock_db, binding_manager)

        assert sync1 is sync2

    def test_reset_state_sync_clears_instance(self, mock_db, binding_manager):
        """Should clear singleton on reset."""
        sync1 = get_state_sync(mock_db, binding_manager)
        reset_state_sync()
        sync2 = get_state_sync(mock_db, binding_manager)

        assert sync1 is not sync2
