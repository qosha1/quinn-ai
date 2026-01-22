"""
Tests for pyterm agent state machine.
"""

import pytest
import time
from datetime import datetime

from shared.pyterm.agent_state import (
    AgentState,
    AgentStateMachine,
    VALID_AGENT_TRANSITIONS,
    agent_state_from_output,
)


class TestAgentState:
    """Tests for AgentState enum."""

    def test_all_states_defined(self):
        """Verify all expected states are defined."""
        expected_states = {"idle", "thinking", "executing_tool", "waiting_input", "error", "paused"}
        actual_states = {s.value for s in AgentState}
        assert actual_states == expected_states

    def test_state_values(self):
        """Test state enum values."""
        assert AgentState.IDLE.value == "idle"
        assert AgentState.THINKING.value == "thinking"
        assert AgentState.EXECUTING_TOOL.value == "executing_tool"
        assert AgentState.WAITING_INPUT.value == "waiting_input"
        assert AgentState.ERROR.value == "error"
        assert AgentState.PAUSED.value == "paused"


class TestValidTransitions:
    """Tests for VALID_AGENT_TRANSITIONS dictionary."""

    def test_all_states_have_transitions(self):
        """Every state should have an entry in the transitions dict."""
        for state in AgentState:
            assert state in VALID_AGENT_TRANSITIONS

    def test_idle_transitions(self):
        """Test valid transitions from IDLE."""
        valid = VALID_AGENT_TRANSITIONS[AgentState.IDLE]
        assert AgentState.THINKING in valid
        assert AgentState.PAUSED in valid
        assert AgentState.ERROR in valid
        # Should not transition to self or certain states
        assert AgentState.IDLE not in valid
        assert AgentState.EXECUTING_TOOL not in valid

    def test_thinking_transitions(self):
        """Test valid transitions from THINKING."""
        valid = VALID_AGENT_TRANSITIONS[AgentState.THINKING]
        assert AgentState.IDLE in valid
        assert AgentState.EXECUTING_TOOL in valid
        assert AgentState.WAITING_INPUT in valid
        assert AgentState.PAUSED in valid
        assert AgentState.ERROR in valid

    def test_executing_tool_transitions(self):
        """Test valid transitions from EXECUTING_TOOL."""
        valid = VALID_AGENT_TRANSITIONS[AgentState.EXECUTING_TOOL]
        assert AgentState.THINKING in valid
        assert AgentState.IDLE in valid
        assert AgentState.WAITING_INPUT in valid
        assert AgentState.PAUSED in valid
        assert AgentState.ERROR in valid

    def test_waiting_input_transitions(self):
        """Test valid transitions from WAITING_INPUT."""
        valid = VALID_AGENT_TRANSITIONS[AgentState.WAITING_INPUT]
        assert AgentState.THINKING in valid
        assert AgentState.EXECUTING_TOOL in valid
        assert AgentState.IDLE in valid
        assert AgentState.PAUSED in valid
        assert AgentState.ERROR in valid

    def test_error_transitions(self):
        """Test valid transitions from ERROR."""
        valid = VALID_AGENT_TRANSITIONS[AgentState.ERROR]
        assert AgentState.IDLE in valid
        assert AgentState.PAUSED in valid
        # Error should be somewhat restricted
        assert AgentState.THINKING not in valid

    def test_paused_transitions(self):
        """Test valid transitions from PAUSED (can resume to most states)."""
        valid = VALID_AGENT_TRANSITIONS[AgentState.PAUSED]
        assert AgentState.IDLE in valid
        assert AgentState.THINKING in valid
        assert AgentState.EXECUTING_TOOL in valid
        assert AgentState.WAITING_INPUT in valid
        assert AgentState.ERROR in valid


