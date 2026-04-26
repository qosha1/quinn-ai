"""
Tests for TmuxSpawner.

Tests tmux-based session spawning, lifecycle management, and I/O operations.
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

from cli.core.sessions.spawner import SpawnerConfig, SpawnFailedError
from cli.core.sessions.tmux_spawner import TmuxSpawner
from cli.core.constants import TMUX_SESSION_PREFIX


@pytest.fixture
def tmux_spawner():
    """Create a TmuxSpawner for testing."""
    with patch.object(TmuxSpawner, "_find_tmux", return_value="/usr/bin/tmux"):
        spawner = TmuxSpawner()
        yield spawner


@pytest.fixture
def spawner_config():
    """Create a basic spawner config."""
    return SpawnerConfig(
        command="claude",
        args=["--dangerously-skip-permissions"],
        working_directory=Path("/tmp/test"),
        worker_id="worker-123",
        cols=120,
        rows=40,
        env_vars={"TEST_VAR": "test_value"},
    )


class TestTmuxSpawnerInit:
    """Tests for TmuxSpawner initialization."""

    def test_init_default(self):
        """Should initialize with default settings."""
        with patch.object(TmuxSpawner, "_find_tmux", return_value="/usr/bin/tmux"):
            spawner = TmuxSpawner()

            assert spawner.name == "tmux"
            assert spawner._socket_path is None
            assert spawner._tmux_cmd == "/usr/bin/tmux"

    def test_init_with_socket_path(self):
        """Should initialize with custom socket path."""
        socket_path = Path("/tmp/custom-tmux.socket")
        with patch.object(TmuxSpawner, "_find_tmux", return_value="/usr/bin/tmux"):
            spawner = TmuxSpawner(socket_path=socket_path)

            assert spawner._socket_path == socket_path

    def test_init_tmux_not_found(self):
        """Should handle tmux not found."""
        with patch("shutil.which", return_value=None):
            spawner = TmuxSpawner()

            assert spawner._tmux_cmd is None


class TestTmuxSpawnerSpawn:
    """Tests for spawning tmux sessions."""

    @patch("subprocess.run")
    def test_spawn_success(self, mock_run, tmux_spawner, spawner_config):
        """Should spawn tmux session successfully."""
        # Mock has-session (session doesn't exist)
        has_session_result = Mock(returncode=1)
        # Mock set-environment (for TEST_VAR)
        set_env_result = Mock(returncode=0)
        # Mock new-session success
        new_session_result = Mock(returncode=0)
        # Mock list-panes for PID
        list_panes_result = Mock(returncode=0, stdout="12345\n")

        mock_run.side_effect = [
            has_session_result,
            set_env_result,
            new_session_result,
            list_panes_result,
        ]

        result = tmux_spawner.spawn(spawner_config)

        assert result.success
        assert result.pid == 12345
        assert result.session_id == f"{TMUX_SESSION_PREFIX}worker-123"
        assert result.metadata["strategy"] == "tmux"

    @patch("subprocess.run")
    def test_spawn_with_custom_session_name(self, mock_run, tmux_spawner):
        """Should use custom session name if provided."""
        config = SpawnerConfig(
            command="claude",
            session_name="custom-session",
        )

        has_session_result = Mock(returncode=1)
        new_session_result = Mock(returncode=0)
        list_panes_result = Mock(returncode=0, stdout="12345\n")

        mock_run.side_effect = [
            has_session_result,
            new_session_result,
            list_panes_result,
        ]

        result = tmux_spawner.spawn(config)

        assert result.success
        assert result.session_id == "custom-session"

    @patch("subprocess.run")
    def test_spawn_session_already_exists(self, mock_run, tmux_spawner, spawner_config):
        """Should fail when session already exists."""
        # Mock has-session returns 0 (exists)
        has_session_result = Mock(returncode=0)
        mock_run.return_value = has_session_result

        result = tmux_spawner.spawn(spawner_config)

        assert not result.success
        assert "already exists" in result.error

    @patch("subprocess.run")
    def test_spawn_new_session_fails(self, mock_run, tmux_spawner, spawner_config):
        """Should handle new-session failure."""
        has_session_result = Mock(returncode=1)
        # Mock set-environment (for TEST_VAR)
        set_env_result = Mock(returncode=0)
        new_session_result = Mock(returncode=1, stderr="tmux error")

        mock_run.side_effect = [has_session_result, set_env_result, new_session_result]

        result = tmux_spawner.spawn(spawner_config)

        assert not result.success
        assert "failed" in result.error

    @patch("subprocess.run")
    def test_spawn_timeout(self, mock_run, tmux_spawner, spawner_config):
        """Should handle timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired("tmux", 10)

        result = tmux_spawner.spawn(spawner_config)

        assert not result.success
        assert "timed out" in result.error

    @patch("subprocess.run")
    def test_spawn_subprocess_error(self, mock_run, tmux_spawner, spawner_config):
        """Should handle subprocess errors."""
        mock_run.side_effect = subprocess.SubprocessError("spawn failed")

        result = tmux_spawner.spawn(spawner_config)

        assert not result.success
        assert result.error is not None

    def test_spawn_tmux_not_found(self, spawner_config):
        """Should fail when tmux not found."""
        with patch("shutil.which", return_value=None):
            spawner = TmuxSpawner()
            result = spawner.spawn(spawner_config)

            assert not result.success
            assert "not found" in result.error

    @patch("subprocess.run")
    def test_spawn_with_env_vars(self, mock_run, tmux_spawner, spawner_config):
        """Should set environment variables."""
        has_session_result = Mock(returncode=1)
        set_env_result = Mock(returncode=0)
        new_session_result = Mock(returncode=0)
        list_panes_result = Mock(returncode=0, stdout="12345\n")

        mock_run.side_effect = [
            has_session_result,
            set_env_result,  # set-environment call
            new_session_result,
            list_panes_result,
        ]

        result = tmux_spawner.spawn(spawner_config)

        assert result.success
        # Verify set-environment was called
        env_calls = [c for c in mock_run.call_args_list if "set-environment" in str(c)]
        assert len(env_calls) > 0

    @patch("subprocess.run")
    def test_spawn_pid_extraction_failure(self, mock_run, tmux_spawner, spawner_config):
        """Should handle PID extraction failure gracefully."""
        has_session_result = Mock(returncode=1)
        # Mock set-environment (for TEST_VAR)
        set_env_result = Mock(returncode=0)
        new_session_result = Mock(returncode=0)
        list_panes_result = Mock(returncode=1, stdout="")  # PID extraction fails

        mock_run.side_effect = [
            has_session_result,
            set_env_result,
            new_session_result,
            list_panes_result,
        ]

        result = tmux_spawner.spawn(spawner_config)

        assert result.success
        assert result.pid is None


