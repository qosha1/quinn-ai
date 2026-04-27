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
from shared.pyterm import PytermConfig


@pytest.fixture
def pyterm_config():
    """Provide standard pyterm config for tests."""
    return PytermConfig.standard()


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

    def test_init_with_config(self, session_config, pyterm_config):
        """Test basic initialization."""
        session = ClaudeCodeSession(session_config, pyterm_config)

        assert session._config == session_config
        assert session._agent_session is None
        assert session._pid is None
        assert session.state == SessionState.STOPPED

    def test_init_creates_session_id(self, session_config, pyterm_config):
        """Test session ID is created from worker_id."""
        session = ClaudeCodeSession(session_config, pyterm_config)

        assert session.id.worker_id == "test-worker"
        assert session.id.instance_id is not None

    def test_init_with_custom_pyterm_config(self, session_config, pyterm_config):
        """Test initialization with custom pyterm config."""
        from shared.pyterm import PytermConfig

        pyterm_config = PytermConfig.standard()
        session = ClaudeCodeSession(session_config, pyterm_config=pyterm_config)

        assert session._pyterm_config == pyterm_config


class TestClaudeCodeSessionProperties:
    """Test session properties."""

    def test_provider_name(self, session_config, pyterm_config):
        """Test provider_name property."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        assert session.provider_name == "claude_code"

    def test_pid_returns_none_initially(self, session_config, pyterm_config):
        """Test pid is None before start."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        assert session.pid is None


