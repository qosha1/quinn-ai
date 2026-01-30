"""
Tests for SubprocessSpawner.

Tests direct subprocess spawning for ephemeral sessions.
"""

import pytest
import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock

from core.sessions.spawner import SpawnerConfig
from core.sessions.subprocess_spawner import SubprocessSpawner


@pytest.fixture
def spawner():
    """Create a SubprocessSpawner for testing."""
    return SubprocessSpawner()


@pytest.fixture
def spawner_config():
    """Create a basic spawner config."""
    return SpawnerConfig(
        command="python",
        args=["-c", "print('hello')"],
        working_directory=Path("/tmp"),
        worker_id="worker-123",
        env_vars={"TEST_VAR": "test_value"},
    )


class TestSubprocessSpawnerInit:
    """Tests for SubprocessSpawner initialization."""

    def test_init(self):
        """Should initialize with empty process dict."""
        spawner = SubprocessSpawner()

        assert spawner.name == "subprocess"
        assert len(spawner._processes) == 0

    def test_thread_safe_init(self):
        """Should have lock for thread safety."""
        spawner = SubprocessSpawner()

        assert hasattr(spawner, "_lock")


class TestSubprocessSpawnerSpawn:
    """Tests for spawning subprocesses."""

    @patch("subprocess.Popen")
    def test_spawn_success(self, mock_popen, spawner, spawner_config):
        """Should spawn subprocess successfully."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        result = spawner.spawn(spawner_config)

        assert result.success
        assert result.pid == 12345
        assert result.session_id == "12345"
        assert result.metadata["strategy"] == "subprocess"
        assert result.metadata["command"] == "python"

    @patch("subprocess.Popen")
    def test_spawn_tracks_process(self, mock_popen, spawner, spawner_config):
        """Should track spawned process."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        result = spawner.spawn(spawner_config)

        assert "12345" in spawner._processes
        assert spawner._processes["12345"] is mock_process

    @patch("subprocess.Popen")
    def test_spawn_with_env_vars(self, mock_popen, spawner, spawner_config):
        """Should pass environment variables."""
        mock_popen.return_value = Mock(pid=12345)

        spawner.spawn(spawner_config)

        call_kwargs = mock_popen.call_args[1]
        assert "TEST_VAR" in call_kwargs["env"]
        assert call_kwargs["env"]["TEST_VAR"] == "test_value"

    @patch("subprocess.Popen")
    def test_spawn_with_working_directory(self, mock_popen, spawner, spawner_config):
        """Should use working directory."""
        mock_popen.return_value = Mock(pid=12345)

        spawner.spawn(spawner_config)

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["cwd"] == "/tmp"

    @patch("subprocess.Popen")
    def test_spawn_without_working_directory(self, mock_popen, spawner):
        """Should handle None working directory."""
        config = SpawnerConfig(command="bash")
        mock_popen.return_value = Mock(pid=12345)

        spawner.spawn(config)

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["cwd"] is None

    @patch("subprocess.Popen")
    def test_spawn_command_not_found(self, mock_popen, spawner):
        """Should handle command not found."""
        config = SpawnerConfig(command="nonexistent-command")
        mock_popen.side_effect = FileNotFoundError()

        result = spawner.spawn(config)

        assert not result.success
        assert "not found" in result.error

    @patch("subprocess.Popen")
    def test_spawn_permission_denied(self, mock_popen, spawner, spawner_config):
        """Should handle permission denied."""
        mock_popen.side_effect = PermissionError()

        result = spawner.spawn(spawner_config)

        assert not result.success
        assert "Permission denied" in result.error

    @patch("subprocess.Popen")
    def test_spawn_subprocess_error(self, mock_popen, spawner, spawner_config):
        """Should handle subprocess errors."""
        mock_popen.side_effect = subprocess.SubprocessError("error")

        result = spawner.spawn(spawner_config)

        assert not result.success
        assert result.error is not None

    @patch("subprocess.Popen")
    def test_spawn_os_error(self, mock_popen, spawner, spawner_config):
        """Should handle OS errors."""
        mock_popen.side_effect = OSError("disk full")

        result = spawner.spawn(spawner_config)

        assert not result.success
        assert result.error is not None