class TestTmuxSpawnerStop:
    """Tests for stopping tmux sessions."""

    @patch("subprocess.run")
    @patch("time.sleep")
    def test_stop_graceful(self, mock_sleep, mock_run, tmux_spawner):
        """Should stop session gracefully."""
        send_keys_result = Mock(returncode=0)
        kill_result = Mock(returncode=0)

        mock_run.side_effect = [send_keys_result, kill_result]

        result = tmux_spawner.stop(f"{TMUX_SESSION_PREFIX}worker-1", force=False)

        assert result
        # Should send Ctrl+C first
        first_call = mock_run.call_args_list[0][0][0]
        assert "send-keys" in first_call
        assert f"{TMUX_SESSION_PREFIX}worker-1" in first_call
        assert "C-c" in first_call
        # Then kill
        assert "kill-session" in mock_run.call_args_list[1][0][0]

    @patch("subprocess.run")
    def test_stop_force(self, mock_run, tmux_spawner):
        """Should kill session immediately when force=True."""
        kill_result = Mock(returncode=0)
        mock_run.return_value = kill_result

        result = tmux_spawner.stop(f"{TMUX_SESSION_PREFIX}worker-1", force=True)

        assert result
        # Should only call kill-session
        assert mock_run.call_count == 1
        assert "kill-session" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_stop_failure(self, mock_run, tmux_spawner):
        """Should return False on failure."""
        mock_run.return_value = Mock(returncode=1)

        result = tmux_spawner.stop(f"{TMUX_SESSION_PREFIX}worker-1", force=True)

        assert not result

    @patch("subprocess.run")
    def test_stop_subprocess_error(self, mock_run, tmux_spawner):
        """Should handle subprocess errors."""
        mock_run.side_effect = subprocess.SubprocessError("error")

        result = tmux_spawner.stop(f"{TMUX_SESSION_PREFIX}worker-1")

        assert not result

    @patch("subprocess.run")
    def test_stop_refuses_non_prefixed_session(self, mock_run, tmux_spawner):
        """Should refuse to kill sessions without the QuinnAI prefix.

        This guards against accidentally killing the board's own tmux session
        or any other non-worker session.
        """
        result = tmux_spawner.stop("quinnai-board", force=True)

        assert not result
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_stop_refuses_bare_session_name(self, mock_run, tmux_spawner):
        """Should refuse to kill sessions with no prefix at all."""
        result = tmux_spawner.stop("my-session", force=True)

        assert not result
        mock_run.assert_not_called()