class TestAgentStateMachine:
    """Tests for AgentStateMachine class."""

    def test_initial_state(self):
        """State machine starts in IDLE state."""
        sm = AgentStateMachine()
        assert sm.state == AgentState.IDLE

    def test_state_property(self):
        """Test state property returns current state."""
        sm = AgentStateMachine()
        assert sm.state == AgentState.IDLE
        sm.transition(AgentState.THINKING)
        assert sm.state == AgentState.THINKING

    def test_valid_transition(self):
        """Test valid transition returns True."""
        sm = AgentStateMachine()
        result = sm.transition(AgentState.THINKING)
        assert result is True
        assert sm.state == AgentState.THINKING

    def test_invalid_transition(self):
        """Test invalid transition returns False and state unchanged."""
        sm = AgentStateMachine()
        # Cannot go directly from IDLE to EXECUTING_TOOL
        result = sm.transition(AgentState.EXECUTING_TOOL)
        assert result is False
        assert sm.state == AgentState.IDLE

    def test_can_transition(self):
        """Test can_transition method."""
        sm = AgentStateMachine()
        assert sm.can_transition(AgentState.THINKING) is True
        assert sm.can_transition(AgentState.EXECUTING_TOOL) is False
        assert sm.can_transition(AgentState.PAUSED) is True

    def test_get_valid_transitions(self):
        """Test get_valid_transitions returns correct list."""
        sm = AgentStateMachine()
        valid = sm.get_valid_transitions()
        assert AgentState.THINKING in valid
        assert AgentState.PAUSED in valid
        assert AgentState.ERROR in valid

    def test_state_sequence(self):
        """Test a sequence of state transitions."""
        sm = AgentStateMachine()

        # IDLE -> THINKING
        assert sm.transition(AgentState.THINKING)
        assert sm.state == AgentState.THINKING

        # THINKING -> EXECUTING_TOOL
        assert sm.transition(AgentState.EXECUTING_TOOL)
        assert sm.state == AgentState.EXECUTING_TOOL

        # EXECUTING_TOOL -> THINKING
        assert sm.transition(AgentState.THINKING)
        assert sm.state == AgentState.THINKING

        # THINKING -> IDLE
        assert sm.transition(AgentState.IDLE)
        assert sm.state == AgentState.IDLE


class TestStateDuration:
    """Tests for state duration tracking."""

    def test_state_duration_initial(self):
        """Test state_duration returns a value."""
        sm = AgentStateMachine()
        # Should be very small since we just created it
        assert sm.state_duration >= 0
        assert sm.state_duration < 1.0  # Less than 1 second

    def test_state_duration_ms(self):
        """Test state_duration_ms returns milliseconds."""
        sm = AgentStateMachine()
        assert sm.state_duration_ms >= 0
        assert isinstance(sm.state_duration_ms, int)

    def test_state_duration_increases(self):
        """Test that state duration increases over time."""
        sm = AgentStateMachine()
        initial = sm.state_duration
        time.sleep(0.05)  # 50ms
        after = sm.state_duration
        assert after > initial

    def test_state_duration_resets_on_transition(self):
        """Test that state duration resets after transition."""
        sm = AgentStateMachine()
        time.sleep(0.05)  # 50ms
        initial_duration = sm.state_duration

        sm.transition(AgentState.THINKING)

        # Duration should be very small after transition
        new_duration = sm.state_duration
        assert new_duration < initial_duration

    def test_state_entered_at(self):
        """Test state_entered_at timestamp."""
        sm = AgentStateMachine()
        initial_time = sm.state_entered_at
        assert isinstance(initial_time, datetime)

        time.sleep(0.01)
        sm.transition(AgentState.THINKING)

        new_time = sm.state_entered_at
        assert new_time > initial_time


