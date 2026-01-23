"""
Tests for SessionBindingManager.

Tests 1:1 worker-session binding enforcement, state synchronization, and lifecycle management.
"""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from cli.core.db import init_database
from cli.core.queries import create_team, create_worker
from cli.core.session import SessionState
from cli.core.sessions.binding_manager import (
    SessionBindingManager,
    SessionBinding,
    WorkerAlreadyBoundError,
    SessionAlreadyBoundError,
    BindingNotFoundError,
    get_binding_manager,
    reset_binding_manager,
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
    """Create a test worker with runtime state."""
    from cli.core.queries import create_worker_state

    worker = create_worker(db, "Alice", "Developer", team.id, 50)
    create_worker_state(db, worker.id, pid=None)
    return worker


@pytest.fixture
def binding_manager(db):
    """Create a SessionBindingManager."""
    return SessionBindingManager(db)


@pytest.fixture
def mock_session():
    """Create a mock session."""
    session = MagicMock()
    session.id = "session-123"
    session.state = SessionState.RUNNING
    session.on_state_change = MagicMock()
    return session


class TestSessionBinding:
    """Tests for SessionBinding dataclass."""

    def test_create_binding(self):
        """Should create binding with minimal fields."""
        binding = SessionBinding(
            worker_id="worker-1",
            session_id="session-1",
            bound_at=datetime.now(),
        )

        assert binding.worker_id == "worker-1"
        assert binding.session_id == "session-1"
        assert binding.pid is None
        assert binding.metadata is None

    def test_create_binding_with_all_fields(self):
        """Should create binding with all fields."""
        now = datetime.now()
        metadata = {"key": "value"}

        binding = SessionBinding(
            worker_id="worker-1",
            session_id="session-1",
            bound_at=now,
            pid=12345,
            metadata=metadata,
        )

        assert binding.worker_id == "worker-1"
        assert binding.session_id == "session-1"
        assert binding.bound_at == now
        assert binding.pid == 12345
        assert binding.metadata == metadata


class TestSessionBindingManagerInit:
    """Tests for SessionBindingManager initialization."""

    def test_init_without_db(self):
        """Should initialize without database."""
        manager = SessionBindingManager()

        assert manager._db is None
        assert len(manager._worker_to_session) == 0
        assert len(manager._session_to_worker) == 0

    def test_init_with_db(self, db):
        """Should initialize with database."""
        manager = SessionBindingManager(db)

        assert manager._db is db


class TestSessionBindingManagerBind:
    """Tests for binding sessions to workers."""

    def test_bind_success(self, binding_manager, worker):
        """Should bind session to worker."""
        binding = binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            pid=12345,
        )

        assert binding.worker_id == worker.id
        assert binding.session_id == "session-123"
        assert binding.pid == 12345
        assert isinstance(binding.bound_at, datetime)

    def test_bind_updates_indices(self, binding_manager, worker):
        """Should update both lookup indices."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
        )

        assert binding_manager.get_session_for_worker(worker.id) == "session-123"
        assert binding_manager.get_worker_for_session("session-123") == worker.id

    def test_bind_stores_session_instance(self, binding_manager, worker, mock_session):
        """Should store session instance."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        assert binding_manager.get_session("session-123") is mock_session

    def test_bind_duplicate_is_idempotent(self, binding_manager, worker):
        """Should allow rebinding same worker-session pair."""
        binding1 = binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
        )
        binding2 = binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
        )

        assert binding1 is binding2

    def test_bind_worker_already_bound_raises(self, binding_manager, worker):
        """Should raise when worker already has different session."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-1",
        )

        with pytest.raises(WorkerAlreadyBoundError) as exc_info:
            binding_manager.bind(
                worker_id=worker.id,
                session_id="session-2",
            )

        assert exc_info.value.worker_id == worker.id
        assert exc_info.value.existing_session_id == "session-1"

    def test_bind_session_already_bound_raises(self, binding_manager, db, team):
        """Should raise when session already bound to different worker."""
        worker1 = create_worker(db, "Alice", "Dev", team.id, 50)
        worker2 = create_worker(db, "Bob", "Dev", team.id, 50)

        binding_manager.bind(
            worker_id=worker1.id,
            session_id="session-123",
        )

        with pytest.raises(SessionAlreadyBoundError) as exc_info:
            binding_manager.bind(
                worker_id=worker2.id,
                session_id="session-123",
            )

        assert exc_info.value.session_id == "session-123"
        assert exc_info.value.existing_worker_id == worker1.id

    def test_bind_with_metadata(self, binding_manager, worker):
        """Should store metadata."""
        metadata = {"provider": "claude_code", "command": "claude"}

        binding = binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            metadata=metadata,
        )

        assert binding.metadata == metadata

    def test_bind_sets_up_state_callback(self, binding_manager, worker, mock_session):
        """Should set up state change callback on session."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        mock_session.on_state_change.assert_called_once()


