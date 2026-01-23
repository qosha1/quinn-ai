"""
Tests for TmuxSession - session implementation using tmux.
"""

import pytest
import subprocess
import threading
import time
from unittest.mock import MagicMock, Mock, patch, call

from shared.pyterm.tmux_session import TmuxSession, TMUX_TIMEOUT
from shared.pyterm.protocols import SessionState, SessionConfig, ExtractedOutput
from shared.pyterm.config import PytermConfig


class TestTmuxSessionInit:
    """Tests for TmuxSession initialization."""

    def test_init_default(self):
        """Test initialization with defaults."""
        session = TmuxSession()

        assert session.id.startswith("pyterm-")
        assert len(session.id) > len("pyterm-")
        assert session.state == SessionState.IDLE
        assert session.pid is None

    def test_init_with_name(self):
        """Test initialization with explicit session name."""
        session = TmuxSession(session_name="test-session")

        assert session.id == "test-session"
        assert session.state == SessionState.IDLE

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = PytermConfig.standard()
        session = TmuxSession(session_name="test", config=config)

        assert session._config == config


class TestTmuxSessionClassMethods:
    """Tests for TmuxSession class methods."""

    @patch('subprocess.run')
    def test_exists_returns_true(self, mock_run):
        """Test exists() when session exists."""
        mock_run.return_value = Mock(returncode=0)

        result = TmuxSession.exists("test-session")

        assert result is True
        mock_run.assert_called_once_with(
            ["tmux", "has-session", "-t", "test-session"],
            capture_output=True,
            text=True,
            timeout=TMUX_TIMEOUT,
        )

    @patch('subprocess.run')
    def test_exists_returns_false(self, mock_run):
        """Test exists() when session doesn't exist."""
        mock_run.return_value = Mock(returncode=1)

        result = TmuxSession.exists("nonexistent")

        assert result is False

    @patch('subprocess.run')
    def test_exists_handles_timeout(self, mock_run):
        """Test exists() handles timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired("tmux", TMUX_TIMEOUT)

        result = TmuxSession.exists("test-session")

        assert result is False

    @patch('subprocess.run')
    def test_connect_success(self, mock_run):
        """Test connect() to existing session."""
        # First call: has-session (exists check)
        # Second call: display-message (get PID)
        mock_run.side_effect = [
            Mock(returncode=0),  # exists
            Mock(returncode=0, stdout="12345\n"),  # get PID
        ]

        session = TmuxSession.connect("existing-session")

        assert session.id == "existing-session"
        assert session.state == SessionState.RUNNING
        assert session.pid == 12345

    @patch('subprocess.run')
    def test_connect_nonexistent_session_raises(self, mock_run):
        """Test connect() raises when session doesn't exist."""
        mock_run.return_value = Mock(returncode=1)

        with pytest.raises(ValueError, match="does not exist"):
            TmuxSession.connect("nonexistent")

    @patch('subprocess.run')
    def test_connect_handles_pid_extraction_failure(self, mock_run):
        """Test connect() handles PID extraction failure gracefully."""
        mock_run.side_effect = [
            Mock(returncode=0),  # exists
            Mock(returncode=1, stdout=""),  # PID extraction fails
        ]

        session = TmuxSession.connect("existing-session")

        assert session.state == SessionState.RUNNING
        assert session.pid is None

    @patch('subprocess.run')
    def test_capture_success(self, mock_run):
        """Test capture() returns pane content."""
        mock_run.return_value = Mock(returncode=0, stdout="Hello world\n")

        output = TmuxSession.capture("test-session")

        assert output == "Hello world\n"
        mock_run.assert_called_once_with(
            ["tmux", "capture-pane", "-t", "test-session", "-p"],
            capture_output=True,
            text=True,
            timeout=TMUX_TIMEOUT,
        )

    @patch('subprocess.run')
    def test_capture_failure_returns_empty(self, mock_run):
        """Test capture() returns empty string on failure."""
        mock_run.return_value = Mock(returncode=1, stdout="")

        output = TmuxSession.capture("test-session")

        assert output == ""

    @patch('subprocess.run')
    def test_capture_timeout_returns_empty(self, mock_run):
        """Test capture() handles timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("tmux", TMUX_TIMEOUT)

        output = TmuxSession.capture("test-session")

        assert output == ""


class TestTmuxSessionLifecycle:
    """Tests for session lifecycle (start/stop)."""

    @patch('subprocess.run')
    def test_start_creates_session(self, mock_run):
        """Test start() creates tmux session."""
        # set-environment calls (can be multiple) + new-session + display-message
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # new-session
            Mock(returncode=0, stdout="12345\n", stderr=""),  # display-message (PID)
        ]

        session = TmuxSession(session_name="test")
        session.start()

        assert session.state == SessionState.RUNNING
        assert session.pid == 12345

        # Verify new-session was called
        calls = mock_run.call_args_list
        new_session_call = calls[0]
        args = new_session_call[0][0]
        assert "tmux" in args
        assert "new-session" in args
        assert "-s" in args
        assert "test" in args

    @patch('subprocess.run')
    def test_start_with_config(self, mock_run):
        """Test start() with custom SessionConfig."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # new-session
            Mock(returncode=0, stdout="999\n", stderr=""),  # display-message
        ]

        config = SessionConfig(
            shell="/bin/zsh",
            cols=120,
            rows=40,
            cwd="/tmp",
            args=["-l"],
        )

        session = TmuxSession(session_name="test")
        session.start(config)

        assert session.state == SessionState.RUNNING

        # Verify config was used
        new_session_call = mock_run.call_args_list[0]
        args = new_session_call[0][0]
        assert "-x" in args
        assert "120" in args
        assert "-y" in args
        assert "40" in args
        assert "-c" in args
        assert "/tmp" in args

    @patch('subprocess.run')
    def test_start_when_already_running_raises(self, mock_run):
        """Test start() raises when already running."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="999\n", stderr=""),
        ]

        session = TmuxSession(session_name="test")
        session.start()

        with pytest.raises(RuntimeError, match="already running"):
            session.start()

    @patch('subprocess.run')
    def test_stop_kills_session(self, mock_run):
        """Test stop() kills tmux session."""
        # Start session first
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message (start)
            Mock(returncode=0),  # send-keys (inject exit)
            Mock(returncode=0),  # has-session (check if exists)
            Mock(returncode=0),  # kill-session
        ]

        session = TmuxSession(session_name="test")
        session.start()

        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            session.stop()

        assert session.state == SessionState.EXITED
        assert session.pid is None

    @patch('subprocess.run')
    def test_stop_force(self, mock_run):
        """Test stop(force=True) immediately kills session."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0),  # kill-session (force)
        ]

        session = TmuxSession(session_name="test")
        session.start()
        session.stop(force=True)

        assert session.state == SessionState.EXITED

        # Verify kill-session was called (not send-keys)
        kill_call = mock_run.call_args_list[-1]
        args = kill_call[0][0]
        assert "kill-session" in args

    @patch('subprocess.run')
    def test_stop_when_not_running(self, mock_run):
        """Test stop() does nothing when not running."""
        session = TmuxSession(session_name="test")
        session.stop()

        # Should not call any tmux commands
        mock_run.assert_not_called()