class TestCallbacks:
    """Tests for callback functionality."""

    def test_on_change_callback(self):
        """Test on_change callback is called."""
        sm = AgentStateMachine()
        changes = []

        def record_change(old: AgentState, new: AgentState):
            changes.append((old, new))

        sm.on_change(record_change)
        sm.transition(AgentState.THINKING)

        assert len(changes) == 1
        assert changes[0] == (AgentState.IDLE, AgentState.THINKING)

    def test_multiple_on_change_callbacks(self):
        """Test multiple on_change callbacks."""
        sm = AgentStateMachine()
        calls1 = []
        calls2 = []

        sm.on_change(lambda o, n: calls1.append((o, n)))
        sm.on_change(lambda o, n: calls2.append((o, n)))

        sm.transition(AgentState.THINKING)

        assert len(calls1) == 1
        assert len(calls2) == 1

    def test_on_enter_callback(self):
        """Test on_enter callback is called."""
        sm = AgentStateMachine()
        entered = []

        sm.on_enter(AgentState.THINKING, lambda s: entered.append(s))
        sm.transition(AgentState.THINKING)

        assert len(entered) == 1
        assert entered[0] == AgentState.THINKING

    def test_on_enter_callback_only_for_specific_state(self):
        """Test on_enter callback only fires for specified state."""
        sm = AgentStateMachine()
        entered = []

        sm.on_enter(AgentState.EXECUTING_TOOL, lambda s: entered.append(s))
        sm.transition(AgentState.THINKING)  # Not EXECUTING_TOOL

        assert len(entered) == 0

    def test_on_exit_callback(self):
        """Test on_exit callback is called."""
        sm = AgentStateMachine()
        exited = []

        sm.on_exit(AgentState.IDLE, lambda s: exited.append(s))
        sm.transition(AgentState.THINKING)

        assert len(exited) == 1
        assert exited[0] == AgentState.IDLE

    def test_callback_order(self):
        """Test callbacks fire in correct order: exit -> change -> enter."""
        sm = AgentStateMachine()
        order = []

        sm.on_exit(AgentState.IDLE, lambda s: order.append("exit"))
        sm.on_change(lambda o, n: order.append("change"))
        sm.on_enter(AgentState.THINKING, lambda s: order.append("enter"))

        sm.transition(AgentState.THINKING)

        assert order == ["exit", "change", "enter"]

    def test_no_callbacks_on_invalid_transition(self):
        """Test callbacks don't fire on invalid transition."""
        sm = AgentStateMachine()
        changes = []

        sm.on_change(lambda o, n: changes.append((o, n)))
        sm.transition(AgentState.EXECUTING_TOOL)  # Invalid from IDLE

        assert len(changes) == 0


class TestForceTransition:
    """Tests for force_transition method."""

    def test_force_transition_bypasses_validation(self):
        """Test force_transition ignores invalid transition rules."""
        sm = AgentStateMachine()
        # Cannot normally go IDLE -> EXECUTING_TOOL
        assert not sm.can_transition(AgentState.EXECUTING_TOOL)

        sm.force_transition(AgentState.EXECUTING_TOOL)
        assert sm.state == AgentState.EXECUTING_TOOL

    def test_force_transition_fires_callbacks(self):
        """Test force_transition still fires callbacks."""
        sm = AgentStateMachine()
        changes = []

        sm.on_change(lambda o, n: changes.append((o, n)))
        sm.force_transition(AgentState.EXECUTING_TOOL)

        assert len(changes) == 1
        assert changes[0] == (AgentState.IDLE, AgentState.EXECUTING_TOOL)

    def test_force_transition_updates_timestamp(self):
        """Test force_transition updates state timestamp."""
        sm = AgentStateMachine()
        time.sleep(0.01)
        old_time = sm.state_entered_at

        sm.force_transition(AgentState.EXECUTING_TOOL)

        assert sm.state_entered_at > old_time


class TestTransitionHistory:
    """Tests for transition history tracking."""

    def test_empty_history_initially(self):
        """Test history is empty on new state machine."""
        sm = AgentStateMachine()
        assert sm.transition_history == []

    def test_history_records_transitions(self):
        """Test history records each transition."""
        sm = AgentStateMachine()
        sm.transition(AgentState.THINKING)
        sm.transition(AgentState.IDLE)

        history = sm.transition_history
        assert len(history) == 2

        # First transition
        assert history[0][0] == AgentState.IDLE
        assert history[0][1] == AgentState.THINKING

        # Second transition
        assert history[1][0] == AgentState.THINKING
        assert history[1][1] == AgentState.IDLE

    def test_history_includes_timestamps(self):
        """Test history includes timestamps."""
        sm = AgentStateMachine()
        sm.transition(AgentState.THINKING)

        history = sm.transition_history
        assert len(history) == 1
        assert isinstance(history[0][2], datetime)

    def test_history_returns_copy(self):
        """Test transition_history returns a copy."""
        sm = AgentStateMachine()
        sm.transition(AgentState.THINKING)

        history1 = sm.transition_history
        history1.append(("fake", "entry", datetime.now()))

        history2 = sm.transition_history
        assert len(history2) == 1  # Original not modified


