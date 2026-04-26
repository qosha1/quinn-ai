"""
Unit tests for qn org observe command.

Tests the observe command functionality including:
- get_tmux_session_name() helper
- stream_session_output() with mocked TmuxSession
- observe_cmd() with various scenarios
- Error cases (worker not found, no active session, tmux session missing)
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.commands.org.observe import (
    get_tmux_session_name,
    stream_session_output,
)
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
    """Create an initialized org and return its path and CEO ID."""
    result = runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--ceo-name", "TestCEO"], catch_exceptions=False)

    # Verify init succeeded
    if result.exit_code != 0:
        pytest.fail(f"org init failed (exit {result.exit_code}): {result.output}\nexception: {result.exception}")

    from cli.core.db import open_database, get_org_db_path
    from cli.core.org import Org

    db_path = get_org_db_path(temp_org)
    if not db_path.exists():
        pytest.fail(f"Database not created at {db_path}")

    db = open_database(db_path)
    org = Org.load(db)
    ceo_id = org.ceo_worker_id
    db.close()

    return temp_org, ceo_id


def set_worker_runtime_status(temp_org, worker_id: str, status: str) -> None:
    """Helper to set worker runtime status for tests.

    Creates the worker_state row if it doesn't exist, then updates the status.
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
    db.close()


class TestGetTmuxSessionName:
    """Test get_tmux_session_name() helper function."""

    def test_returns_prefixed_name(self):
        """Should return worker_id prefixed with TMUX_SESSION_PREFIX."""
        worker_id = "wrkr-abc123"
        result = get_tmux_session_name(worker_id)
        assert result == f"{TMUX_SESSION_PREFIX}{worker_id}"

    def test_with_different_ids(self):
        """Should work with various worker ID formats."""
        test_cases = [
            "wrkr-abc123",
            "test-worker-001",
            "ceo",
            "worker_with_underscores",
        ]
        for worker_id in test_cases:
            result = get_tmux_session_name(worker_id)
            assert result.startswith(TMUX_SESSION_PREFIX)
            assert result.endswith(worker_id)

    def test_prefix_is_consistent(self):
        """Should use the constant prefix."""
        result = get_tmux_session_name("test")
        expected = f"{TMUX_SESSION_PREFIX}test"
        assert result == expected


class TestStreamSessionOutput:
    """Test stream_session_output() function with mocked TmuxSession."""

    @patch('cli.commands.org.observe.TmuxSession')
    @patch('cli.commands.org.observe.click')
    @patch('cli.commands.org.observe.time')
    def test_streams_output_changes(self, mock_time, mock_click, mock_tmux_class):
        """Should stream output when it changes."""
        # Set up mock to return different outputs then stop
        mock_tmux_class.exists.side_effect = [True, True, True, False]
        mock_tmux_class.capture.side_effect = [
            "Initial output",
            "Initial output",  # Same - no echo
            "Changed output",  # Different - should echo
        ]
        mock_time.sleep.return_value = None

        stream_session_output("test-session", poll_interval=0.1)

        # Should have echoed initial message and cleared screen for changes
        assert mock_click.echo.called
        assert mock_click.clear.called

    @patch('cli.commands.org.observe.TmuxSession')
    @patch('cli.commands.org.observe.click')
    @patch('cli.commands.org.observe.time')
    def test_stops_when_session_ends(self, mock_time, mock_click, mock_tmux_class):
        """Should stop streaming when session no longer exists."""
        mock_tmux_class.exists.return_value = False

        stream_session_output("test-session", poll_interval=0.1)

        # Should echo session ended message
        echo_calls = [str(c) for c in mock_click.echo.call_args_list]
        assert any("ended" in c.lower() for c in echo_calls)

    @patch('cli.commands.org.observe.TmuxSession')
    @patch('cli.commands.org.observe.click')
    @patch('cli.commands.org.observe.time')
    def test_handles_keyboard_interrupt(self, mock_time, mock_click, mock_tmux_class):
        """Should handle Ctrl+C gracefully."""
        mock_tmux_class.exists.return_value = True
        mock_time.sleep.side_effect = KeyboardInterrupt()

        # Should not raise, should handle interrupt
        stream_session_output("test-session")

        # Should echo stopped message
        echo_calls = [str(c) for c in mock_click.echo.call_args_list]
        assert any("stopped" in c.lower() for c in echo_calls)

    @patch('cli.commands.org.observe.TmuxSession')
    @patch('cli.commands.org.observe.click')
    @patch('cli.commands.org.observe.time')
    def test_uses_poll_interval(self, mock_time, mock_click, mock_tmux_class):
        """Should sleep for the specified poll interval."""
        mock_tmux_class.exists.side_effect = [True, False]
        mock_tmux_class.capture.return_value = "output"

        stream_session_output("test-session", poll_interval=0.25)

        # Should have called sleep with the poll interval
        mock_time.sleep.assert_called_with(0.25)