class TestTmuxSessionOperations:
    """Tests for session operations (inject, extract)."""

    @patch('subprocess.run')
    def test_inject_sends_text(self, mock_run):
        """Test inject() sends text to session."""
        # Start session first
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0),  # send-keys (inject)
        ]

        session = TmuxSession(session_name="test")
        session.start()
        session.inject("hello\n")

        # Verify send-keys was called
        inject_call = mock_run.call_args_list[-1]
        args = inject_call[0][0]
        assert "send-keys" in args
        assert "-l" in args  # literal flag
        assert "hello\n" in args

    @patch('subprocess.run')
    def test_inject_when_not_running_raises(self, mock_run):
        """Test inject() raises when not running."""
        session = TmuxSession(session_name="test")

        with pytest.raises(RuntimeError, match="not running"):
            session.inject("hello")

    @patch('subprocess.run')
    def test_inject_keys(self, mock_run):
        """Test inject_keys() sends key sequences."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0),  # send-keys (Enter)
            Mock(returncode=0),  # send-keys (C-c)
        ]

        session = TmuxSession(session_name="test")
        session.start()
        session.inject_keys(["Enter", "C-c"])

        # Verify send-keys was called twice
        assert mock_run.call_count == 4  # start + 2 inject_keys

    @patch('subprocess.run')
    def test_extract_returns_output(self, mock_run):
        """Test extract() returns current pane content."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0, stdout="pane content\n"),  # capture-pane
        ]

        session = TmuxSession(session_name="test")
        session.start()
        output = session.extract()

        assert isinstance(output, ExtractedOutput)
        assert output.text == "pane content\n"
        assert output.timestamp > 0

    @patch('subprocess.run')
    def test_extract_when_not_running_raises(self, mock_run):
        """Test extract() raises when not running."""
        session = TmuxSession(session_name="test")

        with pytest.raises(RuntimeError, match="not running"):
            session.extract()

    @patch('subprocess.run')
    def test_extract_history(self, mock_run):
        """Test extract_history() returns scrollback."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0, stdout="line1\nline2\nline3\n"),  # capture-pane
        ]

        session = TmuxSession(session_name="test")
        session.start()
        history = session.extract_history()

        assert isinstance(history, list)
        assert history == ["line1", "line2", "line3"]

    @patch('subprocess.run')
    def test_extract_history_with_limit(self, mock_run):
        """Test extract_history() with line limit."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0, stdout="line1\nline2\n"),  # capture-pane
        ]

        session = TmuxSession(session_name="test")
        session.start()
        history = session.extract_history(lines=2)

        # Verify -E flag was used
        capture_call = mock_run.call_args_list[-1]
        args = capture_call[0][0]
        assert "-E" in args
        assert "2" in args

    @patch('subprocess.run')
    def test_resize(self, mock_run):
        """Test resize() changes terminal dimensions."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0),  # resize-window
        ]

        session = TmuxSession(session_name="test")
        session.start()
        session.resize(120, 40)

        # Verify resize-window was called
        resize_call = mock_run.call_args_list[-1]
        args = resize_call[0][0]
        assert "resize-window" in args
        assert "120" in args
        assert "40" in args


class TestTmuxSessionCallbacks:
    """Tests for callback registration and firing."""

    @patch('subprocess.run')
    def test_on_output_callback(self, mock_run):
        """Test on_output() registers callback."""
        session = TmuxSession(session_name="test")

        callback = MagicMock()
        session.on_output(callback)

        assert callback in session._output_callbacks

    @patch('subprocess.run')
    def test_on_state_change_callback(self, mock_run):
        """Test on_state_change() registers and fires callback."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
        ]

        session = TmuxSession(session_name="test")

        callback = MagicMock()
        session.on_state_change(callback)

        session.start()

        # Callback should be fired with state transition
        callback.assert_called_once_with(SessionState.IDLE, SessionState.RUNNING)


