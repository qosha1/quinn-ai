"""
Unit tests for qn org logs command.

Tests the logs command CLI including:
- Worker lookup by name and ID
- Line limiting with -n option
- Follow mode behavior
- Error cases (worker not found, no active session)
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.core.constants import TMUX_SESSION_PREFIX


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


def get_ceo_worker_id(temp_org: Path) -> str:
    """Get the CEO worker ID from an initialized org."""
    from cli.core.db import open_database, get_org_db_path
    from cli.core.org import Org

    db = open_database(get_org_db_path(temp_org))
    org = Org.load(db)
    ceo_id = org.ceo_worker_id
    db.close()
    return ceo_id


def set_worker_runtime_status(temp_org: Path, worker_id: str, status: str) -> None:
    """Helper to set worker runtime status for tests.

    Also inserts a sessions row for the worker. session_manager auto-repairs
    'state shows running but no session exists' by resetting to 'stopped',
    so without the sessions row these tests fail with the worker reverted.
    """
    from cli.core.db import open_database, get_org_db_path
    from cli.core.queries import (
        update_worker_runtime_status,
        get_worker_state,
        create_worker_state,
    )

    db = open_database(get_org_db_path(temp_org))
    # Create worker_state row if it doesn't exist
    if get_worker_state(db, worker_id) is None:
        create_worker_state(db, worker_id)
    update_worker_runtime_status(db, worker_id, status)

    # Insert a sessions row matching the runtime status so the auto-repair
    # in cli/core/worker/session_manager.py (line ~105) doesn't kick in.
    from cli.core.constants import TMUX_SESSION_PREFIX
    session_state = status if status in ("starting", "running", "idle", "stopped", "crashed") else "running"
    db.execute(
        """INSERT OR REPLACE INTO sessions
           (id, worker_id, provider, command, tmux_session_name, state,
            state_version, started_at, last_activity)
           VALUES (?, ?, 'claude_code', 'claude', ?, ?, 0,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (f"sess-{worker_id}", worker_id, f"{TMUX_SESSION_PREFIX}{worker_id}", session_state),
    )
    db.connection.commit()
    db.close()