class TestSessionBindingManagerUnbind:
    """Tests for unbinding sessions."""

    def test_unbind_success(self, binding_manager, worker):
        """Should unbind session from worker."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
        )

        removed = binding_manager.unbind(worker.id)

        assert removed is not None
        assert removed.worker_id == worker.id
        assert removed.session_id == "session-123"

    def test_unbind_removes_from_indices(self, binding_manager, worker):
        """Should remove from both indices."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
        )

        binding_manager.unbind(worker.id)

        assert binding_manager.get_session_for_worker(worker.id) is None
        assert binding_manager.get_worker_for_session("session-123") is None

    def test_unbind_removes_session_instance(self, binding_manager, worker, mock_session):
        """Should remove session instance."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        binding_manager.unbind(worker.id)

        assert binding_manager.get_session("session-123") is None

    def test_unbind_nonexistent_returns_none(self, binding_manager):
        """Should return None when worker not bound."""
        removed = binding_manager.unbind("nonexistent")

        assert removed is None

    def test_unbind_session_by_id(self, binding_manager, worker):
        """Should unbind by session ID."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
        )

        removed = binding_manager.unbind_session("session-123")

        assert removed is not None
        assert removed.worker_id == worker.id

    def test_unbind_session_nonexistent(self, binding_manager):
        """Should return None when session not bound."""
        removed = binding_manager.unbind_session("nonexistent")

        assert removed is None


class TestSessionBindingManagerLookup:
    """Tests for binding lookups."""

    def test_get_session_for_worker(self, binding_manager, worker):
        """Should get session ID for worker."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
        )

        session_id = binding_manager.get_session_for_worker(worker.id)

        assert session_id == "session-123"

    def test_get_session_for_worker_not_bound(self, binding_manager):
        """Should return None when worker not bound."""
        session_id = binding_manager.get_session_for_worker("nonexistent")

        assert session_id is None

    def test_get_worker_for_session(self, binding_manager, worker):
        """Should get worker ID for session."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
        )

        worker_id = binding_manager.get_worker_for_session("session-123")

        assert worker_id == worker.id

    def test_get_worker_for_session_not_bound(self, binding_manager):
        """Should return None when session not bound."""
        worker_id = binding_manager.get_worker_for_session("nonexistent")

        assert worker_id is None

    def test_get_binding(self, binding_manager, worker):
        """Should get full binding record."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            pid=12345,
        )

        binding = binding_manager.get_binding(worker.id)

        assert binding is not None
        assert binding.worker_id == worker.id
        assert binding.session_id == "session-123"
        assert binding.pid == 12345

    def test_get_binding_not_found(self, binding_manager):
        """Should return None when binding not found."""
        binding = binding_manager.get_binding("nonexistent")

        assert binding is None

    def test_is_worker_bound(self, binding_manager, worker):
        """Should check if worker is bound."""
        assert not binding_manager.is_worker_bound(worker.id)

        binding_manager.bind(worker.id, "session-123")

        assert binding_manager.is_worker_bound(worker.id)

    def test_is_session_bound(self, binding_manager, worker):
        """Should check if session is bound."""
        assert not binding_manager.is_session_bound("session-123")

        binding_manager.bind(worker.id, "session-123")

        assert binding_manager.is_session_bound("session-123")

    def test_get_session(self, binding_manager, worker, mock_session):
        """Should get session instance."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        session = binding_manager.get_session("session-123")

        assert session is mock_session

    def test_get_session_not_found(self, binding_manager):
        """Should return None when session not tracked."""
        session = binding_manager.get_session("nonexistent")

        assert session is None