class TestSubprocessSpawnerStop:
    """Tests for stopping subprocesses."""

    @patch("subprocess.Popen")
    def test_stop_graceful(self, mock_popen, spawner, spawner_config):
        """Should stop process gracefully."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.stop("12345", force=False)

        assert result
        mock_process.terminate.assert_called_once()
        assert "12345" not in spawner._processes

    @patch("subprocess.Popen")
    def test_stop_force(self, mock_popen, spawner, spawner_config):
        """Should kill process when force=True."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.stop("12345", force=True)

        assert result
        mock_process.kill.assert_called_once()

    @patch("subprocess.Popen")
    def test_stop_with_timeout(self, mock_popen, spawner, spawner_config):
        """Should wait for process to exit with timeout."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        spawner.stop("12345")

        mock_process.wait.assert_called()

    @patch("subprocess.Popen")
    def test_stop_timeout_expired_kills(self, mock_popen, spawner, spawner_config):
        """Should force kill if graceful shutdown times out."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", 5),
            None,
        ]
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.stop("12345", force=False)

        assert result
        mock_process.kill.assert_called_once()

    def test_stop_nonexistent_session(self, spawner):
        """Should return False for nonexistent session."""
        result = spawner.stop("nonexistent")

        assert not result

    @patch("subprocess.Popen")
    def test_stop_os_error(self, mock_popen, spawner, spawner_config):
        """Should handle OS errors during stop."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.terminate.side_effect = OSError("error")
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.stop("12345")

        assert not result


class TestSubprocessSpawnerIsAlive:
    """Tests for checking process status."""

    @patch("subprocess.Popen")
    def test_is_alive_true(self, mock_popen, spawner, spawner_config):
        """Should return True when process is running."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Still running
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.is_alive("12345")

        assert result

    @patch("subprocess.Popen")
    def test_is_alive_false(self, mock_popen, spawner, spawner_config):
        """Should return False when process has exited."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = 0  # Exited
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.is_alive("12345")

        assert not result

    @patch("subprocess.Popen")
    def test_is_alive_cleans_up_dead_process(self, mock_popen, spawner, spawner_config):
        """Should remove dead process from tracking."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = 0  # Exited
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        spawner.is_alive("12345")

        assert "12345" not in spawner._processes

    def test_is_alive_nonexistent(self, spawner):
        """Should return False for nonexistent session."""
        result = spawner.is_alive("nonexistent")

        assert not result


class TestSubprocessSpawnerIO:
    """Tests for I/O operations."""

    @patch("subprocess.Popen")
    def test_send_input_success(self, mock_popen, spawner, spawner_config):
        """Should send input to stdin."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdin = Mock()
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.send_input("12345", "hello\n")

        assert result
        mock_process.stdin.write.assert_called_once_with(b"hello\n")
        mock_process.stdin.flush.assert_called_once()

    @patch("subprocess.Popen")
    def test_send_input_no_stdin(self, mock_popen, spawner, spawner_config):
        """Should return False when stdin is None."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdin = None
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.send_input("12345", "hello")

        assert not result

    def test_send_input_nonexistent(self, spawner):
        """Should return False for nonexistent session."""
        result = spawner.send_input("nonexistent", "text")

        assert not result

    @patch("subprocess.Popen")
    def test_send_input_os_error(self, mock_popen, spawner, spawner_config):
        """Should handle OS errors (broken pipe)."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdin = Mock()
        mock_process.stdin.write.side_effect = OSError("broken pipe")
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.send_input("12345", "text")

        assert not result

    @patch("subprocess.Popen")
    @patch("select.select")
    def test_read_output_success(self, mock_select, mock_popen, spawner, spawner_config):
        """Should read output from stdout."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdout = Mock()
        mock_process.stdout.read.return_value = b"output text"
        mock_popen.return_value = mock_process

        # Mock select to indicate data is available
        mock_select.return_value = ([mock_process.stdout], [], [])

        spawner.spawn(spawner_config)
        result = spawner.read_output("12345")

        assert result == "output text"

    @patch("subprocess.Popen")
    @patch("select.select")
    def test_read_output_with_timeout(self, mock_select, mock_popen, spawner, spawner_config):
        """Should use timeout parameter."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdout = Mock()
        mock_process.stdout.read.return_value = b"output"
        mock_popen.return_value = mock_process

        mock_select.return_value = ([mock_process.stdout], [], [])

        spawner.spawn(spawner_config)
        spawner.read_output("12345", timeout_ms=5000)

        # Check that select was called with timeout in seconds
        call_args = mock_select.call_args[0]
        timeout = call_args[3]
        assert timeout == 5.0

    @patch("subprocess.Popen")
    @patch("select.select")
    def test_read_output_no_data_available(self, mock_select, mock_popen, spawner, spawner_config):
        """Should return empty string when no data available."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdout = Mock()
        mock_popen.return_value = mock_process

        # Mock select to indicate no data available
        mock_select.return_value = ([], [], [])

        spawner.spawn(spawner_config)
        result = spawner.read_output("12345")

        assert result == ""

    @patch("subprocess.Popen")
    def test_read_output_no_stdout(self, mock_popen, spawner, spawner_config):
        """Should return empty string when stdout is None."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdout = None
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.read_output("12345")

        assert result == ""

    def test_read_output_nonexistent(self, spawner):
        """Should return empty string for nonexistent session."""
        result = spawner.read_output("nonexistent")

        assert result == ""

    @patch("subprocess.Popen")
    @patch("select.select")
    def test_read_output_os_error(self, mock_select, mock_popen, spawner, spawner_config):
        """Should handle OS errors."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdout = Mock()
        mock_popen.return_value = mock_process

        mock_select.side_effect = OSError("error")

        spawner.spawn(spawner_config)
        result = spawner.read_output("12345")

        assert result == ""