class TestTmuxSpawnerIsAlive:
    """Tests for checking session status."""

    @patch("subprocess.run")
    def test_is_alive_true(self, mock_run, tmux_spawner):
        """Should return True when session exists."""
        mock_run.return_value = Mock(returncode=0)

        result = tmux_spawner.is_alive("test-session")

        assert result
        assert "has-session" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_is_alive_false(self, mock_run, tmux_spawner):
        """Should return False when session doesn't exist."""
        mock_run.return_value = Mock(returncode=1)

        result = tmux_spawner.is_alive("test-session")

        assert not result

    @patch("subprocess.run")
    def test_is_alive_error(self, mock_run, tmux_spawner):
        """Should return False on error."""
        mock_run.side_effect = OSError("error")

        result = tmux_spawner.is_alive("test-session")

        assert not result


class TestTmuxSpawnerIO:
    """Tests for I/O operations."""

    @patch("subprocess.run")
    def test_send_input_success(self, mock_run, tmux_spawner):
        """Should send input to session."""
        mock_run.return_value = Mock(returncode=0)

        result = tmux_spawner.send_input("test-session", "Hello!\n")

        assert result
        assert "send-keys" in mock_run.call_args[0][0]
        assert "Hello!\n" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_send_input_failure(self, mock_run, tmux_spawner):
        """Should return False on failure."""
        mock_run.return_value = Mock(returncode=1)

        result = tmux_spawner.send_input("test-session", "text")

        assert not result

    @patch("subprocess.run")
    def test_send_input_error(self, mock_run, tmux_spawner):
        """Should handle errors."""
        mock_run.side_effect = OSError("error")

        result = tmux_spawner.send_input("test-session", "text")

        assert not result

    @patch("subprocess.run")
    def test_read_output_success(self, mock_run, tmux_spawner):
        """Should read output from session."""
        mock_run.return_value = Mock(returncode=0, stdout="output text")

        result = tmux_spawner.read_output("test-session")

        assert result == "output text"
        assert "capture-pane" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_read_output_timeout_ignored(self, mock_run, tmux_spawner):
        """Should ignore timeout parameter (capture is instant)."""
        mock_run.return_value = Mock(returncode=0, stdout="output")

        result = tmux_spawner.read_output("test-session", timeout_ms=5000)

        assert result == "output"

    @patch("subprocess.run")
    def test_read_output_failure(self, mock_run, tmux_spawner):
        """Should return empty string on failure."""
        mock_run.return_value = Mock(returncode=1)

        result = tmux_spawner.read_output("test-session")

        assert result == ""

    @patch("subprocess.run")
    def test_read_output_error(self, mock_run, tmux_spawner):
        """Should handle errors."""
        mock_run.side_effect = OSError("error")

        result = tmux_spawner.read_output("test-session")

        assert result == ""


class TestTmuxSpawnerAttach:
    """Tests for attaching to sessions."""

    @patch("subprocess.run")
    def test_attach_success(self, mock_run, tmux_spawner):
        """Should attach to session."""
        result = tmux_spawner.attach("test-session")

        assert result
        assert "attach-session" in mock_run.call_args[0][0]
        # check=True means it raises on error
        assert mock_run.call_args[1]["check"]

    @patch("subprocess.run")
    def test_attach_failure(self, mock_run, tmux_spawner):
        """Should return False on failure."""
        mock_run.side_effect = subprocess.SubprocessError("error")

        result = tmux_spawner.attach("test-session")

        assert not result

    def test_attach_no_tmux(self):
        """Should return False when tmux not found."""
        with patch("shutil.which", return_value=None):
            spawner = TmuxSpawner()
            result = spawner.attach("test-session")

            assert not result