class TestSessionBindingManagerListBindings:
    """Tests for listing bindings."""

    def test_list_bindings_empty(self, binding_manager):
        """Should return empty list when no bindings."""
        bindings = binding_manager.list_bindings()

        assert len(bindings) == 0

    def test_list_bindings(self, binding_manager, db, team):
        """Should list all bindings."""
        worker1 = create_worker(db, "Alice", "Dev", team.id, 50)
        worker2 = create_worker(db, "Bob", "Dev", team.id, 50)

        binding_manager.bind(worker1.id, "session-1")
        binding_manager.bind(worker2.id, "session-2")

        bindings = binding_manager.list_bindings()

        assert len(bindings) == 2
        worker_ids = [b.worker_id for b in bindings]
        assert worker1.id in worker_ids
        assert worker2.id in worker_ids


class TestSessionBindingManagerValidation:
    """Tests for binding validation."""

    def test_validate_bindings_all_valid(self, binding_manager, worker, mock_session):
        """Should mark all bindings as valid when sessions running."""
        mock_session.state = SessionState.RUNNING

        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        results = binding_manager.validate_bindings()

        assert worker.id in results["valid"]
        assert len(results["stale"]) == 0
        assert len(results["errors"]) == 0

    def test_validate_bindings_removes_stopped(self, binding_manager, worker, mock_session):
        """Should remove bindings for stopped sessions."""
        mock_session.state = SessionState.STOPPED

        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        results = binding_manager.validate_bindings()

        assert worker.id in results["stale"]
        assert not binding_manager.is_worker_bound(worker.id)

    def test_validate_bindings_removes_crashed(self, binding_manager, worker, mock_session):
        """Should remove bindings for crashed sessions."""
        mock_session.state = SessionState.CRASHED

        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        results = binding_manager.validate_bindings()

        assert worker.id in results["stale"]

    @patch("os.kill")
    def test_validate_bindings_checks_pid(self, mock_kill, binding_manager, worker):
        """Should check PID when session instance not available."""
        # PID exists
        mock_kill.return_value = None

        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            pid=12345,
        )

        results = binding_manager.validate_bindings()

        assert worker.id in results["valid"]
        mock_kill.assert_called_once_with(12345, 0)

    @patch("os.kill")
    def test_validate_bindings_removes_dead_pid(self, mock_kill, binding_manager, worker):
        """Should remove bindings when PID is dead."""
        mock_kill.side_effect = OSError("No such process")

        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            pid=12345,
        )

        results = binding_manager.validate_bindings()

        assert worker.id in results["stale"]
        assert not binding_manager.is_worker_bound(worker.id)

    def test_validate_bindings_fixes_orphaned_index(self, binding_manager, worker):
        """Should fix orphaned session index entries."""
        # Manually create inconsistency
        binding_manager._session_to_worker["orphaned-session"] = "nonexistent-worker"

        results = binding_manager.validate_bindings()

        assert len(results["errors"]) > 0
        assert "orphaned-session" not in binding_manager._session_to_worker


class TestSessionBindingManagerStateCallback:
    """Tests for state change callbacks."""

    def test_state_callback_setup(self, binding_manager, worker, mock_session):
        """Should set up state callback on bind."""
        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        # Verify callback was registered
        mock_session.on_state_change.assert_called_once()

    def test_state_callback_updates_worker_state(self, binding_manager, db, worker, mock_session):
        """Should update worker runtime status on state change."""
        from cli.core.queries import get_worker_state

        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            session=mock_session,
        )

        # Get the callback that was registered
        callback = mock_session.on_state_change.call_args[0][0]

        # Simulate state change
        callback(SessionState.STARTING, SessionState.RUNNING)

        # Check worker state was updated
        state = get_worker_state(db, worker.id)
        assert state.runtime_status == "running"