class TestSubprocessSpawnerSignal:
    """Tests for sending signals."""

    @patch("subprocess.Popen")
    def test_send_signal_success(self, mock_popen, spawner, spawner_config):
        """Should send signal to process."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.send_signal("12345", signal.SIGINT)

        assert result
        mock_process.send_signal.assert_called_once_with(signal.SIGINT)

    def test_send_signal_nonexistent(self, spawner):
        """Should return False for nonexistent session."""
        result = spawner.send_signal("nonexistent", signal.SIGINT)

        assert not result

    @patch("subprocess.Popen")
    def test_send_signal_os_error(self, mock_popen, spawner, spawner_config):
        """Should handle OS errors."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.send_signal.side_effect = OSError("error")
        mock_popen.return_value = mock_process

        spawner.spawn(spawner_config)
        result = spawner.send_signal("12345", signal.SIGINT)

        assert not result


class TestSubprocessSpawnerCleanup:
    """Tests for cleanup functionality."""

    @patch("subprocess.Popen")
    def test_cleanup_stops_all_processes(self, mock_popen, spawner):
        """Should stop all tracked processes."""
        mock_process1 = Mock(pid=111)
        mock_process2 = Mock(pid=222)

        mock_popen.side_effect = [mock_process1, mock_process2]

        spawner.spawn(SpawnerConfig(command="cmd1"))
        spawner.spawn(SpawnerConfig(command="cmd2"))

        spawner.cleanup()

        mock_process1.kill.assert_called_once()
        mock_process2.kill.assert_called_once()
        assert len(spawner._processes) == 0


class TestSubprocessSpawnerThreadSafety:
    """Tests for thread safety."""

    @patch("subprocess.Popen")
    def test_concurrent_spawn(self, mock_popen, spawner):
        """Should handle concurrent spawn calls."""
        import threading

        results = []

        def spawn_process(i):
            mock_process = Mock(pid=1000 + i)
            mock_popen.return_value = mock_process
            config = SpawnerConfig(command=f"cmd{i}")
            result = spawner.spawn(config)
            results.append(result)

        threads = [threading.Thread(target=spawn_process, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert all(r.success for r in results)

    @patch("subprocess.Popen")
    def test_concurrent_stop(self, mock_popen, spawner):
        """Should handle concurrent stop calls."""
        import threading

        # Spawn processes
        for i in range(5):
            mock_process = Mock(pid=1000 + i)
            mock_popen.return_value = mock_process
            spawner.spawn(SpawnerConfig(command=f"cmd{i}"))

        results = []

        def stop_process(session_id):
            result = spawner.stop(session_id, force=True)
            results.append(result)

        threads = [
            threading.Thread(target=stop_process, args=(str(1000 + i),))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5


class TestSubprocessSpawnerEdgeCases:
    """Tests for edge cases."""

    @patch("subprocess.Popen")
    def test_spawn_empty_args(self, mock_popen, spawner):
        """Should handle empty args list."""
        config = SpawnerConfig(command="bash", args=[])
        mock_popen.return_value = Mock(pid=12345)

        result = spawner.spawn(config)

        assert result.success
        call_args = mock_popen.call_args[0][0]
        assert call_args == ["bash"]

    @patch("subprocess.Popen")
    def test_spawn_empty_env_vars(self, mock_popen, spawner):
        """Should handle empty env_vars dict."""
        config = SpawnerConfig(command="bash", env_vars={})
        mock_popen.return_value = Mock(pid=12345)

        result = spawner.spawn(config)

        assert result.success

    @patch("subprocess.Popen")
    @patch("select.select")
    def test_read_output_unicode_decode_error(self, mock_select, mock_popen, spawner):
        """Should handle unicode decode errors."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdout = Mock()
        # Invalid UTF-8 bytes
        mock_process.stdout.read.return_value = b"\xff\xfe"
        mock_popen.return_value = mock_process

        mock_select.return_value = ([mock_process.stdout], [], [])

        spawner.spawn(SpawnerConfig(command="bash"))
        result = spawner.read_output("12345")

        # Should use error replacement
        assert isinstance(result, str)