class TestLogsCommandHelp:
    """Test logs command help and arguments."""

    def test_logs_help(self, runner):
        """qn org logs --help should show usage."""
        result = runner.invoke(qn, ["org", "logs", "--help"])
        assert result.exit_code == 0
        assert "WORKER" in result.output
        assert "--lines" in result.output or "-n" in result.output
        assert "--follow" in result.output or "-f" in result.output

    def test_logs_requires_worker_arg(self, runner, initialized_org):
        """logs command should require worker argument."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs"
        ])
        # Click exits with 2 for missing required args
        assert result.exit_code == 2
        assert "Missing argument" in result.output

    def test_logs_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "logs", "SomeWorker"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestGetTmuxSessionName:
    """Test the get_tmux_session_name helper function."""

    def test_session_name_format(self):
        """Should format session name with prefix."""
        from cli.commands.org.logs import get_tmux_session_name

        result = get_tmux_session_name("wrkr-abc123")
        assert result == f"{TMUX_SESSION_PREFIX}wrkr-abc123"

    def test_session_name_with_different_ids(self):
        """Should work with various worker IDs."""
        from cli.commands.org.logs import get_tmux_session_name

        assert get_tmux_session_name("wrkr-001").startswith(TMUX_SESSION_PREFIX)
        assert get_tmux_session_name("wrkr-test").startswith(TMUX_SESSION_PREFIX)


class TestSessionExists:
    """Test the session_exists helper function."""

    @patch('cli.commands.org.logs.subprocess.run')
    def test_session_exists_returns_true(self, mock_run):
        """Should return True when tmux session exists."""
        from cli.commands.org.logs import session_exists

        mock_run.return_value = MagicMock(returncode=0)

        result = session_exists("test-session")

        assert result is True
        mock_run.assert_called_once_with(
            ["tmux", "has-session", "-t", "test-session"],
            capture_output=True,
            text=True,
        )

    @patch('cli.commands.org.logs.subprocess.run')
    def test_session_exists_returns_false(self, mock_run):
        """Should return False when tmux session does not exist."""
        from cli.commands.org.logs import session_exists

        mock_run.return_value = MagicMock(returncode=1)

        result = session_exists("nonexistent")

        assert result is False


class TestCaptureTmuxScrollback:
    """Test the capture_tmux_scrollback function."""

    @patch('cli.commands.org.logs.session_exists')
    def test_raises_when_session_not_found(self, mock_exists):
        """Should raise ClickException when session doesn't exist."""
        from cli.commands.org.logs import capture_tmux_scrollback
        import click

        mock_exists.return_value = False

        with pytest.raises(click.ClickException) as exc_info:
            capture_tmux_scrollback("nonexistent-session")

        assert "No active session found" in str(exc_info.value)
        assert "nonexistent-session" in str(exc_info.value)

    @patch('cli.commands.org.logs.subprocess.run')
    @patch('cli.commands.org.logs.session_exists')
    def test_captures_all_output(self, mock_exists, mock_run):
        """Should capture all scrollback when lines is None."""
        from cli.commands.org.logs import capture_tmux_scrollback

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="line1\nline2\nline3\n"
        )

        result = capture_tmux_scrollback("test-session")

        assert result == "line1\nline2\nline3\n"
        # Verify capture-pane command was used
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "capture-pane" in cmd

    @patch('cli.commands.org.logs.subprocess.run')
    @patch('cli.commands.org.logs.session_exists')
    def test_limits_to_last_n_lines(self, mock_exists, mock_run):
        """Should limit output to last N lines when specified."""
        from cli.commands.org.logs import capture_tmux_scrollback

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="line1\nline2\nline3\nline4\nline5\n"
        )

        result = capture_tmux_scrollback("test-session", lines=2)

        # Should only have last 2 lines
        assert result == "line4\nline5\n"

    @patch('cli.commands.org.logs.subprocess.run')
    @patch('cli.commands.org.logs.session_exists')
    def test_handles_fewer_lines_than_limit(self, mock_exists, mock_run):
        """Should handle when output has fewer lines than limit."""
        from cli.commands.org.logs import capture_tmux_scrollback

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="line1\nline2\n"
        )

        result = capture_tmux_scrollback("test-session", lines=100)

        # Should return all lines since fewer than limit
        assert result == "line1\nline2\n"

    @patch('cli.commands.org.logs.subprocess.run')
    @patch('cli.commands.org.logs.session_exists')
    def test_raises_on_capture_failure(self, mock_exists, mock_run):
        """Should raise ClickException when capture fails."""
        from cli.commands.org.logs import capture_tmux_scrollback
        import click

        mock_exists.return_value = True
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Error capturing pane"
        )

        with pytest.raises(click.ClickException) as exc_info:
            capture_tmux_scrollback("test-session")

        assert "Failed to capture" in str(exc_info.value)


