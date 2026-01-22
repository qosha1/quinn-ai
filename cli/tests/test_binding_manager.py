"""
Tests for SessionBindingManager.
"""

import pytest
from unittest.mock import MagicMock, patch

from cli.core.sessions import (
    SessionBindingManager,
    SessionBinding,
    WorkerAlreadyBoundError,
    SessionAlreadyBoundError,
    get_binding_manager,
    reset_binding_manager,
)


class TestSessionBindingManager:
    """Tests for SessionBindingManager."""

    @pytest.fixture
    def manager(self):
        """Create a fresh binding manager."""
        return SessionBindingManager()

    @pytest.fixture(autouse=True)
    def reset_default(self):
        """Reset default manager after each test."""
        yield
        reset_binding_manager()

    def test_bind_creates_binding(self, manager):
        """Should create binding between worker and session."""
        binding = manager.bind("worker-1", "session-a")

        assert binding.worker_id == "worker-1"
        assert binding.session_id == "session-a"
        assert binding.bound_at is not None

    def test_bind_with_pid(self, manager):
        """Should store PID in binding."""
        binding = manager.bind("worker-1", "session-a", pid=12345)

        assert binding.pid == 12345

    def test_bind_with_metadata(self, manager):
        """Should store metadata in binding."""
        binding = manager.bind(
            "worker-1", "session-a", metadata={"provider": "claude_code"}
        )

        assert binding.metadata == {"provider": "claude_code"}

    def test_bind_duplicate_returns_existing(self, manager):
        """Should return existing binding if same worker-session pair."""
        binding1 = manager.bind("worker-1", "session-a")
        binding2 = manager.bind("worker-1", "session-a")

        assert binding1 is binding2

    def test_bind_worker_already_bound(self, manager):
        """Should raise error if worker already has different session."""
        manager.bind("worker-1", "session-a")

        with pytest.raises(WorkerAlreadyBoundError) as exc_info:
            manager.bind("worker-1", "session-b")

        assert exc_info.value.worker_id == "worker-1"
        assert exc_info.value.existing_session_id == "session-a"

    def test_bind_session_already_bound(self, manager):
        """Should raise error if session already bound to different worker."""
        manager.bind("worker-1", "session-a")

        with pytest.raises(SessionAlreadyBoundError) as exc_info:
            manager.bind("worker-2", "session-a")

        assert exc_info.value.session_id == "session-a"
        assert exc_info.value.existing_worker_id == "worker-1"

    def test_unbind_removes_binding(self, manager):
        """Should remove binding and return it."""
        manager.bind("worker-1", "session-a")

        binding = manager.unbind("worker-1")

        assert binding.worker_id == "worker-1"
        assert binding.session_id == "session-a"
        assert not manager.is_worker_bound("worker-1")
        assert not manager.is_session_bound("session-a")

    def test_unbind_nonexistent_returns_none(self, manager):
        """Should return None for nonexistent binding."""
        result = manager.unbind("worker-999")

        assert result is None

    def test_unbind_session_removes_binding(self, manager):
        """Should remove binding via session ID."""
        manager.bind("worker-1", "session-a")

        binding = manager.unbind_session("session-a")

        assert binding.worker_id == "worker-1"
        assert not manager.is_worker_bound("worker-1")

    def test_get_session_for_worker(self, manager):
        """Should return session ID for bound worker."""
        manager.bind("worker-1", "session-a")

        session_id = manager.get_session_for_worker("worker-1")

        assert session_id == "session-a"

    def test_get_session_for_unbound_worker(self, manager):
        """Should return None for unbound worker."""
        session_id = manager.get_session_for_worker("worker-999")

        assert session_id is None

    def test_get_worker_for_session(self, manager):
        """Should return worker ID for bound session."""
        manager.bind("worker-1", "session-a")

        worker_id = manager.get_worker_for_session("session-a")

        assert worker_id == "worker-1"

    def test_get_worker_for_unbound_session(self, manager):
        """Should return None for unbound session."""
        worker_id = manager.get_worker_for_session("session-999")

        assert worker_id is None

    def test_get_binding(self, manager):
        """Should return full binding record."""
        manager.bind("worker-1", "session-a", pid=12345)

        binding = manager.get_binding("worker-1")

        assert binding.worker_id == "worker-1"
        assert binding.session_id == "session-a"
        assert binding.pid == 12345

    def test_is_worker_bound(self, manager):
        """Should check if worker has session."""
        assert not manager.is_worker_bound("worker-1")

        manager.bind("worker-1", "session-a")

        assert manager.is_worker_bound("worker-1")

    def test_is_session_bound(self, manager):
        """Should check if session has worker."""
        assert not manager.is_session_bound("session-a")

        manager.bind("worker-1", "session-a")

        assert manager.is_session_bound("session-a")

    def test_list_bindings(self, manager):
        """Should list all bindings."""
        manager.bind("worker-1", "session-a")
        manager.bind("worker-2", "session-b")

        bindings = manager.list_bindings()

        assert len(bindings) == 2
        worker_ids = {b.worker_id for b in bindings}
        assert worker_ids == {"worker-1", "worker-2"}

    def test_list_bindings_empty(self, manager):
        """Should return empty list when no bindings."""
        bindings = manager.list_bindings()

        assert bindings == []