class TestHelperMethods:
    """Tests for helper methods."""

    def test_is_active(self):
        """Test is_active method."""
        sm = AgentStateMachine()

        assert sm.is_active() is False  # IDLE

        sm.transition(AgentState.THINKING)
        assert sm.is_active() is True

        sm.transition(AgentState.EXECUTING_TOOL)
        assert sm.is_active() is True

        sm.transition(AgentState.WAITING_INPUT)
        assert sm.is_active() is True

        sm.transition(AgentState.IDLE)
        assert sm.is_active() is False

    def test_is_idle(self):
        """Test is_idle method."""
        sm = AgentStateMachine()
        assert sm.is_idle() is True

        sm.transition(AgentState.THINKING)
        assert sm.is_idle() is False

    def test_is_paused(self):
        """Test is_paused method."""
        sm = AgentStateMachine()
        assert sm.is_paused() is False

        sm.transition(AgentState.PAUSED)
        assert sm.is_paused() is True

    def test_is_error(self):
        """Test is_error method."""
        sm = AgentStateMachine()
        assert sm.is_error() is False

        sm.transition(AgentState.ERROR)
        assert sm.is_error() is True

    def test_reset(self):
        """Test reset method."""
        sm = AgentStateMachine()
        sm.transition(AgentState.THINKING)
        sm.transition(AgentState.EXECUTING_TOOL)

        assert sm.state != AgentState.IDLE
        assert len(sm.transition_history) == 2

        sm.reset()

        assert sm.state == AgentState.IDLE
        assert len(sm.transition_history) == 0


class TestSerialization:
    """Tests for serialization."""

    def test_to_dict(self):
        """Test to_dict method."""
        sm = AgentStateMachine()
        d = sm.to_dict()

        assert d["state"] == "idle"
        assert "state_entered_at" in d
        assert "state_duration_ms" in d
        assert d["is_active"] is False
        assert "idle" not in d["valid_transitions"]  # Can't transition to self
        assert "thinking" in d["valid_transitions"]
        assert d["transition_count"] == 0

    def test_to_dict_after_transitions(self):
        """Test to_dict after some transitions."""
        sm = AgentStateMachine()
        sm.transition(AgentState.THINKING)
        sm.transition(AgentState.EXECUTING_TOOL)

        d = sm.to_dict()

        assert d["state"] == "executing_tool"
        assert d["is_active"] is True
        assert d["transition_count"] == 2


class TestOutputDetection:
    """Tests for agent_state_from_output function."""

    def test_detect_error_state(self):
        """Test detecting error patterns."""
        assert agent_state_from_output("Error: file not found") == AgentState.ERROR
        assert agent_state_from_output("Exception: connection failed") == AgentState.ERROR
        assert agent_state_from_output("Traceback (most recent call last)") == AgentState.ERROR
        assert agent_state_from_output("FATAL: cannot continue") == AgentState.ERROR

    def test_detect_waiting_input(self):
        """Test detecting input waiting patterns."""
        assert agent_state_from_output("Continue? (Y/n)") == AgentState.WAITING_INPUT
        assert agent_state_from_output("Press Enter to continue") == AgentState.WAITING_INPUT
        assert agent_state_from_output("Proceed? [y/n]") == AgentState.WAITING_INPUT
        assert agent_state_from_output("Confirm deletion") == AgentState.WAITING_INPUT

    def test_detect_executing_tool(self):
        """Test detecting tool execution patterns."""
        assert agent_state_from_output("Executing command...") == AgentState.EXECUTING_TOOL
        assert agent_state_from_output("Running command: ls -la") == AgentState.EXECUTING_TOOL
        assert agent_state_from_output("Reading file /tmp/x") == AgentState.EXECUTING_TOOL
        assert agent_state_from_output("Bash: running npm install") == AgentState.EXECUTING_TOOL

    def test_detect_thinking(self):
        """Test detecting thinking patterns."""
        assert agent_state_from_output("Thinking...") == AgentState.THINKING
        assert agent_state_from_output("Processing your request") == AgentState.THINKING
        assert agent_state_from_output("Analyzing the code") == AgentState.THINKING

    def test_detect_idle(self):
        """Test detecting idle/prompt patterns."""
        assert agent_state_from_output("some output\n$ ") == AgentState.IDLE
        assert agent_state_from_output(">>> ") == AgentState.IDLE
        assert agent_state_from_output("Ready for input") == AgentState.IDLE

    def test_unknown_output(self):
        """Test returns None for unrecognized output."""
        assert agent_state_from_output("Hello world") is None
        assert agent_state_from_output("Just some text") is None
        assert agent_state_from_output("") is None


