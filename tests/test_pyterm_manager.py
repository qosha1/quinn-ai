"""
Tests for SessionManager - manages multiple worker sessions.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from shared.pyterm.manager import SessionManager, ManagedSession
from shared.pyterm.protocols import PytermSessionState, WorkerState, PytermSessionConfig
from shared.pyterm.lifecycle import LifecycleHooks
from shared.pyterm.patterns import PatternMatcher


class MockSession:
    """Mock session for testing."""

    def __init__(self, session_id: str):
        self._id = session_id
        self._state = PytermSessionState.IDLE
        self.stopped = False

    @property
    def id(self) -> str:
        return self._id

    @property
    def state(self) -> PytermSessionState:
        return self._state

    def start(self, config=None) -> None:
        self._state = PytermSessionState.RUNNING

    def stop(self, force: bool = False) -> None:
        self.stopped = True
        self._state = PytermSessionState.EXITED


class TestManagedSession:
    """Tests for ManagedSession dataclass."""

    def test_creation(self):
        """Test ManagedSession creation."""
        session = MockSession("test-session")
        lifecycle = LifecycleHooks()
        patterns = None

        managed = ManagedSession(
            worker_id="worker-1",
            session=session,
            lifecycle=lifecycle,
            patterns=patterns,
        )

        assert managed.worker_id == "worker-1"
        assert managed.session == session
        assert managed.lifecycle == lifecycle
        assert managed.patterns is None

    def test_state_property(self):
        """Test state property delegates to session."""
        session = MockSession("test")
        lifecycle = LifecycleHooks()

        managed = ManagedSession(
            worker_id="worker-1",
            session=session,
            lifecycle=lifecycle,
        )

        assert managed.state == PytermSessionState.IDLE

        session._state = PytermSessionState.RUNNING
        assert managed.state == PytermSessionState.RUNNING

    def test_worker_state_property(self):
        """Test worker_state property delegates to lifecycle."""
        session = MockSession("test")
        lifecycle = LifecycleHooks()

        managed = ManagedSession(
            worker_id="worker-1",
            session=session,
            lifecycle=lifecycle,
        )

        assert managed.worker_state == WorkerState.PENDING

        lifecycle.transition(WorkerState.ONBOARDING)
        assert managed.worker_state == WorkerState.ONBOARDING


class TestSessionManagerCreate:
    """Tests for creating sessions."""

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_create_session(self, mock_pattern_class, mock_tmux_class):
        """Test create() creates a new session."""
        mock_session = MockSession("qn-worker-1")
        mock_tmux_class.return_value = mock_session

        mock_patterns = Mock()
        mock_pattern_class.return_value = mock_patterns

        manager = SessionManager()
        managed = manager.create("worker-1")

        assert managed.worker_id == "worker-1"
        assert managed.session == mock_session
        assert isinstance(managed.lifecycle, LifecycleHooks)
        assert managed.patterns == mock_patterns

        # Verify session name
        mock_tmux_class.assert_called_once_with(session_name="qn-worker-1")

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_create_with_custom_session_name(self, mock_pattern_class, mock_tmux_class):
        """Test create() with custom session name."""
        mock_session = MockSession("custom-name")
        mock_tmux_class.return_value = mock_session

        manager = SessionManager()
        managed = manager.create("worker-1", session_name="custom-name")

        mock_tmux_class.assert_called_once_with(session_name="custom-name")

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_create_duplicate_worker_raises(self, mock_pattern_class, mock_tmux_class):
        """Test create() raises when worker already has session."""
        mock_tmux_class.return_value = MockSession("qn-worker-1")

        manager = SessionManager()
        manager.create("worker-1")

        with pytest.raises(ValueError, match="already has a session"):
            manager.create("worker-1")

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_create_adds_to_internal_dict(self, mock_pattern_class, mock_tmux_class):
        """Test create() adds session to internal dict."""
        mock_tmux_class.return_value = MockSession("qn-worker-1")

        manager = SessionManager()
        manager.create("worker-1")

        assert "worker-1" in manager._sessions


class TestSessionManagerGet:
    """Tests for getting sessions."""

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_get_existing_session(self, mock_pattern_class, mock_tmux_class):
        """Test get() retrieves existing session."""
        mock_tmux_class.return_value = MockSession("qn-worker-1")

        manager = SessionManager()
        created = manager.create("worker-1")

        retrieved = manager.get("worker-1")

        assert retrieved == created

    def test_get_nonexistent_session(self):
        """Test get() returns None for nonexistent session."""
        manager = SessionManager()

        result = manager.get("nonexistent")

        assert result is None


class TestSessionManagerRemove:
    """Tests for removing sessions."""

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_remove_session(self, mock_pattern_class, mock_tmux_class):
        """Test remove() removes session."""
        mock_session = MockSession("qn-worker-1")
        mock_tmux_class.return_value = mock_session

        mock_patterns = Mock()
        mock_pattern_class.return_value = mock_patterns

        manager = SessionManager()
        manager.create("worker-1")

        result = manager.remove("worker-1")

        assert result is True
        assert "worker-1" not in manager._sessions

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_remove_stops_session(self, mock_pattern_class, mock_tmux_class):
        """Test remove() stops running session."""
        mock_session = MockSession("qn-worker-1")
        mock_session._state = PytermSessionState.RUNNING
        mock_tmux_class.return_value = mock_session

        manager = SessionManager()
        manager.create("worker-1")

        manager.remove("worker-1")

        assert mock_session.stopped is True

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_remove_stops_pattern_watching(self, mock_pattern_class, mock_tmux_class):
        """Test remove() stops pattern watching."""
        mock_session = MockSession("qn-worker-1")
        mock_tmux_class.return_value = mock_session

        mock_patterns = Mock()
        mock_pattern_class.return_value = mock_patterns

        manager = SessionManager()
        manager.create("worker-1")

        manager.remove("worker-1")

        mock_patterns.stop_watching.assert_called_once()

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_remove_transitions_lifecycle_to_terminated(self, mock_pattern_class, mock_tmux_class):
        """Test remove() attempts to transition lifecycle to terminated."""
        mock_session = MockSession("qn-worker-1")
        mock_tmux_class.return_value = mock_session

        manager = SessionManager()
        managed = manager.create("worker-1")

        # Transition to offboarding (valid terminal path)
        managed.lifecycle.transition(WorkerState.ONBOARDING)
        managed.lifecycle.transition(WorkerState.ACTIVE)
        managed.lifecycle.transition(WorkerState.OFFBOARDING)

        manager.remove("worker-1")

        # Should be terminated now (OFFBOARDING->TERMINATED is valid)
        assert managed.lifecycle.state == WorkerState.TERMINATED

    def test_remove_nonexistent_session(self):
        """Test remove() returns False for nonexistent session."""
        manager = SessionManager()

        result = manager.remove("nonexistent")

        assert result is False

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_remove_with_force(self, mock_pattern_class, mock_tmux_class):
        """Test remove() with force flag."""
        mock_session = Mock()
        mock_session.state = PytermSessionState.RUNNING
        mock_tmux_class.return_value = mock_session

        manager = SessionManager()
        manager.create("worker-1")

        manager.remove("worker-1", force=True)

        mock_session.stop.assert_called_once_with(force=True)


class TestSessionManagerListOperations:
    """Tests for list operations."""

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_list_active(self, mock_pattern_class, mock_tmux_class):
        """Test list_active() returns running sessions."""
        # Create 3 sessions, 2 running, 1 idle
        sessions = [
            MockSession("qn-worker-1"),
            MockSession("qn-worker-2"),
            MockSession("qn-worker-3"),
        ]
        sessions[0]._state = PytermSessionState.RUNNING
        sessions[1]._state = PytermSessionState.RUNNING
        sessions[2]._state = PytermSessionState.IDLE

        mock_tmux_class.side_effect = sessions

        manager = SessionManager()
        manager.create("worker-1")
        manager.create("worker-2")
        manager.create("worker-3")

        active = manager.list_active()

        assert len(active) == 2
        worker_ids = {m.worker_id for m in active}
        assert worker_ids == {"worker-1", "worker-2"}

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_list_by_worker_state(self, mock_pattern_class, mock_tmux_class):
        """Test list_by_worker_state() filters by lifecycle state."""
        sessions = [MockSession(f"qn-worker-{i}") for i in range(3)]
        mock_tmux_class.side_effect = sessions

        manager = SessionManager()
        m1 = manager.create("worker-1")
        m2 = manager.create("worker-2")
        m3 = manager.create("worker-3")

        # Transition states
        m1.lifecycle.transition(WorkerState.ONBOARDING)
        m2.lifecycle.transition(WorkerState.ONBOARDING)
        m2.lifecycle.transition(WorkerState.ACTIVE)
        # m3 stays in PENDING

        # List ONBOARDING
        onboarding = manager.list_by_worker_state(WorkerState.ONBOARDING)
        assert len(onboarding) == 1
        assert onboarding[0].worker_id == "worker-1"

        # List ACTIVE
        active = manager.list_by_worker_state(WorkerState.ACTIVE)
        assert len(active) == 1
        assert active[0].worker_id == "worker-2"

        # List PENDING
        pending = manager.list_by_worker_state(WorkerState.PENDING)
        assert len(pending) == 1
        assert pending[0].worker_id == "worker-3"


class TestSessionManagerIteration:
    """Tests for iteration and container operations."""

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_iteration(self, mock_pattern_class, mock_tmux_class):
        """Test iterating over manager yields all sessions."""
        sessions = [MockSession(f"qn-worker-{i}") for i in range(3)]
        mock_tmux_class.side_effect = sessions

        manager = SessionManager()
        manager.create("worker-1")
        manager.create("worker-2")
        manager.create("worker-3")

        collected = list(manager)

        assert len(collected) == 3
        worker_ids = {m.worker_id for m in collected}
        assert worker_ids == {"worker-1", "worker-2", "worker-3"}

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_len(self, mock_pattern_class, mock_tmux_class):
        """Test len() returns session count."""
        sessions = [MockSession(f"qn-worker-{i}") for i in range(2)]
        mock_tmux_class.side_effect = sessions

        manager = SessionManager()

        assert len(manager) == 0

        manager.create("worker-1")
        assert len(manager) == 1

        manager.create("worker-2")
        assert len(manager) == 2

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_contains(self, mock_pattern_class, mock_tmux_class):
        """Test 'in' operator checks for worker."""
        mock_tmux_class.return_value = MockSession("qn-worker-1")

        manager = SessionManager()
        manager.create("worker-1")

        assert "worker-1" in manager
        assert "worker-2" not in manager


class TestSessionManagerCleanup:
    """Tests for cleanup operations."""

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_cleanup_exited(self, mock_pattern_class, mock_tmux_class):
        """Test cleanup_exited() removes exited sessions."""
        sessions = [MockSession(f"qn-worker-{i}") for i in range(4)]
        sessions[0]._state = PytermSessionState.RUNNING
        sessions[1]._state = PytermSessionState.EXITED
        sessions[2]._state = PytermSessionState.ERROR
        sessions[3]._state = PytermSessionState.IDLE

        mock_tmux_class.side_effect = sessions

        manager = SessionManager()
        manager.create("worker-1")
        manager.create("worker-2")
        manager.create("worker-3")
        manager.create("worker-4")

        count = manager.cleanup_exited()

        assert count == 2  # EXITED and ERROR
        assert len(manager) == 2
        assert "worker-1" in manager  # RUNNING
        assert "worker-4" in manager  # IDLE
        assert "worker-2" not in manager  # EXITED
        assert "worker-3" not in manager  # ERROR

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_stop_all(self, mock_pattern_class, mock_tmux_class):
        """Test stop_all() stops all running sessions."""
        sessions = [MockSession(f"qn-worker-{i}") for i in range(3)]
        sessions[0]._state = PytermSessionState.RUNNING
        sessions[1]._state = PytermSessionState.RUNNING
        sessions[2]._state = PytermSessionState.IDLE

        mock_tmux_class.side_effect = sessions

        manager = SessionManager()
        manager.create("worker-1")
        manager.create("worker-2")
        manager.create("worker-3")

        manager.stop_all()

        assert sessions[0].stopped is True
        assert sessions[1].stopped is True
        assert sessions[2].stopped is False  # Not running, so not stopped

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_stop_all_with_force(self, mock_pattern_class, mock_tmux_class):
        """Test stop_all() with force flag."""
        mock_session = Mock()
        mock_session.state = PytermSessionState.RUNNING
        mock_tmux_class.return_value = mock_session

        manager = SessionManager()
        manager.create("worker-1")

        manager.stop_all(force=True)

        mock_session.stop.assert_called_once_with(force=True)


class TestSessionManagerThreadSafety:
    """Tests for thread safety."""

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_concurrent_create(self, mock_pattern_class, mock_tmux_class):
        """Test concurrent session creation is thread-safe."""
        import threading

        mock_tmux_class.side_effect = lambda session_name: MockSession(session_name)

        manager = SessionManager()
        errors = []

        def create_session(worker_id: str):
            try:
                manager.create(worker_id)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=create_session, args=(f"worker-{i}",))
            for i in range(10)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(manager) == 10

    @patch('shared.pyterm.manager.TmuxSession')
    @patch('shared.pyterm.manager.PatternMatcher')
    def test_concurrent_create_duplicate_raises(self, mock_pattern_class, mock_tmux_class):
        """Test concurrent create of same worker raises."""
        import threading

        mock_tmux_class.return_value = MockSession("qn-worker-1")

        manager = SessionManager()
        errors = []

        def create_duplicate():
            try:
                manager.create("worker-1")
            except ValueError as e:
                errors.append(e)

        threads = [threading.Thread(target=create_duplicate) for _ in range(3)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # One should succeed, two should raise
        assert len(manager) == 1
        assert len(errors) == 2
