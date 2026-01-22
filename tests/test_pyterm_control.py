"""
Tests for pyterm agent control operations.
"""

import pytest
import threading
import time
from unittest.mock import MagicMock, patch

from shared.pyterm.control import (
    AgentController,
    ControlConfig,
    PromptResult,
    TimeoutError,
    CancelledError,
)
from shared.pyterm.agent_state import AgentState
from shared.pyterm.protocols import ExtractedOutput, SessionState
from shared.pyterm.conversation import Message, ToolCall, Transcript
from shared.pyterm.config import PytermConfig, TimingConfig, LoopDetectionConfig, SessionConfig as PytermSessionConfig
from shared.pyterm.parsers import get_parser


class MockSession:
    """Mock session for testing."""

    def __init__(self):
        self.injected: list[str] = []
        self.output_text = ""
        self._state = SessionState.RUNNING

    @property
    def id(self) -> str:
        return "test-session"

    @property
    def state(self) -> SessionState:
        return self._state

    def inject(self, text: str) -> None:
        self.injected.append(text)

    def extract(self) -> ExtractedOutput:
        return ExtractedOutput(text=self.output_text, timestamp=time.time())

    def set_output(self, text: str) -> None:
        self.output_text = text


def create_test_config(
    poll_interval: float = 0.1,
    idle_timeout: float = 300.0,
    response_timeout: float = 600.0,
    cancel_signal: str = "\x03",
) -> ControlConfig:
    """Create a ControlConfig for testing with custom timing values."""
    pyterm_config = PytermConfig(
        timing=TimingConfig(
            poll_interval=poll_interval,
            idle_timeout=idle_timeout,
            response_timeout=response_timeout,
            stop_grace_period=0.5,
        ),
        loop_detection=LoopDetectionConfig(
            max_triggers_per_window=10,
            window_duration=1.0,
        ),
        session=PytermSessionConfig(
            cancel_signal=cancel_signal,
            default_cols=80,
            default_rows=24,
            default_shell="/bin/bash",
        ),
    )
    return ControlConfig.from_pyterm_config(pyterm_config)


class TestControlConfig:
    """Tests for ControlConfig."""

    def test_standard_config(self):
        config = ControlConfig.standard()
        assert config.poll_interval == 0.1
        assert config.idle_timeout == 300.0
        assert config.response_timeout == 600.0
        assert config.cancel_signal == "\x03"

    def test_custom_config(self):
        config = create_test_config(
            poll_interval=0.5,
            idle_timeout=60.0,
            response_timeout=120.0,
            cancel_signal="\x1b",
        )
        assert config.poll_interval == 0.5
        assert config.idle_timeout == 60.0