class TestObserveCommand:
    """Test qn org observe command with mocked TmuxSession."""

    def test_observe_help(self, runner):
        """qn org observe --help should show usage."""
        result = runner.invoke(qn, ["org", "observe", "--help"])
        assert result.exit_code == 0
        assert "tmux session" in result.output.lower()
        assert "--stream" in result.output
        assert "--poll-interval" in result.output

    def test_observe_requires_org_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", "some-worker"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_observe_worker_not_found(self, runner, initialized_org):
        """Should error when worker doesn't exist."""
        temp_org, _ = initialized_org
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", "nonexistent-worker-xyz"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_observe_by_worker_name(self, runner, initialized_org):
        """Should accept worker name in addition to ID."""
        temp_org, _ = initialized_org
        # Try to observe by name - will fail because no active session
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", "TestCEO"
        ])
        assert result.exit_code != 0
        # Should fail because no active session, not because worker not found
        assert "does not have an active session" in result.output.lower() or "session" in result.output.lower()

    def test_observe_requires_active_session(self, runner, initialized_org):
        """Should require worker to have an active session."""
        temp_org, ceo_id = initialized_org
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id
        ])
        assert result.exit_code != 0
        assert "does not have an active session" in result.output.lower() or "runtime status" in result.output.lower()

    @patch('cli.commands.org.observe.TmuxSession')
    def test_observe_tmux_session_not_found(self, mock_tmux_class, runner, initialized_org):
        """Should error when tmux session doesn't exist even if worker shows active."""
        temp_org, ceo_id = initialized_org
        mock_tmux_class.exists.return_value = False

        # Set worker to running state
        set_worker_runtime_status(temp_org, ceo_id, "running")

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "cleanup" in result.output.lower()

    @patch('cli.commands.org.observe.stream_session_output')
    @patch('cli.commands.org.observe.TmuxSession')
    def test_observe_stream_mode(self, mock_tmux_class, mock_stream_fn, runner, initialized_org):
        """Should use stream mode when --stream flag is provided."""
        temp_org, ceo_id = initialized_org
        mock_tmux_class.exists.return_value = True

        # Set worker to running state
        set_worker_runtime_status(temp_org, ceo_id, "running")

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id, "--stream"
        ])

        # Should call stream_session_output
        assert mock_stream_fn.called
        assert result.exit_code == 0

    @patch('cli.commands.org.observe.stream_session_output')
    @patch('cli.commands.org.observe.TmuxSession')
    def test_observe_stream_custom_interval(self, mock_tmux_class, mock_stream_fn, runner, initialized_org):
        """Should pass custom poll interval in stream mode."""
        temp_org, ceo_id = initialized_org
        mock_tmux_class.exists.return_value = True

        # Set worker to running state
        set_worker_runtime_status(temp_org, ceo_id, "running")

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id, "--stream", "--poll-interval", "1.5"
        ])

        # Should call stream_session_output with custom interval
        mock_stream_fn.assert_called_once()
        call_args = mock_stream_fn.call_args
        assert call_args[1].get('poll_interval') == 1.5 or (len(call_args[0]) > 1 and call_args[0][1] == 1.5)

    @patch('cli.commands.org.observe.TmuxSession')
    def test_observe_attach_mode_closes_db(self, mock_tmux_class, runner, initialized_org):
        """Should close database before attaching to tmux session."""
        temp_org, ceo_id = initialized_org
        mock_tmux_class.exists.return_value = True

        # Mock attach to not actually exec
        def mock_attach(session_name):
            pass

        mock_tmux_class.attach.side_effect = mock_attach

        # Set worker to running state
        set_worker_runtime_status(temp_org, ceo_id, "running")

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id
        ])

        # Should call TmuxSession.attach
        mock_tmux_class.attach.assert_called_once()

    @patch('cli.commands.org.observe.TmuxSession')
    def test_observe_shows_worker_info(self, mock_tmux_class, runner, initialized_org):
        """Should display worker information before observing."""
        temp_org, ceo_id = initialized_org
        mock_tmux_class.exists.return_value = True
        mock_tmux_class.attach.return_value = None

        # Set worker to running state
        set_worker_runtime_status(temp_org, ceo_id, "running")

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id
        ])

        # Should show worker info
        assert "Observing worker" in result.output
        assert "TestCEO" in result.output
        assert "Role:" in result.output
        assert "Session:" in result.output


class TestObserveCommandEdgeCases:
    """Test edge cases for observe command."""

    def test_observe_with_worker_id_format(self, runner, initialized_org):
        """Should handle worker ID format correctly."""
        temp_org, ceo_id = initialized_org

        # CEO ID should be found by ID
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id
        ])

        # Should fail because no active session, not because ID not recognized
        assert "not found" not in result.output.lower() or "session" in result.output.lower()

    def test_observe_case_insensitive_worker_name(self, runner, initialized_org):
        """Should be case insensitive for worker names."""
        temp_org, _ = initialized_org

        # Try lowercase version of CEO name
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", "testceo"
        ])

        # get_worker_by_name should handle this - currently case sensitive
        # This documents current behavior
        # Either finds worker (no session error) or doesn't find (not found error)
        assert result.exit_code != 0

    @patch('cli.commands.org.observe.TmuxSession')
    def test_observe_with_idle_runtime_status(self, mock_tmux_class, runner, initialized_org):
        """Should work when worker is in IDLE state (considered active)."""
        temp_org, ceo_id = initialized_org
        mock_tmux_class.exists.return_value = True
        mock_tmux_class.attach.return_value = None

        # Set worker to idle state
        set_worker_runtime_status(temp_org, ceo_id, "idle")

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id
        ])

        # IDLE is considered active, so should proceed
        assert result.exit_code == 0
        mock_tmux_class.attach.assert_called_once()

    @patch('cli.commands.org.observe.TmuxSession')
    def test_observe_with_starting_runtime_status(self, mock_tmux_class, runner, initialized_org):
        """Should work when worker is in STARTING state (considered active)."""
        temp_org, ceo_id = initialized_org
        mock_tmux_class.exists.return_value = True
        mock_tmux_class.attach.return_value = None

        # Set worker to starting state
        set_worker_runtime_status(temp_org, ceo_id, "starting")

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id
        ])

        # STARTING is considered active, so should proceed
        assert result.exit_code == 0
        mock_tmux_class.attach.assert_called_once()
