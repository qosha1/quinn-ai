"""
Tests for ClaudeCodeSession.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from pathlib import Path

from cli.core.session import (
    SessionConfig,
    SessionState,
    SessionSpawnError,
    SessionOutput,
)
from cli.core.sessions.claude_code import ClaudeCodeSession


@pytest.fixture
def session_config():
    """Create a basic session config for tests."""
    return SessionConfig(
        worker_id="test-worker",
        provider="claude_code",
        command="claude",
        args=["--dangerously-skip-permissions"],
        working_directory=Path("/tmp/test"),
    )


@pytest.fixture
def mock_agent_session():
    """Create a mock AgentSession."""
    mock = MagicMock()
    mock.is_idle = True
    mock.get_current_output.return_value = MagicMock(
        raw="Test output",
        prompt_ready=True,
        tool_calls=[],
        state=None,
        assistant_response="Response text",
        error_message=None,
    )
    mock.transcript = MagicMock()
    mock.transcript.to_dict.return_value = {"turns": []}
    mock.get_tool_calls.return_value = []
    mock._session = MagicMock()
    mock._session.pid = 12345
    return mock


class TestClaudeCodeSessionInit:
    """Test session initialization."""

    def test_init_with_config(self, session_config):
        """Test basic initialization."""
        session = ClaudeCodeSession(session_config)

        assert session._config == session_config
        assert session._agent_session is None
        assert session._pid is None
        assert session.state == SessionState.STOPPED

    def test_init_creates_session_id(self, session_config):
        """Test session ID is created from worker_id."""
        session = ClaudeCodeSession(session_config)

        assert session.id.worker_id == "test-worker"
        assert session.id.instance_id is not None

    def test_init_with_custom_pyterm_config(self, session_config):
        """Test initialization with custom pyterm config."""
        from shared.pyterm import PytermConfig

        pyterm_config = PytermConfig.standard()
        session = ClaudeCodeSession(session_config, pyterm_config=pyterm_config)

        assert session._pyterm_config == pyterm_config


class TestClaudeCodeSessionProperties:
    """Test session properties."""

    def test_provider_name(self, session_config):
        """Test provider_name property."""
        session = ClaudeCodeSession(session_config)
        assert session.provider_name == "claude_code"

    def test_pid_returns_none_initially(self, session_config):
        """Test pid is None before start."""
        session = ClaudeCodeSession(session_config)
        assert session.pid is None


class TestClaudeCodeSessionSpawn:
    """Test process spawning."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_process_creates_agent_session(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _spawn_process creates AgentSession."""
        mock_session_class.return_value = mock_agent_session
        mock_config = MagicMock()
        mock_config_class.create.return_value = mock_config

        session = ClaudeCodeSession(session_config)
        session._spawn_process()

        assert session._agent_session is not None
        mock_session_class.assert_called_once()
        mock_agent_session.start.assert_called_once()

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_process_extracts_pid(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _spawn_process extracts PID from tmux session."""
        mock_session_class.return_value = mock_agent_session
        mock_config = MagicMock()
        mock_config_class.create.return_value = mock_config

        session = ClaudeCodeSession(session_config)
        session._spawn_process()

        assert session._pid == 12345

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_process_error_raises_session_spawn_error(
        self, mock_config_class, mock_session_class, session_config
    ):
        """Test _spawn_process raises SessionSpawnError on failure."""
        mock_session_class.side_effect = Exception("Failed to start")
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)

        with pytest.raises(SessionSpawnError) as exc_info:
            session._spawn_process()

        assert "Failed to start" in str(exc_info.value)


class TestClaudeCodeSessionTerminate:
    """Test process termination."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_terminate_process_calls_stop(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _terminate_process calls AgentSession.stop()."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()
        session._terminate_process()

        mock_agent_session.stop.assert_called_once_with(force=False)
        assert session._agent_session is None
        assert session._pid is None

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_terminate_process_force(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _terminate_process with force=True."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()
        session._terminate_process(force=True)

        mock_agent_session.stop.assert_called_once_with(force=True)

    def test_terminate_process_no_session_is_safe(self, session_config):
        """Test _terminate_process is safe when no session exists."""
        session = ClaudeCodeSession(session_config)
        # Should not raise
        session._terminate_process()


class TestClaudeCodeSessionIO:
    """Test input/output operations."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_send_input(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _send_input sends text to underlying session."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()
        session._send_input("Hello, Claude!")

        mock_agent_session._session.send.assert_called_once_with("Hello, Claude!")

    def test_send_input_no_session_is_safe(self, session_config):
        """Test _send_input is safe when no session exists."""
        session = ClaudeCodeSession(session_config)
        # Should not raise
        session._send_input("Hello!")

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_read_output(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _read_output returns SessionOutput."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()
        output = session._read_output()

        assert isinstance(output, SessionOutput)
        assert output.content == "Test output"
        assert output.is_complete == True

    def test_read_output_no_session_returns_empty(self, session_config):
        """Test _read_output returns empty output when no session."""
        session = ClaudeCodeSession(session_config)
        output = session._read_output()

        assert output.content == ""


class TestClaudeCodeSessionDetection:
    """Test ready/completion detection."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_detect_ready_when_idle(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _detect_ready returns True when agent is idle."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()

        assert session._detect_ready("any output") == True

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_detect_ready_when_not_idle(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _detect_ready returns False when agent is not idle."""
        mock_agent_session.is_idle = False
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()

        assert session._detect_ready("any output") == False

    def test_detect_ready_no_session(self, session_config):
        """Test _detect_ready returns False when no session."""
        session = ClaudeCodeSession(session_config)
        assert session._detect_ready("any output") == False

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_detect_completion_when_idle(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _detect_completion returns True when agent is idle."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()

        assert session._detect_completion("any output") == True

    def test_detect_completion_no_session(self, session_config):
        """Test _detect_completion returns True when no session."""
        session = ClaudeCodeSession(session_config)
        assert session._detect_completion("any output") == True


class TestClaudeCodeSessionStateMapping:
    """Test state mapping between pyterm and session states."""

    def test_map_pyterm_session_state_exited(self, session_config):
        """Test mapping pyterm EXITED state to STOPPED."""
        from shared.pyterm.protocols import SessionState as PytermSessionState

        session = ClaudeCodeSession(session_config)
        result = session._map_pyterm_state_to_session_state(PytermSessionState.EXITED)

        assert result == SessionState.STOPPED

    def test_map_pyterm_session_state_idle(self, session_config):
        """Test mapping pyterm IDLE state."""
        from shared.pyterm.protocols import SessionState as PytermSessionState

        session = ClaudeCodeSession(session_config)
        result = session._map_pyterm_state_to_session_state(PytermSessionState.IDLE)

        assert result == SessionState.IDLE

    def test_map_pyterm_session_state_running(self, session_config):
        """Test mapping pyterm RUNNING state."""
        from shared.pyterm.protocols import SessionState as PytermSessionState

        session = ClaudeCodeSession(session_config)
        result = session._map_pyterm_state_to_session_state(PytermSessionState.RUNNING)

        assert result == SessionState.RUNNING

    def test_map_pyterm_session_state_error(self, session_config):
        """Test mapping pyterm ERROR state to CRASHED."""
        from shared.pyterm.protocols import SessionState as PytermSessionState

        session = ClaudeCodeSession(session_config)
        result = session._map_pyterm_state_to_session_state(PytermSessionState.ERROR)

        assert result == SessionState.CRASHED

    def test_map_agent_state_idle(self, session_config):
        """Test mapping agent IDLE state."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config)
        result = session._map_agent_state_to_session_state(AgentState.IDLE)

        assert result == SessionState.IDLE

    def test_map_agent_state_thinking(self, session_config):
        """Test mapping agent THINKING state."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config)
        result = session._map_agent_state_to_session_state(AgentState.THINKING)

        assert result == SessionState.RUNNING

    def test_map_agent_state_executing_tool(self, session_config):
        """Test mapping agent EXECUTING_TOOL state."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config)
        result = session._map_agent_state_to_session_state(AgentState.EXECUTING_TOOL)

        assert result == SessionState.RUNNING

    def test_map_agent_state_error(self, session_config):
        """Test mapping agent ERROR state."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config)
        result = session._map_agent_state_to_session_state(AgentState.ERROR)

        assert result == SessionState.CRASHED


class TestClaudeCodeSessionInterrupt:
    """Test interrupt functionality."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_send_interrupt_calls_cancel(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test _send_interrupt calls AgentSession.cancel()."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()
        session._send_interrupt()

        mock_agent_session.cancel.assert_called_once()

    def test_send_interrupt_no_session_is_safe(self, session_config):
        """Test _send_interrupt is safe when no session."""
        session = ClaudeCodeSession(session_config)
        # Should not raise
        session._send_interrupt()


class TestClaudeCodeSessionExtended:
    """Test extended functionality."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_get_transcript(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test get_transcript returns transcript data."""
        mock_agent_session.transcript.to_dict.return_value = {
            "turns": [{"prompt": "Hello", "response": "Hi"}]
        }
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()
        transcript = session.get_transcript()

        assert len(transcript) == 1
        assert transcript[0]["prompt"] == "Hello"

    def test_get_transcript_no_session(self, session_config):
        """Test get_transcript returns empty when no session."""
        session = ClaudeCodeSession(session_config)
        assert session.get_transcript() == []

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_get_tool_calls(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test get_tool_calls returns tool call data."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "tc-123"
        mock_tool_call.name = "bash"
        mock_tool_call.arguments = {"command": "ls"}
        mock_tool_call.result = "file1 file2"
        mock_tool_call.status = MagicMock(value="completed")
        mock_agent_session.get_tool_calls.return_value = [mock_tool_call]
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()
        tool_calls = session.get_tool_calls()

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "bash"

    def test_get_tool_calls_no_session(self, session_config):
        """Test get_tool_calls returns empty when no session."""
        session = ClaudeCodeSession(session_config)
        assert session.get_tool_calls() == []

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_agent_session_property(
        self, mock_config_class, mock_session_class, session_config, mock_agent_session
    ):
        """Test agent_session property exposes underlying session."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config)
        session._spawn_process()

        assert session.agent_session == mock_agent_session

    def test_agent_session_property_none_before_start(self, session_config):
        """Test agent_session property is None before start."""
        session = ClaudeCodeSession(session_config)
        assert session.agent_session is None


class TestClaudeCodeSessionContextUsage:
    """Test context usage tracking."""

    def test_get_context_usage_returns_zero(self, session_config):
        """Test _get_context_usage returns 0 (not yet implemented in pyterm)."""
        session = ClaudeCodeSession(session_config)
        assert session._get_context_usage() == 0