class TestTmuxSpawnerSignal:
    """Tests for sending signals."""

    @patch("subprocess.run")
    @patch("os.kill")
    def test_send_signal_success(self, mock_kill, mock_run, tmux_spawner):
        """Should send signal to session process."""
        mock_run.return_value = Mock(returncode=0, stdout="12345\n")

        result = tmux_spawner.send_signal("test-session", 2)  # SIGINT

        assert result
        mock_kill.assert_called_once_with(12345, 2)

    @patch("subprocess.run")
    def test_send_signal_no_pid(self, mock_run, tmux_spawner):
        """Should return False when PID not available."""
        mock_run.return_value = Mock(returncode=1, stdout="")

        result = tmux_spawner.send_signal("test-session", 2)

        assert not result

    @patch("subprocess.run")
    @patch("os.kill")
    def test_send_signal_os_error(self, mock_kill, mock_run, tmux_spawner):
        """Should handle os.kill errors."""
        mock_run.return_value = Mock(returncode=0, stdout="12345\n")
        mock_kill.side_effect = OSError("error")

        result = tmux_spawner.send_signal("test-session", 2)

        assert not result


class TestTmuxSpawnerListSessions:
    """Tests for listing sessions."""

    @patch("subprocess.run")
    def test_list_sessions_success(self, mock_run, tmux_spawner):
        """Should list all tmux sessions."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="session1\nsession2\nsession3\n",
        )

        result = tmux_spawner.list_sessions()

        assert result == ["session1", "session2", "session3"]

    @patch("subprocess.run")
    def test_list_sessions_empty(self, mock_run, tmux_spawner):
        """Should return empty list when no sessions."""
        mock_run.return_value = Mock(returncode=1, stdout="")

        result = tmux_spawner.list_sessions()

        assert result == []

    @patch("subprocess.run")
    def test_list_sessions_error(self, mock_run, tmux_spawner):
        """Should return empty list on error."""
        mock_run.side_effect = OSError("error")

        result = tmux_spawner.list_sessions()

        assert result == []


class TestTmuxSpawnerSocketPath:
    """Tests for custom socket path support."""

    @patch("subprocess.run")
    def test_uses_custom_socket_path(self, mock_run):
        """Should use custom socket path in tmux commands."""
        socket_path = Path("/tmp/custom.socket")
        with patch.object(TmuxSpawner, "_find_tmux", return_value="/usr/bin/tmux"):
            spawner = TmuxSpawner(socket_path=socket_path)

        mock_run.return_value = Mock(returncode=0)
        spawner.is_alive("test-session")

        # Check that -S flag was used
        call_args = mock_run.call_args[0][0]
        assert "-S" in call_args
        assert str(socket_path) in call_args


class TestTmuxSpawnerEdgeCases:
    """Tests for edge cases and error conditions."""

    @patch("subprocess.run")
    def test_spawn_with_no_args(self, mock_run, tmux_spawner):
        """Should spawn with command only, no args."""
        config = SpawnerConfig(command="bash")

        has_session_result = Mock(returncode=1)
        new_session_result = Mock(returncode=0)
        list_panes_result = Mock(returncode=0, stdout="12345\n")

        mock_run.side_effect = [
            has_session_result,
            new_session_result,
            list_panes_result,
        ]

        result = tmux_spawner.spawn(config)

        assert result.success

    @patch("subprocess.run")
    def test_spawn_with_no_working_directory(self, mock_run, tmux_spawner):
        """Should spawn without working directory."""
        config = SpawnerConfig(command="bash", working_directory=None)

        has_session_result = Mock(returncode=1)
        new_session_result = Mock(returncode=0)
        list_panes_result = Mock(returncode=0, stdout="12345\n")

        mock_run.side_effect = [
            has_session_result,
            new_session_result,
            list_panes_result,
        ]

        result = tmux_spawner.spawn(config)

        assert result.success
        # Verify -c flag was not used
        new_session_call = mock_run.call_args_list[1][0][0]
        assert "-c" not in new_session_call

    @patch("subprocess.run")
    def test_get_session_pid_invalid_format(self, mock_run, tmux_spawner):
        """Should handle invalid PID format."""
        mock_run.return_value = Mock(returncode=0, stdout="not-a-number\n")

        pid = tmux_spawner._get_session_pid("test-session")

        assert pid is None

    @patch("subprocess.run")
    def test_spawn_os_error(self, mock_run, tmux_spawner, spawner_config):
        """Should handle OSError during spawn."""
        mock_run.side_effect = OSError("disk full")

        result = tmux_spawner.spawn(spawner_config)

        assert not result.success
        assert result.error is not None