class TestSessionBindingManagerWithSession:
    """Tests for binding manager with session instances."""

    @pytest.fixture
    def manager(self):
        """Create a fresh binding manager."""
        return SessionBindingManager()

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        session = MagicMock()
        session.state = MagicMock()
        session.state.value = "idle"
        session.on_state_change = MagicMock()
        return session

    def test_bind_with_session_stores_instance(self, manager, mock_session):
        """Should store session instance for later retrieval."""
        manager.bind("worker-1", "session-a", session=mock_session)

        retrieved = manager.get_session("session-a")

        assert retrieved is mock_session

    def test_bind_with_session_sets_up_callback(self, manager, mock_session):
        """Should register state change callback on session."""
        manager.bind("worker-1", "session-a", session=mock_session)

        mock_session.on_state_change.assert_called_once()

    def test_unbind_removes_session_instance(self, manager, mock_session):
        """Should remove session instance on unbind."""
        manager.bind("worker-1", "session-a", session=mock_session)

        manager.unbind("worker-1")

        assert manager.get_session("session-a") is None


class TestValidateBindings:
    """Tests for binding validation."""

    @pytest.fixture
    def manager(self):
        """Create a fresh binding manager."""
        return SessionBindingManager()

    def test_validate_with_no_bindings(self, manager):
        """Should handle empty binding list."""
        results = manager.validate_bindings()

        assert results["valid"] == []
        assert results["stale"] == []
        assert results["errors"] == []

    @patch.object(SessionBindingManager, "_is_process_alive")
    def test_validate_removes_dead_pid_bindings(self, mock_alive, manager):
        """Should remove bindings with dead PIDs."""
        mock_alive.return_value = False

        manager.bind("worker-1", "session-a", pid=12345)

        results = manager.validate_bindings()

        assert "worker-1" in results["stale"]
        assert not manager.is_worker_bound("worker-1")

    @patch.object(SessionBindingManager, "_is_process_alive")
    def test_validate_keeps_alive_pid_bindings(self, mock_alive, manager):
        """Should keep bindings with alive PIDs."""
        mock_alive.return_value = True

        manager.bind("worker-1", "session-a", pid=12345)

        results = manager.validate_bindings()

        assert "worker-1" in results["valid"]
        assert manager.is_worker_bound("worker-1")

    def test_validate_removes_crashed_session_bindings(self, manager):
        """Should remove bindings for crashed sessions."""
        from cli.core.session import SessionState

        mock_session = MagicMock()
        mock_session.state = SessionState.CRASHED
        mock_session.on_state_change = MagicMock()

        manager.bind("worker-1", "session-a", session=mock_session)

        results = manager.validate_bindings()

        assert "worker-1" in results["stale"]
        assert not manager.is_worker_bound("worker-1")

    def test_validate_keeps_running_session_bindings(self, manager):
        """Should keep bindings for running sessions."""
        from cli.core.session import SessionState

        mock_session = MagicMock()
        mock_session.state = SessionState.RUNNING
        mock_session.on_state_change = MagicMock()

        manager.bind("worker-1", "session-a", session=mock_session)

        results = manager.validate_bindings()

        assert "worker-1" in results["valid"]
        assert manager.is_worker_bound("worker-1")


class TestDefaultBindingManager:
    """Tests for default manager singleton."""

    @pytest.fixture(autouse=True)
    def reset_default(self):
        """Reset default manager before and after each test."""
        reset_binding_manager()
        yield
        reset_binding_manager()

    def test_get_binding_manager_returns_singleton(self):
        """Should return same instance on repeated calls."""
        manager1 = get_binding_manager()
        manager2 = get_binding_manager()

        assert manager1 is manager2

    def test_reset_binding_manager_clears_singleton(self):
        """Should clear singleton on reset."""
        manager1 = get_binding_manager()
        reset_binding_manager()
        manager2 = get_binding_manager()

        assert manager1 is not manager2