class TestIntegration:
    """Integration tests for agent state machine."""

    def test_full_conversation_flow(self):
        """Test a complete conversation state flow."""
        sm = AgentStateMachine()
        states_visited = []

        sm.on_change(lambda o, n: states_visited.append(n))

        # User sends input
        assert sm.transition(AgentState.THINKING)

        # Agent decides to execute a tool
        assert sm.transition(AgentState.EXECUTING_TOOL)

        # Tool needs user confirmation
        assert sm.transition(AgentState.WAITING_INPUT)

        # User confirms, continue execution
        assert sm.transition(AgentState.EXECUTING_TOOL)

        # Tool complete, back to thinking
        assert sm.transition(AgentState.THINKING)

        # Response complete
        assert sm.transition(AgentState.IDLE)

        assert states_visited == [
            AgentState.THINKING,
            AgentState.EXECUTING_TOOL,
            AgentState.WAITING_INPUT,
            AgentState.EXECUTING_TOOL,
            AgentState.THINKING,
            AgentState.IDLE,
        ]

    def test_error_recovery_flow(self):
        """Test error state and recovery."""
        sm = AgentStateMachine()

        # User sends input
        sm.transition(AgentState.THINKING)

        # Error occurs
        sm.transition(AgentState.ERROR)
        assert sm.is_error()

        # Recover to idle
        sm.transition(AgentState.IDLE)
        assert sm.is_idle()

    def test_pause_resume_flow(self):
        """Test pause and resume functionality."""
        sm = AgentStateMachine()

        # Start working
        sm.transition(AgentState.THINKING)
        sm.transition(AgentState.EXECUTING_TOOL)

        # External pause
        sm.transition(AgentState.PAUSED)
        assert sm.is_paused()

        # Resume to where we were
        sm.transition(AgentState.EXECUTING_TOOL)
        assert sm.state == AgentState.EXECUTING_TOOL

    def test_output_driven_transitions(self):
        """Test using output detection to drive transitions."""
        sm = AgentStateMachine()

        # Simulate output-driven state changes
        outputs = [
            "Processing your request...",  # THINKING
            "Running command: ls",  # EXECUTING_TOOL
            "Continue? (Y/n)",  # WAITING_INPUT
            "Running command: rm -rf",  # EXECUTING_TOOL
            "Done!\n$ ",  # IDLE
        ]

        expected_states = [
            AgentState.THINKING,
            AgentState.EXECUTING_TOOL,
            AgentState.WAITING_INPUT,
            AgentState.EXECUTING_TOOL,
            AgentState.IDLE,
        ]

        for output, expected in zip(outputs, expected_states):
            detected = agent_state_from_output(output)
            if detected and sm.can_transition(detected):
                sm.transition(detected)
                assert sm.state == expected

    def test_state_machine_with_conversation_turn(self):
        """Test state machine usage pattern with a conversation turn."""
        sm = AgentStateMachine()

        # Simulating a turn lifecycle
        # 1. Start turn - transition to THINKING
        turn_started = datetime.now()
        sm.transition(AgentState.THINKING)

        # 2. Tool call - transition to EXECUTING_TOOL
        sm.transition(AgentState.EXECUTING_TOOL)
        tool_start = sm.state_entered_at

        # 3. Tool complete - back to THINKING
        time.sleep(0.01)
        sm.transition(AgentState.THINKING)

        # 4. Response complete - back to IDLE
        sm.transition(AgentState.IDLE)
        turn_ended = datetime.now()

        # Verify history captures the flow
        history = sm.transition_history
        assert len(history) == 4

        # Verify we can calculate total turn time
        total_time = (turn_ended - turn_started).total_seconds()
        assert total_time > 0

        # Verify tool execution time was tracked
        assert tool_start > turn_started
