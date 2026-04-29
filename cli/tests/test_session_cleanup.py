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

from cli.core.db import init_database
from cli.core.queries import create_team, create_worker
from cli.core.sessions.cleanup import (
    TMUX_SESSION_PREFIX,
    OrphanedSession,
    CleanupResult,
    find_orphaned_tmux_sessions,
    find_stale_db_sessions,
    find_all_orphans,
    cleanup_orphaned_sessions,
    run_startup_cleanup,
)
from cli.core.sessions.persistence import (
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
        tmux_name = f"qn-{worker.id}"
        create_session_record(
            db=db,
            session_id="session-123",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name=tmux_name,
            state="running",
        )

        mock_tmux_spawner.list_sessions.return_value = [tmux_name]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 0

    def test_finds_orphaned_tmux_session_for_known_worker(
        self, db, worker, mock_tmux_spawner
    ):
        """Should find tmux sessions for OUR workers that aren't tracked
        in the sessions table (e.g., crashed without DB cleanup)."""
        # Worker exists in DB but no session record — yet tmux has a
        # session named after the worker.
        tmux_name = f"qn-{worker.id}"
        mock_tmux_spawner.list_sessions.return_value = [tmux_name]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        assert len(orphans) == 1
        assert orphans[0].session_name == tmux_name
        assert orphans[0].source == "tmux"

    def test_ignores_non_quinnai_sessions(self, db, worker, mock_tmux_spawner):
        """Should ignore tmux sessions without the quinnai prefix."""
        # Plus a sibling-org session (qn- prefix but unknown worker_id) —
        # should also be ignored.
        mock_tmux_spawner.list_sessions.return_value = [
            "other-session",
            "my-dev-session",
            f"qn-{worker.id}",  # ours — would be classified as orphan
            "qn-wrkr-deadbeef",  # sibling org's, must NOT be touched
        ]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        # Only OUR wrkr's untracked session is reported.
        assert len(orphans) == 1
        assert orphans[0].session_name == f"qn-{worker.id}"

    def test_mixed_tracked_and_orphaned(self, db, worker, mock_tmux_spawner):
        """Should find only orphaned sessions among mixed list — and they
        must all key on workers that belong to THIS db."""
        from cli.core.queries import create_worker

        worker2 = create_worker(db, "Bob", "Engineer", worker.team_id, 30)

        tracked = f"qn-{worker.id}"
        untracked_own = f"qn-{worker2.id}"
        sibling_org = "qn-wrkr-sibling"  # must be ignored

        create_session_record(
            db=db,
            session_id="session-tracked",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name=tracked,
            state="running",
        )

        mock_tmux_spawner.list_sessions.return_value = [
            tracked, untracked_own, sibling_org,
        ]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        # Only the untracked-but-OURS session is an orphan.
        session_names = [o.session_name for o in orphans]
        assert session_names == [untracked_own]
        assert tracked not in session_names
        assert sibling_org not in session_names

    def test_does_not_classify_sibling_orgs_sessions_as_orphans(
        self, db, worker, mock_tmux_spawner
    ):
        """Regression for quinn-ai-non8: a tmux session for a worker_id
        not in this org's workers table must NOT be flagged as orphan,
        even though it shares the global 'qn-' prefix.

        Pre-fix, running canaries 03 and 04 in parallel caused canary 03's
        startup cleanup to kill canary 04's CEO session because the global
        list_sessions() returns sessions from EVERY QuinnAI org on the
        machine. We now key on 'wrkr-id is in OUR workers table'.
        """
        # This db has 'worker' (Alice). The sibling org has wrkr-foreign.
        sibling_session = "qn-wrkr-foreign-from-other-org"
        mock_tmux_spawner.list_sessions.return_value = [sibling_session]

        orphans = find_orphaned_tmux_sessions(db, mock_tmux_spawner)

        assert orphans == [], (
            f"sibling org's session '{sibling_session}' must NOT be classified "
            f"as orphan — got {[o.session_name for o in orphans]}"
        )


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
        from cli.core.queries import create_worker

        # Stale db record: worker has session in DB but tmux is dead.
        create_session_record(
            db=db,
            session_id="session-stale",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name=f"qn-{worker.id}",
            state="running",
        )

        # Tmux orphan: a SECOND worker exists in this org with a tmux
        # session but no DB record. Per quinn-ai-non8 the orphan check
        # only fires for sessions whose worker_id is in our workers
        # table, so the orphan needs a real worker_id.
        worker2 = create_worker(db, "Bob", "Engineer", worker.team_id, 30)

        mock_tmux_spawner.list_sessions.return_value = [f"qn-{worker2.id}"]
        mock_tmux_spawner.is_alive.return_value = False

        orphans = find_all_orphans(db, mock_tmux_spawner)

        assert len(orphans) == 2
        sources = [o.source for o in orphans]
        assert "tmux" in sources
        assert "database" in sources


class TestCleanupOrphanedSessions:
    """Tests for cleanup_orphaned_sessions."""

    def test_kills_orphaned_tmux_sessions(self, db, team, mock_tmux_spawner):
        """Should kill orphaned tmux sessions for THIS org's workers."""
        from cli.core.queries import create_worker

        # Orphans must reference real worker_ids (quinn-ai-non8 fix).
        w1 = create_worker(db, "Alice", "Engineer", team.id, 30)
        w2 = create_worker(db, "Bob", "Engineer", team.id, 30)

        mock_tmux_spawner.list_sessions.return_value = [
            f"qn-{w1.id}",
            f"qn-{w2.id}",
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

    def test_respects_kill_tmux_false(self, db, worker, mock_tmux_spawner):
        """Should not kill tmux when kill_tmux=False."""
        mock_tmux_spawner.list_sessions.return_value = [f"qn-{worker.id}"]

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

    def test_records_errors(self, db, worker, mock_tmux_spawner):
        """Should record errors without failing."""
        mock_tmux_spawner.list_sessions.return_value = [f"qn-{worker.id}"]
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
        from cli.core.queries import create_worker

        # Stale db record for the existing worker.
        create_session_record(
            db=db,
            session_id="session-stale",
            worker_id=worker.id,
            provider="claude_code",
            command="claude",
            tmux_session_name=f"qn-{worker.id}",
            state="running",
        )

        # Tmux orphan for a SECOND worker (must reference a real wrkr-id
        # in this org's workers table — quinn-ai-non8).
        worker2 = create_worker(db, "Bob", "Engineer", worker.team_id, 30)
        mock_tmux_spawner.list_sessions.return_value = [f"qn-{worker2.id}"]
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