class TestSessionBindingManagerPersistence:
    """Tests for database persistence."""

    def test_bind_persists_to_db(self, binding_manager, db, worker):
        """Should persist binding to database."""
        from cli.core.queries import get_worker_state

        binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            pid=12345,
        )

        state = get_worker_state(db, worker.id)
        assert state.pid == 12345

    def test_unbind_clears_db(self, binding_manager, db, worker):
        """Should clear binding from database."""
        from cli.core.queries import get_worker_state

        binding_manager.bind(worker.id, "session-123", pid=12345)
        binding_manager.unbind(worker.id)

        state = get_worker_state(db, worker.id)
        assert state.pid is None


class TestSessionBindingManagerDefaults:
    """Tests for default manager functions."""

    def setup_method(self):
        """Reset binding manager before each test."""
        reset_binding_manager()

    def teardown_method(self):
        """Reset binding manager after each test."""
        reset_binding_manager()

    def test_get_binding_manager_lazy_init(self, db):
        """Should lazily initialize default manager."""
        manager = get_binding_manager(db)

        assert manager is not None
        assert isinstance(manager, SessionBindingManager)

    def test_get_binding_manager_singleton(self, db):
        """Should return same instance on subsequent calls."""
        manager1 = get_binding_manager(db)
        manager2 = get_binding_manager()

        assert manager1 is manager2

    def test_reset_binding_manager(self, db):
        """Should reset to None."""
        initial = get_binding_manager(db)

        reset_binding_manager()

        new = get_binding_manager(db)
        assert new is not initial


class TestSessionBindingManagerThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_bind(self, binding_manager, db, team):
        """Should handle concurrent bind calls."""
        import threading

        workers = [create_worker(db, f"Worker{i}", "Dev", team.id, 50) for i in range(10)]
        results = []

        def bind_worker(worker):
            try:
                binding = binding_manager.bind(
                    worker_id=worker.id,
                    session_id=f"session-{worker.id}",
                )
                results.append(("success", binding))
            except Exception as e:
                results.append(("error", str(e)))

        threads = [threading.Thread(target=bind_worker, args=(w,)) for w in workers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r[0] == "success"]
        assert len(successes) == 10

    def test_concurrent_unbind(self, binding_manager, db, team):
        """Should handle concurrent unbind calls."""
        import threading

        workers = [create_worker(db, f"Worker{i}", "Dev", team.id, 50) for i in range(5)]
        for w in workers:
            binding_manager.bind(w.id, f"session-{w.id}")

        results = []

        def unbind_worker(worker):
            removed = binding_manager.unbind(worker.id)
            results.append(removed)

        threads = [threading.Thread(target=unbind_worker, args=(w,)) for w in workers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len([r for r in results if r is not None]) == 5


class TestSessionBindingManagerIntegration:
    """Integration tests for SessionBindingManager."""

    def test_full_lifecycle(self, binding_manager, worker, mock_session):
        """Test complete binding lifecycle."""
        # Bind
        binding = binding_manager.bind(
            worker_id=worker.id,
            session_id="session-123",
            pid=12345,
            session=mock_session,
        )

        assert binding_manager.is_worker_bound(worker.id)
        assert binding_manager.is_session_bound("session-123")

        # Validate
        results = binding_manager.validate_bindings()
        assert worker.id in results["valid"]

        # Unbind
        removed = binding_manager.unbind(worker.id)
        assert removed is not None

        assert not binding_manager.is_worker_bound(worker.id)
        assert not binding_manager.is_session_bound("session-123")

    def test_enforce_1_to_1_relationship(self, binding_manager, db, team):
        """Should enforce 1:1 worker-session relationship."""
        worker1 = create_worker(db, "Alice", "Dev", team.id, 50)
        worker2 = create_worker(db, "Bob", "Dev", team.id, 50)
        worker3 = create_worker(db, "Charlie", "Dev", team.id, 50)

        # Worker can only have one session
        binding_manager.bind(worker1.id, "session-1")
        with pytest.raises(WorkerAlreadyBoundError):
            binding_manager.bind(worker1.id, "session-2")

        # Session can only belong to one worker
        binding_manager.bind(worker2.id, "session-2")
        with pytest.raises(SessionAlreadyBoundError):
            binding_manager.bind(worker3.id, "session-2")