class TestLogsCommandWorkerLookup:
    """Test worker lookup by name and ID."""

    def test_worker_not_found_by_name(self, runner, initialized_org):
        """Should fail when worker name not found."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "NonexistentWorker"
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_worker_not_found_by_id(self, runner, initialized_org):
        """Should fail when worker ID not found."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "wrkr-fake123"
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_worker_found_by_name_no_session(self, runner, initialized_org):
        """Should fail when worker exists but has no active session."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO"
        ])

        assert result.exit_code != 0
        assert "does not have an active session" in result.output

    def test_worker_found_by_id_no_session(self, runner, initialized_org):
        """Should fail when worker exists by ID but has no active session."""
        ceo_id = get_ceo_worker_id(initialized_org)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", ceo_id
        ])

        assert result.exit_code != 0
        assert "does not have an active session" in result.output


class TestLogsCommandWithSession:
    """Test logs command when worker has active session."""

    @patch('cli.commands.org.logs.capture_tmux_scrollback')
    def test_displays_output(self, mock_capture, runner, initialized_org):
        """Should display captured output."""
        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "running")
        mock_capture.return_value = "Hello from session\nLine 2\n"

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO"
        ])

        assert result.exit_code == 0
        assert "Hello from session" in result.output
        assert "Line 2" in result.output

    @patch('cli.commands.org.logs.capture_tmux_scrollback')
    def test_line_limit_passed_to_capture(self, mock_capture, runner, initialized_org):
        """Should pass -n lines option to capture function."""
        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "running")
        mock_capture.return_value = "Last line\n"

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO", "-n", "50"
        ])

        assert result.exit_code == 0
        # Verify lines parameter was passed
        mock_capture.assert_called_once()
        call_args = mock_capture.call_args
        assert call_args[0][1] == 50 or call_args[1].get('lines') == 50

    @patch('cli.commands.org.logs.capture_tmux_scrollback')
    def test_shows_no_output_message(self, mock_capture, runner, initialized_org):
        """Should show message when no output captured."""
        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "running")
        mock_capture.return_value = ""

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO"
        ])

        assert result.exit_code == 0
        assert "No output captured" in result.output

    @patch('cli.commands.org.logs.capture_tmux_scrollback')
    def test_shows_no_output_for_whitespace_only(self, mock_capture, runner, initialized_org):
        """Should show no output message for whitespace-only content."""
        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "running")
        mock_capture.return_value = "   \n\n  \n"

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO"
        ])

        assert result.exit_code == 0
        assert "No output captured" in result.output

    @patch('cli.commands.org.logs.capture_tmux_scrollback')
    def test_works_with_worker_id(self, mock_capture, runner, initialized_org):
        """Should work when using worker ID instead of name."""
        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "running")
        mock_capture.return_value = "Session output\n"

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", ceo_id
        ])

        assert result.exit_code == 0
        assert "Session output" in result.output


class TestLogsFollowMode:
    """Test follow mode (-f) behavior."""

    @patch('cli.commands.org.logs.time.sleep')
    @patch('cli.commands.org.logs.capture_tmux_scrollback')
    def test_follow_streams_new_lines(self, mock_capture, mock_sleep, runner, initialized_org):
        """Follow mode should stream only new lines."""
        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "running")

        # Simulate output growing over time
        call_count = [0]

        def capture_side_effect(session_name):
            call_count[0] += 1
            if call_count[0] == 1:
                return "line1\n"
            elif call_count[0] == 2:
                return "line1\nline2\n"
            elif call_count[0] == 3:
                # Raise KeyboardInterrupt to exit loop
                raise KeyboardInterrupt()
            return "line1\nline2\n"

        mock_capture.side_effect = capture_side_effect

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO", "-f"
        ])

        # Should exit cleanly on KeyboardInterrupt
        assert result.exit_code == 0
        # First call outputs line1, second call outputs line2
        assert "line1" in result.output
        assert "line2" in result.output

    @patch('cli.commands.org.logs.capture_tmux_scrollback')
    def test_follow_exits_on_interrupt(self, mock_capture, runner, initialized_org):
        """Follow mode should exit gracefully on KeyboardInterrupt."""
        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "running")

        mock_capture.side_effect = KeyboardInterrupt()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO", "-f"
        ])

        # Should exit with 0 (graceful exit)
        assert result.exit_code == 0


class TestLogsCommandErrors:
    """Test error handling in logs command."""

    @patch('cli.commands.org.logs.capture_tmux_scrollback')
    def test_handles_capture_error(self, mock_capture, runner, initialized_org):
        """Should handle errors from capture_tmux_scrollback."""
        import click

        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "running")
        mock_capture.side_effect = click.ClickException("Session not found")

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO"
        ])

        assert result.exit_code != 0
        assert "Session not found" in result.output

    def test_handles_inactive_session_status(self, runner, initialized_org):
        """Should handle worker with stopped status."""
        ceo_id = get_ceo_worker_id(initialized_org)
        set_worker_runtime_status(initialized_org, ceo_id, "stopped")

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "TestCEO"
        ])

        assert result.exit_code != 0
        assert "does not have an active session" in result.output
        assert "stopped" in result.output.lower()