class TestTmuxSessionPolling:
    """Tests for output polling."""

    @patch('subprocess.run')
    def test_start_polling(self, mock_run):
        """Test start_polling() starts polling thread."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0, stdout="output1\n"),  # extract (in poll loop)
        ]

        session = TmuxSession(session_name="test")
        session.start()
        session.start_polling()

        assert session._polling_thread is not None
        assert session._polling_thread.is_alive()

        # Clean up
        session.stop_polling()

    @patch('subprocess.run')
    def test_polling_calls_callbacks_on_change(self, mock_run):
        """Test polling calls output callbacks when output changes."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0, stdout="output1\n"),  # first extract
            Mock(returncode=0, stdout="output2\n"),  # second extract (changed)
            Mock(returncode=0, stdout="output2\n"),  # third extract (no change)
        ]

        session = TmuxSession(session_name="test")
        callback = MagicMock()

        session.start()
        session.on_output(callback)
        session.start_polling()

        # Wait for a few poll cycles
        time.sleep(0.3)

        # Clean up
        session.stop_polling()

        # Callback should be called at least once (when output changed)
        assert callback.call_count >= 1

    @patch('subprocess.run')
    def test_stop_polling(self, mock_run):
        """Test stop_polling() stops the polling thread."""
        mock_run.side_effect = [
            Mock(returncode=0),  # new-session
            Mock(returncode=0, stdout="999\n"),  # display-message
            Mock(returncode=0, stdout="output\n"),  # extract
        ]

        session = TmuxSession(session_name="test")
        session.start()
        session.start_polling()

        # Stop polling
        session.stop_polling()

        # Thread should exit
        time.sleep(0.3)
        assert not session._polling_thread.is_alive()

    @patch('subprocess.run')
    def test_start_polling_when_already_polling(self, mock_run):
        """Test start_polling() is idempotent."""
        mock_run.side_effect = [
            Mock(returncode=0),
            Mock(returncode=0, stdout="999\n"),
        ] + [Mock(returncode=0, stdout="output\n")] * 10

        session = TmuxSession(session_name="test")
        session.start()
        session.start_polling()

        first_thread = session._polling_thread

        # Call again
        session.start_polling()

        # Should be same thread
        assert session._polling_thread == first_thread

        session.stop_polling()


class TestTmuxSessionProtocol:
    """Tests verifying TmuxSession implements Session protocol."""

    def test_implements_protocol(self):
        """Test TmuxSession implements Session protocol."""
        from shared.pyterm.protocols import Session

        session = TmuxSession()

        # Check required properties exist
        assert hasattr(session, 'id')
        assert hasattr(session, 'state')

        # Check required methods exist
        assert hasattr(session, 'start')
        assert hasattr(session, 'stop')
        assert hasattr(session, 'inject')
        assert hasattr(session, 'extract')
        assert hasattr(session, 'on_output')
        assert hasattr(session, 'on_state_change')
