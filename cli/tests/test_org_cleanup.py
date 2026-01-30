"""
Unit tests for qn org cleanup command.

Tests the cleanup command CLI including:
- Dry-run mode showing what would be cleaned up
- Actual cleanup execution
- Notification cleanup with retention period
- Session cleanup with orphaned resources
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from commands.main import qn
from core.constants import DEFAULT_NOTIFICATION_RETENTION_DAYS


@pytest.fixture
def runner():
    """Get Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_org():
    """Create temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def initialized_org(runner, temp_org):
    """Create an initialized org and return its path."""
    result = runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--ceo-name", "TestCEO"])
    if result.exit_code != 0:
        pytest.fail(f"org init failed: {result.output}")
    return temp_org


class TestCleanupCommandHelp:
    """Test cleanup command help and arguments."""

    def test_cleanup_help(self, runner):
        """qn org cleanup --help should show usage."""
        result = runner.invoke(qn, ["org", "cleanup", "--help"])
        assert result.exit_code == 0
        assert "--retention-days" in result.output
        assert "--dry-run" in result.output
        assert "--notifications" in result.output
        assert "--sessions" in result.output
        assert "--delete-stale-sessions" in result.output

    def test_cleanup_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "cleanup"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestCleanupDryRun:
    """Test cleanup command dry-run mode."""

    @patch('cli.commands.org.cleanup.find_all_orphans')
    def test_dry_run_shows_summary(self, mock_find_orphans, runner, initialized_org):
        """Dry-run should show what would be cleaned without deleting."""
        mock_find_orphans.return_value = []

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--dry-run"
        ])

        assert result.exit_code == 0
        assert "Dry run" in result.output

    @patch('cli.commands.org.cleanup.find_all_orphans')
    def test_dry_run_shows_notification_counts(self, mock_find_orphans, runner, initialized_org):
        """Dry-run should show notification cleanup counts."""
        mock_find_orphans.return_value = []

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--dry-run"
        ])

        assert result.exit_code == 0
        assert "Notification cleanup:" in result.output
        assert "Old closed notifications" in result.output
        assert "Expired notifications" in result.output
        assert "Orphaned notifications" in result.output

    @patch('cli.commands.org.cleanup.find_all_orphans')
    def test_dry_run_shows_session_cleanup(self, mock_find_orphans, runner, initialized_org):
        """Dry-run should show session cleanup info."""
        from core.sessions.cleanup import OrphanedSession

        # Mock orphaned sessions
        mock_find_orphans.return_value = [
            OrphanedSession(session_name="qn-worker-123", source="tmux"),
            OrphanedSession(
                session_name="qn-worker-456",
                source="database",
                worker_id="wrkr-456",
                session_id="sess-abc",
            ),
        ]

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--dry-run"
        ])

        assert result.exit_code == 0
        assert "Session cleanup:" in result.output
        assert "Orphaned tmux sessions" in result.output
        assert "Stale DB records" in result.output

    @patch('cli.commands.org.cleanup.find_all_orphans')
    def test_dry_run_with_no_notifications(self, mock_find_orphans, runner, initialized_org):
        """Dry-run with --no-notifications should skip notification counts."""
        mock_find_orphans.return_value = []

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--dry-run", "--no-notifications"
        ])

        assert result.exit_code == 0
        # Should still show session cleanup
        assert "Session cleanup:" in result.output

    @patch('cli.commands.org.cleanup.find_all_orphans')
    def test_dry_run_with_no_sessions(self, mock_find_orphans, runner, initialized_org):
        """Dry-run with --no-sessions should skip session cleanup."""
        mock_find_orphans.return_value = []

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--dry-run", "--no-sessions"
        ])

        assert result.exit_code == 0
        # Should still show notification cleanup
        assert "Notification cleanup:" in result.output
        # Should not show session cleanup
        assert "Session cleanup:" not in result.output

    @patch('cli.commands.org.cleanup.find_all_orphans')
    def test_dry_run_with_nothing_enabled(self, mock_find_orphans, runner, initialized_org):
        """Dry-run with both disabled should say nothing to clean."""
        mock_find_orphans.return_value = []

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--dry-run", "--no-notifications", "--no-sessions"
        ])

        assert result.exit_code == 0
        assert "Nothing to clean up" in result.output


class TestCleanupExecution:
    """Test actual cleanup execution."""

    @patch('cli.commands.org.cleanup.cleanup_orphaned_sessions')
    @patch('cli.commands.org.cleanup.run_notification_cleanup')
    def test_executes_both_cleanups(
        self, mock_notification_cleanup, mock_session_cleanup, runner, initialized_org
    ):
        """Should execute both notification and session cleanup."""
        mock_notification_cleanup.return_value = {
            'old_notifications_purged': 0,
            'expired_notifications_purged': 0,
            'orphaned_notifications_purged': 0,
            'total_purged': 0,
        }

        from core.sessions.cleanup import CleanupResult
        mock_session_cleanup.return_value = CleanupResult(
            orphaned_tmux_sessions=[],
            stale_db_records=[],
            tmux_sessions_killed=0,
            db_records_updated=0,
            db_records_deleted=0,
            errors=[],
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup"
        ])

        assert result.exit_code == 0
        mock_notification_cleanup.assert_called_once()
        mock_session_cleanup.assert_called_once()
        assert "Notification cleanup completed:" in result.output
        assert "Session cleanup completed:" in result.output

    @patch('cli.commands.org.cleanup.cleanup_orphaned_sessions')
    @patch('cli.commands.org.cleanup.run_notification_cleanup')
    def test_only_notifications(
        self, mock_notification_cleanup, mock_session_cleanup, runner, initialized_org
    ):
        """--no-sessions should only run notification cleanup."""
        mock_notification_cleanup.return_value = {
            'old_notifications_purged': 5,
            'expired_notifications_purged': 2,
            'orphaned_notifications_purged': 3,
            'total_purged': 10,
        }

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--no-sessions"
        ])

        assert result.exit_code == 0
        mock_notification_cleanup.assert_called_once()
        mock_session_cleanup.assert_not_called()
        assert "Total purged: 10" in result.output

    @patch('cli.commands.org.cleanup.cleanup_orphaned_sessions')
    @patch('cli.commands.org.cleanup.run_notification_cleanup')
    def test_only_sessions(
        self, mock_notification_cleanup, mock_session_cleanup, runner, initialized_org
    ):
        """--no-notifications should only run session cleanup."""
        from core.sessions.cleanup import CleanupResult
        mock_session_cleanup.return_value = CleanupResult(
            orphaned_tmux_sessions=["qn-worker-1", "qn-worker-2"],
            stale_db_records=["sess-1"],
            tmux_sessions_killed=2,
            db_records_updated=1,
            db_records_deleted=0,
            errors=[],
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--no-notifications"
        ])

        assert result.exit_code == 0
        mock_notification_cleanup.assert_not_called()
        mock_session_cleanup.assert_called_once()
        assert "Orphaned tmux sessions killed: 2" in result.output

    @patch('cli.commands.org.cleanup.cleanup_orphaned_sessions')
    @patch('cli.commands.org.cleanup.run_notification_cleanup')
    def test_delete_stale_sessions_flag(
        self, mock_notification_cleanup, mock_session_cleanup, runner, initialized_org
    ):
        """--delete-stale-sessions should pass delete_stale=True."""
        mock_notification_cleanup.return_value = {
            'old_notifications_purged': 0,
            'expired_notifications_purged': 0,
            'orphaned_notifications_purged': 0,
            'total_purged': 0,
        }

        from core.sessions.cleanup import CleanupResult
        mock_session_cleanup.return_value = CleanupResult(
            orphaned_tmux_sessions=[],
            stale_db_records=["sess-1", "sess-2", "sess-3"],
            tmux_sessions_killed=0,
            db_records_updated=0,
            db_records_deleted=3,
            errors=[],
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--delete-stale-sessions"
        ])

        assert result.exit_code == 0
        # Verify delete_stale was passed
        call_kwargs = mock_session_cleanup.call_args.kwargs
        assert call_kwargs.get('delete_stale') is True
        assert "Stale DB records deleted: 3" in result.output


class TestRetentionPeriod:
    """Test notification retention period filtering."""

    @patch('cli.commands.org.cleanup.cleanup_orphaned_sessions')
    @patch('cli.commands.org.cleanup.run_notification_cleanup')
    def test_custom_retention_days(
        self, mock_notification_cleanup, mock_session_cleanup, runner, initialized_org
    ):
        """--retention-days should be passed to cleanup."""
        mock_notification_cleanup.return_value = {
            'old_notifications_purged': 0,
            'expired_notifications_purged': 0,
            'orphaned_notifications_purged': 0,
            'total_purged': 0,
        }

        from core.sessions.cleanup import CleanupResult
        mock_session_cleanup.return_value = CleanupResult(
            orphaned_tmux_sessions=[],
            stale_db_records=[],
            tmux_sessions_killed=0,
            db_records_updated=0,
            db_records_deleted=0,
            errors=[],
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--retention-days", "7"
        ])

        assert result.exit_code == 0
        # Verify retention_days was passed
        call_args = mock_notification_cleanup.call_args
        assert call_args[1].get('retention_days') == 7 or call_args[0][1] == 7

    @patch('cli.commands.org.cleanup.find_all_orphans')
    def test_dry_run_shows_retention_days(self, mock_find_orphans, runner, initialized_org):
        """Dry-run should show the retention days in output."""
        mock_find_orphans.return_value = []

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--dry-run", "--retention-days", "14"
        ])

        assert result.exit_code == 0
        assert ">14 days" in result.output


class TestCleanupErrors:
    """Test cleanup error handling."""

    @patch('cli.commands.org.cleanup.cleanup_orphaned_sessions')
    @patch('cli.commands.org.cleanup.run_notification_cleanup')
    def test_shows_session_cleanup_errors(
        self, mock_notification_cleanup, mock_session_cleanup, runner, initialized_org
    ):
        """Should show errors from session cleanup."""
        mock_notification_cleanup.return_value = {
            'old_notifications_purged': 0,
            'expired_notifications_purged': 0,
            'orphaned_notifications_purged': 0,
            'total_purged': 0,
        }

        from core.sessions.cleanup import CleanupResult
        mock_session_cleanup.return_value = CleanupResult(
            orphaned_tmux_sessions=["qn-worker-123"],
            stale_db_records=[],
            tmux_sessions_killed=0,
            db_records_updated=0,
            db_records_deleted=0,
            errors=["Failed to kill session qn-worker-123: Permission denied"],
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup"
        ])

        assert result.exit_code == 0  # Still succeeds but shows errors
        assert "Errors encountered:" in result.output
        assert "Permission denied" in result.output


class TestCleanupIntegration:
    """Integration tests for cleanup with real database operations."""

    def test_cleanup_with_old_notifications(self, runner, initialized_org):
        """Should clean up old closed notifications."""
        # Add some old closed notifications to the database
        from core.db import open_database, get_org_db_path
        from core.org import Org

        db = open_database(get_org_db_path(initialized_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id

        # Create a channel first (type must be 'team', 'topic', or 'direct')
        channel_id = f"channel-{ceo_id}"
        db.execute(
            "INSERT INTO channels (id, name, type, team_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (channel_id, "general", "team", None, datetime.now())
        )

        # Create a message
        msg_id = "msg-test-old"
        db.execute(
            "INSERT INTO messages (id, channel_id, from_worker_id, content, priority, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, channel_id, ceo_id, "Test message", 2, datetime.now())
        )

        # Create an old closed notification (older than retention period)
        old_date = datetime.now() - timedelta(days=DEFAULT_NOTIFICATION_RETENTION_DAYS + 10)
        db.execute(
            """INSERT INTO notification_beads
               (id, worker_id, message_id, channel_id, status, priority, created_at, closed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("notif-old", ceo_id, msg_id, channel_id, "closed", 2, old_date, old_date)
        )
        db.connection.commit()

        # Verify notification exists
        count_before = db.fetchone("SELECT COUNT(*) as c FROM notification_beads")["c"]
        assert count_before > 0

        db.close()

        # Run cleanup
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--no-sessions"
        ])

        assert result.exit_code == 0
        assert "Old notifications purged:" in result.output

    @patch('cli.commands.org.cleanup.find_all_orphans')
    @patch('cli.commands.org.cleanup.cleanup_orphaned_sessions')
    def test_cleanup_with_orphaned_sessions(
        self, mock_cleanup, mock_find_orphans, runner, initialized_org
    ):
        """Should clean up orphaned sessions."""
        from core.sessions.cleanup import OrphanedSession, CleanupResult

        # Mock finding orphaned sessions
        mock_find_orphans.return_value = [
            OrphanedSession(session_name="qn-worker-orphan", source="tmux"),
        ]
        mock_cleanup.return_value = CleanupResult(
            orphaned_tmux_sessions=["qn-worker-orphan"],
            stale_db_records=[],
            tmux_sessions_killed=1,
            db_records_updated=0,
            db_records_deleted=0,
            errors=[],
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--no-notifications"
        ])

        assert result.exit_code == 0
        assert "Orphaned tmux sessions killed: 1" in result.output