class TestClaudeCodeSessionSpawn:
    """Test process spawning."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_process_creates_agent_session(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _spawn_process creates AgentSession."""
        mock_session_class.return_value = mock_agent_session
        mock_config = MagicMock()
        mock_config_class.create.return_value = mock_config

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        assert session._agent_session is not None
        mock_session_class.assert_called_once()
        mock_agent_session.start.assert_called_once()

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_process_extracts_pid(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _spawn_process extracts PID from tmux session."""
        mock_session_class.return_value = mock_agent_session
        mock_config = MagicMock()
        mock_config_class.create.return_value = mock_config

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        assert session._pid == 12345

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_process_error_raises_session_spawn_error(
        self, mock_config_class, mock_session_class, session_config, pyterm_config
    ):
        """Test _spawn_process raises SessionSpawnError on failure."""
        mock_session_class.side_effect = Exception("Failed to start")
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)

        with pytest.raises(SessionSpawnError) as exc_info:
            session._spawn_process()

        assert "Failed to start" in str(exc_info.value)


class TestClaudeCodeSessionTerminate:
    """Test process termination."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_terminate_process_calls_stop(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _terminate_process calls AgentSession.stop()."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        session._terminate_process()

        mock_agent_session.stop.assert_called_once_with(force=False)
        assert session._agent_session is None
        assert session._pid is None

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_terminate_process_force(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _terminate_process with force=True."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        session._terminate_process(force=True)

        mock_agent_session.stop.assert_called_once_with(force=True)

    def test_terminate_process_no_session_is_safe(self, session_config, pyterm_config):
        """Test _terminate_process is safe when no session exists."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        # Should not raise
        session._terminate_process()


class TestClaudeCodeSessionIO:
    """Test input/output operations."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_send_input(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _send_input sends text to underlying session."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        session._send_input("Hello, Claude!")

        mock_agent_session._session.send.assert_called_once_with("Hello, Claude!")

    def test_send_input_no_session_is_safe(self, session_config, pyterm_config):
        """Test _send_input is safe when no session exists."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        # Should not raise
        session._send_input("Hello!")

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_read_output(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _read_output returns SessionOutput."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        output = session._read_output()

        assert isinstance(output, SessionOutput)
        assert output.content == "Test output"
        assert output.is_complete == True

    def test_read_output_no_session_returns_empty(self, session_config, pyterm_config):
        """Test _read_output returns empty output when no session."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        output = session._read_output()

        assert output.content == ""


class TestClaudeCodeSessionDetection:
    """Test ready/completion detection."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_detect_ready_when_idle(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _detect_ready returns True when agent is idle."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        assert session._detect_ready("any output") == True

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_detect_ready_when_not_idle(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _detect_ready returns False when agent is not idle."""
        mock_agent_session.is_idle = False
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        assert session._detect_ready("any output") == False

    def test_detect_ready_no_session(self, session_config, pyterm_config):
        """Test _detect_ready returns False when no session."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        assert session._detect_ready("any output") == False

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_detect_completion_when_idle(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _detect_completion returns True when agent is idle."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        assert session._detect_completion("any output") == True

    def test_detect_completion_no_session(self, session_config, pyterm_config):
        """Test _detect_completion returns True when no session."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        assert session._detect_completion("any output") == True


class TestClaudeCodeSessionStateMapping:
    """Test state mapping between pyterm and session states."""

    def test_map_pyterm_session_state_exited(self, session_config, pyterm_config):
        """Test mapping pyterm EXITED state to STOPPED."""
        from shared.pyterm.protocols import PytermSessionState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_pyterm_state_to_session_state(PytermSessionState.EXITED)

        assert result == SessionState.STOPPED

    def test_map_pyterm_session_state_idle(self, session_config, pyterm_config):
        """Test mapping pyterm IDLE state."""
        from shared.pyterm.protocols import PytermSessionState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_pyterm_state_to_session_state(PytermSessionState.IDLE)

        assert result == SessionState.IDLE

    def test_map_pyterm_session_state_running(self, session_config, pyterm_config):
        """Test mapping pyterm RUNNING state."""
        from shared.pyterm.protocols import PytermSessionState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_pyterm_state_to_session_state(PytermSessionState.RUNNING)

        assert result == SessionState.RUNNING

    def test_map_pyterm_session_state_error(self, session_config, pyterm_config):
        """Test mapping pyterm ERROR state to CRASHED."""
        from shared.pyterm.protocols import PytermSessionState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_pyterm_state_to_session_state(PytermSessionState.ERROR)

        assert result == SessionState.CRASHED

    def test_map_agent_state_idle(self, session_config, pyterm_config):
        """Test mapping agent IDLE state."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_agent_state_to_session_state(AgentState.IDLE)

        assert result == SessionState.IDLE

    def test_map_agent_state_thinking(self, session_config, pyterm_config):
        """Test mapping agent THINKING state."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_agent_state_to_session_state(AgentState.THINKING)

        assert result == SessionState.RUNNING

    def test_map_agent_state_executing_tool(self, session_config, pyterm_config):
        """Test mapping agent EXECUTING_TOOL state."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_agent_state_to_session_state(AgentState.EXECUTING_TOOL)

        assert result == SessionState.RUNNING

    def test_map_agent_state_error(self, session_config, pyterm_config):
        """Test mapping agent ERROR state."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_agent_state_to_session_state(AgentState.ERROR)

        assert result == SessionState.CRASHED


class TestClaudeCodeSessionInterrupt:
    """Test interrupt functionality."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_send_interrupt_calls_cancel(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _send_interrupt calls AgentSession.cancel()."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        session._send_interrupt()

        mock_agent_session.cancel.assert_called_once()

    def test_send_interrupt_no_session_is_safe(self, session_config, pyterm_config):
        """Test _send_interrupt is safe when no session."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        # Should not raise
        session._send_interrupt()


class TestClaudeCodeSessionExtended:
    """Test extended functionality."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_get_transcript(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test get_transcript returns transcript data."""
        mock_agent_session.transcript.to_dict.return_value = {
            "turns": [{"prompt": "Hello", "response": "Hi"}]
        }
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        transcript = session.get_transcript()

        assert len(transcript) == 1
        assert transcript[0]["prompt"] == "Hello"

    def test_get_transcript_no_session(self, session_config, pyterm_config):
        """Test get_transcript returns empty when no session."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        assert session.get_transcript() == []

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_get_tool_calls(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
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

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        tool_calls = session.get_tool_calls()

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "bash"

    def test_get_tool_calls_no_session(self, session_config, pyterm_config):
        """Test get_tool_calls returns empty when no session."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        assert session.get_tool_calls() == []

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_agent_session_property(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test agent_session property exposes underlying session."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        assert session.agent_session == mock_agent_session

    def test_agent_session_property_none_before_start(self, session_config, pyterm_config):
        """Test agent_session property is None before start."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        assert session.agent_session is None


class TestClaudeCodeSessionContextUsage:
    """Test context usage tracking."""

    def test_get_context_usage_returns_zero(self, session_config, pyterm_config):
        """Test _get_context_usage returns 0 (not yet implemented in pyterm)."""
        session = ClaudeCodeSession(session_config, pyterm_config)
        assert session._get_context_usage() == 0


class TestClaudeCodeSessionEdgeCases:
    """Test edge cases and additional scenarios."""

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_process_pid_extraction_failure(
        self, mock_config_class, mock_session_class, session_config
    ):
        """Test _spawn_process handles PID extraction failure gracefully."""
        mock_agent_session = MagicMock()
        mock_agent_session._session = None  # No session means AttributeError
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        # PID should be None when extraction fails
        assert session._pid is None
        assert session._agent_session is not None

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_read_output_with_tool_calls(
        self, mock_config_class, mock_session_class, session_config
    ):
        """Test _read_output properly formats tool calls."""
        mock_agent_session = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.name = "read"
        mock_tool_call.arguments = {"file": "test.py"}
        mock_agent_session.get_current_output.return_value = MagicMock(
            raw="Reading file...",
            prompt_ready=False,
            tool_calls=[mock_tool_call],
            state=None,
            assistant_response="I'll read the file",
            error_message=None,
        )
        mock_agent_session._session = MagicMock(pid=12345)
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        output = session._read_output()

        assert len(output.tool_calls) == 1
        assert output.tool_calls[0]["name"] == "read"
        assert output.tool_calls[0]["arguments"] == {"file": "test.py"}

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_read_output_with_state_and_error(
        self, mock_config_class, mock_session_class, session_config
    ):
        """Test _read_output includes state and error in metadata."""
        from shared.pyterm.agent_state import AgentState

        mock_agent_session = MagicMock()
        mock_agent_session.get_current_output.return_value = MagicMock(
            raw="Error occurred",
            prompt_ready=False,
            tool_calls=[],
            state=AgentState.ERROR,
            assistant_response=None,
            error_message="Something went wrong",
        )
        mock_agent_session._session = MagicMock(pid=12345)
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        output = session._read_output()

        assert output.metadata["state"] == "error"
        assert output.metadata["error"] == "Something went wrong"
        assert output.metadata["assistant_response"] is None

    def test_map_agent_state_waiting_input(self, session_config, pyterm_config):
        """Test mapping agent WAITING_INPUT state to RUNNING."""
        from shared.pyterm.agent_state import AgentState

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_agent_state_to_session_state(AgentState.WAITING_INPUT)

        assert result == SessionState.RUNNING

    def test_map_pyterm_state_unknown_defaults_to_stopped(self, session_config, pyterm_config):
        """Test mapping unknown pyterm state defaults to STOPPED."""
        from enum import Enum

        # Create a fake state to test unknown state handling
        class FakeState(Enum):
            UNKNOWN = "unknown"

        session = ClaudeCodeSession(session_config, pyterm_config)
        # Using a non-existent state (simulate by passing wrong type)
        result = session._map_pyterm_state_to_session_state(FakeState.UNKNOWN)

        assert result == SessionState.STOPPED

    def test_map_agent_state_unknown_defaults_to_running(self, session_config, pyterm_config):
        """Test mapping unknown agent state defaults to RUNNING."""
        from enum import Enum

        # Create a fake state to test unknown state handling
        class FakeAgentState(Enum):
            UNKNOWN = "unknown"

        session = ClaudeCodeSession(session_config, pyterm_config)
        result = session._map_agent_state_to_session_state(FakeAgentState.UNKNOWN)

        assert result == SessionState.RUNNING

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_process_passes_correct_session_config(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _spawn_process creates correct PytermSessionConfig."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        # Verify start was called with correct config
        call_args = mock_agent_session.start.call_args
        session_cfg = call_args[0][0]

        assert session_cfg.shell == "claude"
        assert session_cfg.args == ["--dangerously-skip-permissions"]
        assert session_cfg.cwd == "/tmp/test"
        assert session_cfg.cols == 120
        assert session_cfg.rows == 40

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_read_output_not_complete_when_prompt_not_ready(
        self, mock_config_class, mock_session_class, session_config
    ):
        """Test _read_output returns is_complete=False when prompt not ready."""
        mock_agent_session = MagicMock()
        mock_agent_session.get_current_output.return_value = MagicMock(
            raw="Still processing...",
            prompt_ready=False,
            tool_calls=[],
            state=None,
            assistant_response="Working on it",
            error_message=None,
        )
        mock_agent_session._session = MagicMock(pid=12345)
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        output = session._read_output()

        assert output.is_complete is False

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_get_tool_calls_with_none_status(
        self, mock_config_class, mock_session_class, session_config
    ):
        """Test get_tool_calls handles tool calls with None status."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "tc-456"
        mock_tool_call.name = "write"
        mock_tool_call.arguments = {"content": "hello"}
        mock_tool_call.result = None
        mock_tool_call.status = None

        mock_agent_session = MagicMock()
        mock_agent_session.get_tool_calls.return_value = [mock_tool_call]
        mock_agent_session._session = MagicMock(pid=12345)
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()
        tool_calls = session.get_tool_calls()

        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "tc-456"
        assert tool_calls[0]["status"] is None

    def test_session_config_with_env_vars(self):
        """Test session initialization with environment variables."""
        config = SessionConfig(
            worker_id="test-worker",
            provider="claude_code",
            command="claude",
            args=["--model", "opus"],
            working_directory=Path("/tmp/test"),
            env_vars={"ANTHROPIC_API_KEY": "test-key"},
        )
        session = ClaudeCodeSession(config, PytermConfig.standard())

        assert session._config.env_vars == {"ANTHROPIC_API_KEY": "test-key"}

    def test_session_config_with_custom_terminal_size(self):
        """Test session initialization with custom terminal size."""
        config = SessionConfig(
            worker_id="test-worker",
            provider="claude_code",
            command="claude",
            cols=200,
            rows=60,
        )
        session = ClaudeCodeSession(config, PytermConfig.standard())

        assert session._config.cols == 200
        assert session._config.rows == 60

    def test_session_config_with_timeouts(self):
        """Test session initialization with custom timeouts."""
        config = SessionConfig(
            worker_id="test-worker",
            provider="claude_code",
            command="claude",
            startup_timeout_ms=60000,
            idle_timeout_ms=600000,
            response_timeout_ms=1200000,
        )
        session = ClaudeCodeSession(config, PytermConfig.standard())

        assert session._config.startup_timeout_ms == 60000
        assert session._config.idle_timeout_ms == 600000
        assert session._config.response_timeout_ms == 1200000

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_uses_session_name_with_worker_id(
        self, mock_config_class, mock_session_class, session_config, pyterm_config, mock_agent_session
    ):
        """Test _spawn_process uses qn-{worker_id} as session name."""
        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(session_config, pyterm_config)
        session._spawn_process()

        # Verify AgentSessionConfig.create was called with correct session_name
        call_kwargs = mock_config_class.create.call_args[1]
        assert call_kwargs["session_name"] == "qn-test-worker"

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_passes_transcript_db_path(
        self, mock_config_class, mock_session_class, mock_agent_session
    ):
        """Test _spawn_process passes transcript_db_path to config."""
        config = SessionConfig(
            worker_id="test-worker",
            provider="claude_code",
            command="claude",
            transcript_db_path=Path("/tmp/transcripts.db"),
        )

        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(config, PytermConfig.standard())
        session._spawn_process()

        call_kwargs = mock_config_class.create.call_args[1]
        assert call_kwargs["db_path"] == Path("/tmp/transcripts.db")

    @patch("cli.core.sessions.claude_code.AgentSession")
    @patch("cli.core.sessions.claude_code.AgentSessionConfig")
    def test_spawn_without_working_directory(
        self, mock_config_class, mock_session_class, mock_agent_session
    ):
        """Test _spawn_process handles None working directory."""
        config = SessionConfig(
            worker_id="test-worker",
            provider="claude_code",
            command="claude",
            working_directory=None,
        )

        mock_session_class.return_value = mock_agent_session
        mock_config_class.create.return_value = MagicMock()

        session = ClaudeCodeSession(config, PytermConfig.standard())
        session._spawn_process()

        # Verify start was called with cwd=None
        call_args = mock_agent_session.start.call_args[0][0]
        assert call_args.cwd is None