class TestAgentController:
    """Tests for AgentController."""

    def test_init_with_config(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        assert controller.state == AgentState.IDLE
        assert controller.is_idle is True
        assert controller.is_paused is False
        assert len(controller.transcript) == 0

    def test_init_with_custom_config(self):
        session = MockSession()
        config = create_test_config(poll_interval=0.2)
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        assert controller._config.poll_interval == 0.2

    def test_state_property(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        assert controller.state == AgentState.IDLE
        controller._state_machine.force_transition(AgentState.THINKING)
        assert controller.state == AgentState.THINKING

    def test_is_idle_changes_after_transition(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        assert controller.is_idle is True
        controller._state_machine.force_transition(AgentState.THINKING)
        assert controller.is_idle is False

    def test_is_paused_changes_after_transition(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        assert controller.is_paused is False
        controller._state_machine.force_transition(AgentState.PAUSED)
        assert controller.is_paused is True


class TestStateCallbacks:
    """Tests for state change callbacks."""

    def test_on_state_change_callback(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        states = []

        def callback(old: AgentState, new: AgentState):
            states.append((old, new))

        controller.on_state_change(callback)
        controller._state_machine.transition(AgentState.THINKING)

        assert len(states) == 1
        assert states[0] == (AgentState.IDLE, AgentState.THINKING)

    def test_multiple_callbacks(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        count = {"value": 0}

        def callback1(old, new):
            count["value"] += 1

        def callback2(old, new):
            count["value"] += 10

        controller.on_state_change(callback1)
        controller.on_state_change(callback2)
        controller._state_machine.transition(AgentState.THINKING)

        assert count["value"] == 11


class TestResponseCallbacks:
    """Tests for response callbacks."""

    def test_on_response_callback(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        responses = []
        controller.on_response(lambda r: responses.append(r))

        # We can't easily test this without a full send_prompt
        # but we verify registration works
        assert len(controller._response_callbacks) == 1


class TestPauseResume:
    """Tests for pause/resume functionality."""

    def test_pause_from_idle(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        assert controller.pause()
        assert controller.is_paused
        assert controller._pause_requested.is_set()

    def test_resume_from_paused(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        controller.pause()
        assert controller.is_paused

        assert controller.resume()
        assert controller.is_idle
        assert not controller._pause_requested.is_set()

    def test_resume_when_not_paused(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        assert not controller.resume()


class TestCancel:
    """Tests for cancel functionality."""

    def test_cancel_sets_flag(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        controller.cancel()
        assert controller._cancel_requested.is_set()


class TestWaitForIdle:
    """Tests for wait_for_idle."""

    def test_wait_for_idle_when_already_idle(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        result = controller.wait_for_idle(timeout=1.0)
        assert result is True

    def test_wait_for_idle_times_out_when_not_idle(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)
        controller._state_machine.force_transition(AgentState.THINKING)

        # Verify state transition actually happened
        assert controller.state == AgentState.THINKING
        assert controller.is_idle is False

        result = controller.wait_for_idle(timeout=0.1)
        assert result is False


class TestGetCurrentOutput:
    """Tests for get_current_output."""

    def test_get_current_output(self):
        session = MockSession()
        session.set_output("Hello world")
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        parsed = controller.get_current_output()
        assert parsed.raw == "Hello world"


class TestAddToolResult:
    """Tests for add_tool_result."""

    def test_add_tool_result(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        # Create a turn first
        turn = controller.transcript.new_turn("Test prompt")
        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        turn.add_tool_call(tc)
        controller._tool_tracker.add_call(tc)

        # Add result
        controller.add_tool_result("tc1", "file1.txt", success=True)

        assert len(controller._tool_tracker.get_completed()) == 1
        assert len(turn.tool_results) == 1


class TestReset:
    """Tests for reset functionality."""

    def test_reset_clears_state(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        # Create some state
        controller.transcript.new_turn("Test")
        controller._state_machine.force_transition(AgentState.THINKING)
        controller._cancel_requested.set()

        # Reset
        controller.reset()

        assert controller.is_idle
        assert len(controller.transcript) == 0
        assert not controller._cancel_requested.is_set()


class TestSerialization:
    """Tests for to_dict serialization."""

    def test_to_dict(self):
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        d = controller.to_dict()

        assert d["state"] == "idle"
        assert d["is_idle"] == True
        assert d["is_paused"] == False
        assert "transcript" in d
        assert "tool_tracker" in d
        assert "state_machine" in d


class TestPromptResult:
    """Tests for PromptResult."""

    def test_prompt_result_creation(self):
        turn = Transcript().new_turn("Test")
        turn.complete(Message.assistant("Response"))

        result = PromptResult(
            turn=turn,
            final_state=AgentState.IDLE,
            duration_ms=1000,
        )

        assert result.turn == turn
        assert result.final_state == AgentState.IDLE
        assert result.duration_ms == 1000
        assert not result.was_cancelled
        assert result.error is None

    def test_prompt_result_cancelled(self):
        turn = Transcript().new_turn("Test")

        result = PromptResult(
            turn=turn,
            final_state=AgentState.ERROR,
            duration_ms=500,
            was_cancelled=True,
        )

        assert result.was_cancelled is True

    def test_prompt_result_to_dict(self):
        turn = Transcript().new_turn("Test")
        turn.complete(Message.assistant("Response"))

        result = PromptResult(
            turn=turn,
            final_state=AgentState.IDLE,
            duration_ms=1000,
        )

        d = result.to_dict()
        assert d["final_state"] == "idle"
        assert d["duration_ms"] == 1000
        assert d["was_cancelled"] is False
        assert d["response"] == "Response"
        assert d["tool_calls_count"] == 0


class TestSendPromptBasics:
    """Basic tests for send_prompt (without full agent simulation)."""

    def test_send_prompt_injects_text(self):
        session = MockSession()
        # Set output that simulates immediate idle with response
        session.set_output("> \nHello back!")

        config = create_test_config(poll_interval=0.01, response_timeout=0.5)
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        # Mock the parser to return idle state with response
        with patch.object(controller._parser, 'detect_state', return_value=AgentState.IDLE):
            with patch.object(controller._parser, 'parse_output') as mock_parse:
                from shared.pyterm.parsers import ParsedOutput
                mock_parse.return_value = ParsedOutput(
                    raw="> \nHello back!",
                    state=AgentState.IDLE,
                    assistant_response="Hello back!",
                    tool_calls=[],
                )

                result = controller.send_prompt("Hello")

                assert "Hello\n" in session.injected
                assert result.turn.prompt.content == "Hello"


class TestIntegration:
    """Integration tests for controller."""

    def test_full_flow_with_mocked_session(self):
        """Test a full conversation flow with mocked responses."""
        session = MockSession()
        config = create_test_config(poll_interval=0.01)
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        # Verify initial state
        assert controller.is_idle
        assert len(controller.transcript) == 0

        # Simulate state transitions
        controller._state_machine.transition(AgentState.THINKING)
        assert controller.state == AgentState.THINKING
        assert not controller.is_idle

        controller._state_machine.transition(AgentState.IDLE)
        assert controller.is_idle

    def test_transcript_access(self):
        """Test transcript property returns correct object."""
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        # Add turns directly to transcript
        turn1 = controller.transcript.new_turn("First")
        turn1.complete(Message.assistant("First response"))

        turn2 = controller.transcript.new_turn("Second")
        turn2.complete(Message.assistant("Second response"))

        assert len(controller.transcript) == 2
        assert controller.transcript.current_turn() == turn2

    def test_tool_tracker_access(self):
        """Test tool_tracker property returns correct object."""
        session = MockSession()
        config = ControlConfig.standard()
        parser = get_parser("claude_code")
        controller = AgentController(session, config=config, parser=parser)

        tc = ToolCall(id="tc1", name="bash", arguments={"command": "ls"})
        controller._tool_tracker.add_call(tc)

        assert controller.tool_tracker.total_calls == 1
        assert len(controller.tool_tracker.get_pending()) == 1
