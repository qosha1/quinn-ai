"""
Tests for session cleanup functionality.

Tests orphaned session detection and cleanup:
- Orphaned tmux sessions (exist in tmux but not tracked)
- Stale database records (tracked but tmux session gone)
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.db import init_database
from core.queries import create_team, create_worker
from core.sessions.cleanup import (
    TMUX_SESSION_PREFIX,
    OrphanedSession,
    CleanupResult,
    find_orphaned_tmux_sessions,
    find_stale_db_sessions,
    find_all_orphans,
    cleanup_orphaned_sessions,
    run_startup_cleanup,
)
from core.sessions.persistence import (
    create_session_record,
    get_session_by_id,
    get_active_sessions,
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
def mock_tmux_spawner():
    """Create a mock TmuxSpawner."""
    spawner = MagicMock()
    spawner.list_sessions.return_value = []
    spawner.is_alive.return_value = False
    spawner.stop.return_value = True
    return spawner


class TestOrphanedSession:
    """Tests for OrphanedSession dataclass."""

    def test_create_tmux_orphan(self):
        """Should create tmux orphan with minimal fields."""
        orphan = OrphanedSession(
            session_name="qn-worker-123",
            source="tmux",
        )
        assert orphan.session_name == "qn-worker-123"
        assert orphan.source == "tmux"
        assert orphan.worker_id is None
        assert orphan.session_id is None

    def test_create_database_orphan(self):
        """Should create database orphan with full fields."""
        orphan = OrphanedSession(
            session_name="qn-worker-456",
            source="database",
            worker_id="worker-456",
            session_id="session-abc",
            state="running",
        )
        assert orphan.session_name == "qn-worker-456"
        assert orphan.source == "database"
        assert orphan.worker_id == "worker-456"
        assert orphan.session_id == "session-abc"
        assert orphan.state == "running"


class TestCleanupResult:
    """Tests for CleanupResult dataclass."""

    def test_empty_result(self):
        """Should create empty result."""
        result = CleanupResult(
            orphaned_tmux_sessions=[],
            stale_db_records=[],
            tmux_sessions_killed=0,
            db_records_updated=0,
            db_records_deleted=0,
            errors=[],
        )
        assert len(result.orphaned_tmux_sessions) == 0
        assert len(result.stale_db_records) == 0
        assert result.tmux_sessions_killed == 0


class TestFindOrphanedTmuxSessions:
    """Tests for find_orphaned_tmux_sessions."""

    def test_no_orphans_when_no_tmux_sessions(self, db, mock_tmux_spawner):
        """Should return empty when no tmux sessions exist."""
        mock_tmux_spawner.list_sessions.return_value = []

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 0

    def test_no_orphans_when_all_tracked(self, db, worker, mock_tmux_spawner):
        """Should return empty when all tmux sessions are tracked."""
        # Create a tracked session
        create_session_record(
            db=db,
            session_id="session-123",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-worker-tracked",
            state="running",
        )

        # Mock tmux to return only tracked session
        mock_tmux_spawner.list_sessions.return_value = ["qn-worker-tracked"]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 0

    def test_finds_orphaned_tmux_session(self, db, mock_tmux_spawner):
        """Should find tmux sessions not in database."""
        # Mock tmux to return untracked session
        mock_tmux_spawner.list_sessions.return_value = [
            "qn-orphan-1",
            "qn-orphan-2",
        ]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 2
        assert orphans[0].session_name == "qn-orphan-1"
        assert orphans[0].source == "tmux"
        assert orphans[1].session_name == "qn-orphan-2"
        assert orphans[1].source == "tmux"

    def test_ignores_non_quinnai_sessions(self, db, mock_tmux_spawner):
        """Should ignore tmux sessions without quinnai prefix."""
        mock_tmux_spawner.list_sessions.return_value = [
            "other-session",
            "my-dev-session",
            "qn-orphan",
        ]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 1
        assert orphans[0].session_name == "qn-orphan"

    def test_mixed_tracked_and_orphaned(self, db, worker, mock_tmux_spawner):
        """Should find only orphaned sessions among mixed list."""
        # Create a tracked session
        create_session_record(
            db=db,
            session_id="session-tracked",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-tracked",
            state="running",
        )

        # Mock tmux with mix of tracked and orphaned
        mock_tmux_spawner.list_sessions.return_value = [
            "qn-tracked",
            "qn-orphan-1",
            "qn-orphan-2",
        ]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 2
        session_names = [o.session_name for o in orphans]
        assert "qn-orphan-1" in session_names
        assert "qn-orphan-2" in session_names
        assert "qn-tracked" not in session_names


class TestFindStaleDbSessions:
    """Tests for find_stale_db_sessions."""

    def test_no_stale_when_no_sessions(self, db, mock_tmux_spawner):
        """Should return empty when no sessions in database."""
        orphans = find_stale_db_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 0

    def test_no_stale_when_all_alive(self, db, worker, mock_tmux_spawner):
        """Should return empty when all tracked sessions are alive."""
        create_session_record(
            db=db,
            session_id="session-123",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-alive",
            state="running",
        )

        # Mock tmux to report session as alive
        mock_tmux_spawner.is_alive.return_value = True

        orphans = find_stale_db_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 0

    def test_finds_stale_session(self, db, worker, mock_tmux_spawner):
        """Should find database records where tmux is gone."""
        create_session_record(
            db=db,
            session_id="session-stale",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-stale",
            state="running",
        )

        # Mock tmux to report session as dead
        mock_tmux_spawner.is_alive.return_value = False

        orphans = find_stale_db_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 1
        assert orphans[0].session_name == "qn-stale"
        assert orphans[0].source == "database"
        assert orphans[0].worker_id == worker.id
        assert orphans[0].session_id == "session-stale"
        assert orphans[0].state == "running"

    def test_ignores_stopped_sessions(self, db, worker, mock_tmux_spawner):
        """Should not check stopped sessions (they're expected to be dead)."""
        create_session_record(
            db=db,
            session_id="session-stopped",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-stopped",
            state="stopped",
        )

        mock_tmux_spawner.is_alive.return_value = False

        orphans = find_stale_db_sessions(db, mock_tmux_spawner)

        # Stopped sessions are not considered active, so not checked
        assert len(orphans) == 0

    def test_ignores_sessions_without_tmux(self, db, worker, mock_tmux_spawner):
        """Should ignore sessions without tmux name (subprocess spawner)."""
        create_session_record(
            db=db,
            session_id="session-subprocess",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name=None,  # No tmux
            state="running",
        )

        orphans = find_stale_db_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 0


class TestFindAllOrphans:
    """Tests for find_all_orphans."""

    def test_finds_both_types(self, db, worker, mock_tmux_spawner):
        """Should find both tmux orphans and stale db records."""
        # Create a stale session
        create_session_record(
            db=db,
            session_id="session-stale",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-stale",
            state="running",
        )

        # Mock tmux with orphaned session and stale session dead
        mock_tmux_spawner.list_sessions.return_value = [
            "qn-orphan-tmux",
        ]
        mock_tmux_spawner.is_alive.return_value = False

        orphans = find_all_orphans(db, mock_tmux_spawner)

        assert len(orphans) == 2
        sources = [o.source for o in orphans]
        assert "tmux" in sources
        assert "database" in sources


class TestCleanupOrphanedSessions:
    """Tests for cleanup_orphaned_sessions."""

    def test_kills_orphaned_tmux_sessions(self, db, mock_tmux_spawner):
        """Should kill orphaned tmux sessions."""
        mock_tmux_spawner.list_sessions.return_value = [
            "qn-orphan-1",
            "qn-orphan-2",
        ]
        mock_tmux_spawner.stop.return_value = True

        result = cleanup_orphaned_sessions(
            db=db,
            tmux_spawner=mock_tmux_spawner,
            kill_tmux=True,
        )

        assert result.tmux_sessions_killed == 2
        assert len(result.orphaned_tmux_sessions) == 2
        assert mock_tmux_spawner.stop.call_count == 2

    def test_marks_stale_as_crashed(self, db, worker, mock_tmux_spawner):
        """Should mark stale database records as crashed."""
        create_session_record(
            db=db,
            session_id="session-stale",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-stale",
            state="running",
        )

        mock_tmux_spawner.list_sessions.return_value = []
        mock_tmux_spawner.is_alive.return_value = False

        result = cleanup_orphaned_sessions(
            db=db,
            tmux_spawner=mock_tmux_spawner,
            update_db=True,
            delete_stale=False,
        )

        assert result.db_records_updated == 1
        assert len(result.stale_db_records) == 1

        # Verify the session was marked as crashed
        session = get_session_by_id(db, "session-stale")
        assert session["state"] == "crashed"
        assert session["stopped_at"] is not None

    def test_deletes_stale_when_requested(self, db, worker, mock_tmux_spawner):
        """Should delete stale records when delete_stale=True."""
        create_session_record(
            db=db,
            session_id="session-stale",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-stale",
            state="running",
        )

        mock_tmux_spawner.list_sessions.return_value = []
        mock_tmux_spawner.is_alive.return_value = False

        result = cleanup_orphaned_sessions(
            db=db,
            tmux_spawner=mock_tmux_spawner,
            update_db=True,
            delete_stale=True,
        )

        assert result.db_records_deleted == 1

        # Verify the session was deleted
        session = get_session_by_id(db, "session-stale")
        assert session is None

    def test_respects_kill_tmux_false(self, db, mock_tmux_spawner):
        """Should not kill tmux when kill_tmux=False."""
        mock_tmux_spawner.list_sessions.return_value = ["qn-orphan"]

        result = cleanup_orphaned_sessions(
            db=db,
            tmux_spawner=mock_tmux_spawner,
            kill_tmux=False,
        )

        assert result.tmux_sessions_killed == 0
        assert len(result.orphaned_tmux_sessions) == 1
        mock_tmux_spawner.stop.assert_not_called()

    def test_respects_update_db_false(self, db, worker, mock_tmux_spawner):
        """Should not update db when update_db=False."""
        create_session_record(
            db=db,
            session_id="session-stale",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-stale",
            state="running",
        )

        mock_tmux_spawner.list_sessions.return_value = []
        mock_tmux_spawner.is_alive.return_value = False

        result = cleanup_orphaned_sessions(
            db=db,
            tmux_spawner=mock_tmux_spawner,
            update_db=False,
        )

        assert result.db_records_updated == 0
        assert len(result.stale_db_records) == 1

        # Verify the session was NOT modified
        session = get_session_by_id(db, "session-stale")
        assert session["state"] == "running"

    def test_records_errors(self, db, mock_tmux_spawner):
        """Should record errors without failing."""
        mock_tmux_spawner.list_sessions.return_value = ["qn-orphan"]
        mock_tmux_spawner.stop.side_effect = Exception("tmux error")

        result = cleanup_orphaned_sessions(
            db=db,
            tmux_spawner=mock_tmux_spawner,
            kill_tmux=True,
        )

        assert result.tmux_sessions_killed == 0
        assert len(result.errors) == 1
        assert "tmux error" in result.errors[0]


class TestRunStartupCleanup:
    """Tests for run_startup_cleanup convenience function."""

    def test_startup_cleanup_settings(self, db, worker, mock_tmux_spawner):
        """Should use appropriate settings for startup."""
        # Create both types of orphans
        create_session_record(
            db=db,
            session_id="session-stale",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name="qn-stale",
            state="running",
        )

        mock_tmux_spawner.list_sessions.return_value = ["qn-orphan-tmux"]
        mock_tmux_spawner.is_alive.return_value = False
        mock_tmux_spawner.stop.return_value = True

        result = run_startup_cleanup(db, mock_tmux_spawner)

        # Should kill tmux orphans
        assert result.tmux_sessions_killed == 1

        # Should update db records (mark crashed, not delete)
        assert result.db_records_updated == 1
        assert result.db_records_deleted == 0

        # Verify session is crashed, not deleted
        session = get_session_by_id(db, "session-stale")
        assert session is not None
        assert session["state"] == "crashed"


class TestTmuxSessionPrefix:
    """Tests for TMUX_SESSION_PREFIX constant."""

    def test_prefix_value(self):
        """Should have correct prefix value."""
        assert TMUX_SESSION_PREFIX == "qn-"
