"""
Agent State Machine for AI agent sessions.

Tracks the state of an AI agent during conversation:
- IDLE: Agent is at prompt, waiting for input
- THINKING: Agent is processing, generating response
- EXECUTING_TOOL: Agent is running a tool (bash, read, etc)
- WAITING_INPUT: Agent is waiting for user input (Y/n prompt, etc)
- ERROR: Agent encountered an error
- PAUSED: Agent is paused by external control
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent activity states during a session."""

    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING_TOOL = "executing_tool"
    WAITING_INPUT = "waiting_input"
    ERROR = "error"
    PAUSED = "paused"


# Valid state transitions
# Key: current state, Value: list of valid next states
VALID_AGENT_TRANSITIONS: dict[AgentState, list[AgentState]] = {
    AgentState.IDLE: [
        AgentState.THINKING,  # User sends input
        AgentState.PAUSED,  # External pause
        AgentState.ERROR,  # Session error
    ],
    AgentState.THINKING: [
        AgentState.IDLE,  # Response complete, back to prompt
        AgentState.EXECUTING_TOOL,  # Agent calls a tool
        AgentState.WAITING_INPUT,  # Agent needs user confirmation
        AgentState.PAUSED,  # External pause
        AgentState.ERROR,  # Processing error
    ],
    AgentState.EXECUTING_TOOL: [
        AgentState.THINKING,  # Tool complete, continue processing
        AgentState.IDLE,  # Tool complete, response done
        AgentState.WAITING_INPUT,  # Tool needs user input
        AgentState.PAUSED,  # External pause
        AgentState.ERROR,  # Tool error
    ],
    AgentState.WAITING_INPUT: [
        AgentState.THINKING,  # User provided input
        AgentState.EXECUTING_TOOL,  # Continue with tool after input
        AgentState.IDLE,  # User cancelled/declined
        AgentState.PAUSED,  # External pause
        AgentState.ERROR,  # Input error
    ],
    AgentState.ERROR: [
        AgentState.IDLE,  # Error recovered, back to prompt
        AgentState.PAUSED,  # Pause for investigation
    ],
    AgentState.PAUSED: [
        AgentState.IDLE,  # Resume to idle
        AgentState.THINKING,  # Resume to thinking
        AgentState.EXECUTING_TOOL,  # Resume to tool execution
        AgentState.WAITING_INPUT,  # Resume to waiting input
        AgentState.ERROR,  # Error during pause
    ],
}


# Callback type aliases
AgentStateChangeCallback = Callable[[AgentState, AgentState], None]
AgentStateEnterCallback = Callable[[AgentState], None]
AgentStateExitCallback = Callable[[AgentState], None]


@dataclass
class AgentStateMachine:
    """
    State machine for tracking agent activity state.

    Manages state transitions with validation and callbacks.
    Tracks duration in each state for metrics.

    Thread-safe: Uses a lock to protect state modifications.
    """

    _state: AgentState = AgentState.IDLE
    _state_entered_at: datetime = field(default_factory=datetime.now)
    _on_change: list[AgentStateChangeCallback] = field(default_factory=list)
    _on_enter: dict[AgentState, list[AgentStateEnterCallback]] = field(
        default_factory=dict
    )
    _on_exit: dict[AgentState, list[AgentStateExitCallback]] = field(
        default_factory=dict
    )
    _transition_history: list[tuple[AgentState, AgentState, datetime]] = field(
        default_factory=list
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def state(self) -> AgentState:
        """Current agent state."""
        with self._lock:
            return self._state

    @property
    def state_duration(self) -> float:
        """Time in seconds since entering current state."""
        with self._lock:
            delta = datetime.now() - self._state_entered_at
        return delta.total_seconds()

    @property
    def state_duration_ms(self) -> int:
        """Time in milliseconds since entering current state."""
        return int(self.state_duration * 1000)

    @property
    def state_entered_at(self) -> datetime:
        """Timestamp when current state was entered."""
        with self._lock:
            return self._state_entered_at

    @property
    def transition_history(self) -> list[tuple[AgentState, AgentState, datetime]]:
        """History of state transitions (old_state, new_state, timestamp)."""
        with self._lock:
            return list(self._transition_history)

    def can_transition(self, new_state: AgentState) -> bool:
        """Check if transition to new_state is valid from current state."""
        with self._lock:
            return new_state in VALID_AGENT_TRANSITIONS.get(self._state, [])

    def transition(self, new_state: AgentState) -> bool:
        """
        Transition to a new state.

        Returns True if transition was valid, False otherwise.
        Fires hooks in order: exit(old) -> change(old, new) -> enter(new)

        Thread-safe: State changes are atomic, callbacks called outside lock.
        """
        with self._lock:
            if not self.can_transition(new_state):
                return False

            old_state = self._state
            transition_time = datetime.now()

            # Copy callbacks to invoke outside lock
            exit_callbacks = list(self._on_exit.get(old_state, []))
            change_callbacks = list(self._on_change)
            enter_callbacks = list(self._on_enter.get(new_state, []))

            # Update state and timestamp atomically
            self._state = new_state
            self._state_entered_at = transition_time

            # Record in history
            self._transition_history.append((old_state, new_state, transition_time))

        # Fire callbacks outside lock (with error isolation)
        for cb in exit_callbacks:
            try:
                cb(old_state)
            except Exception as e:
                logger.warning(f"State exit callback failed: {e}")

        for cb in change_callbacks:
            try:
                cb(old_state, new_state)
            except Exception as e:
                logger.warning(f"State change callback failed: {e}")

        for cb in enter_callbacks:
            try:
                cb(new_state)
            except Exception as e:
                logger.warning(f"State enter callback failed: {e}")

        return True

    def force_transition(self, new_state: AgentState) -> None:
        """
        Force transition to a new state, bypassing validation.

        Use sparingly - primarily for error recovery or initialization.
        Still fires all callbacks.

        Thread-safe: State changes are atomic, callbacks called outside lock.
        """
        with self._lock:
            old_state = self._state
            transition_time = datetime.now()

            # Copy callbacks to invoke outside lock
            exit_callbacks = list(self._on_exit.get(old_state, []))
            change_callbacks = list(self._on_change)
            enter_callbacks = list(self._on_enter.get(new_state, []))

            # Update state and timestamp atomically
            self._state = new_state
            self._state_entered_at = transition_time

            # Record in history (marked as forced)
            self._transition_history.append((old_state, new_state, transition_time))

        # Fire callbacks outside lock (with error isolation)
        for cb in exit_callbacks:
            try:
                cb(old_state)
            except Exception as e:
                logger.warning(f"State exit callback failed: {e}")

        for cb in change_callbacks:
            try:
                cb(old_state, new_state)
            except Exception as e:
                logger.warning(f"State change callback failed: {e}")

        for cb in enter_callbacks:
            try:
                cb(new_state)
            except Exception as e:
                logger.warning(f"State enter callback failed: {e}")

    def on_change(self, callback: AgentStateChangeCallback) -> None:
        """Register callback for any state change."""
        if not callable(callback):
            raise TypeError("Callback must be callable")
        with self._lock:
            self._on_change.append(callback)

    def on_enter(self, state: AgentState, callback: AgentStateEnterCallback) -> None:
        """Register callback for entering a specific state."""
        if not callable(callback):
            raise TypeError("Callback must be callable")
        with self._lock:
            if state not in self._on_enter:
                self._on_enter[state] = []
            self._on_enter[state].append(callback)

    def on_exit(self, state: AgentState, callback: AgentStateExitCallback) -> None:
        """Register callback for exiting a specific state."""
        if not callable(callback):
            raise TypeError("Callback must be callable")
        with self._lock:
            if state not in self._on_exit:
                self._on_exit[state] = []
            self._on_exit[state].append(callback)

    def reset(self) -> None:
        """Reset to initial IDLE state (for testing)."""
        with self._lock:
            self._state = AgentState.IDLE
            self._state_entered_at = datetime.now()
            self._transition_history.clear()

    def is_active(self) -> bool:
        """Check if agent is in an active (non-idle, non-paused) state."""
        with self._lock:
            return self._state in (
                AgentState.THINKING,
                AgentState.EXECUTING_TOOL,
                AgentState.WAITING_INPUT,
            )

    def is_idle(self) -> bool:
        """Check if agent is idle (ready for input)."""
        with self._lock:
            return self._state == AgentState.IDLE

    def is_paused(self) -> bool:
        """Check if agent is paused."""
        with self._lock:
            return self._state == AgentState.PAUSED

    def is_error(self) -> bool:
        """Check if agent is in error state."""
        with self._lock:
            return self._state == AgentState.ERROR

    def get_valid_transitions(self) -> list[AgentState]:
        """Get list of valid states to transition to from current state."""
        with self._lock:
            return list(VALID_AGENT_TRANSITIONS.get(self._state, []))

    def to_dict(self) -> dict:
        """Serialize current state to dictionary."""
        with self._lock:
            return {
                "state": self._state.value,
                "state_entered_at": self._state_entered_at.isoformat(),
                "state_duration_ms": self.state_duration_ms,
                "is_active": self._state in (
                    AgentState.THINKING,
                    AgentState.EXECUTING_TOOL,
                    AgentState.WAITING_INPUT,
                ),
                "valid_transitions": [s.value for s in VALID_AGENT_TRANSITIONS.get(self._state, [])],
                "transition_count": len(self._transition_history),
            }


def agent_state_from_output(output: str) -> AgentState | None:
    """
    Detect agent state from session output.

    This is a heuristic-based detection for common patterns.
    Returns None if state cannot be determined.

    Integration point: Used by session output parsing to detect state changes.
    """
    # Keep original for prompt detection (prompts have trailing spaces)
    output_lower = output.lower()
    output_stripped = output_lower.strip()

    # Error patterns
    error_patterns = [
        "error:",
        "exception:",
        "failed:",
        "traceback",
        "panic:",
        "fatal:",
    ]
    if any(pattern in output_stripped for pattern in error_patterns):
        return AgentState.ERROR

    # Waiting for input patterns (Y/n prompts, confirmations)
    input_patterns = [
        "(y/n)",
        "[y/n]",
        "press enter",
        "continue?",
        "proceed?",
        "confirm",
        "waiting for input",
        "type your",
    ]
    if any(pattern in output_stripped for pattern in input_patterns):
        return AgentState.WAITING_INPUT

    # Tool execution patterns
    tool_patterns = [
        "executing",
        "running command",
        "reading file",
        "writing file",
        "searching",
        "bash:",
        "tool:",
    ]
    if any(pattern in output_stripped for pattern in tool_patterns):
        return AgentState.EXECUTING_TOOL

    # Thinking patterns (common AI response indicators)
    thinking_patterns = [
        "thinking",
        "processing",
        "analyzing",
        "generating",
        "...",
    ]
    if any(pattern in output_stripped for pattern in thinking_patterns):
        return AgentState.THINKING

    # Prompt patterns (ready for input) - check the end of original output
    # These patterns indicate the agent is at a prompt waiting for input
    prompt_patterns_with_space = ["$ ", "> ", ">>> "]
    prompt_patterns_exact = ["claude>", "assistant>"]
    prompt_keywords = ["ready"]

    # Check if output ends with a prompt pattern (with trailing space)
    last_chars = output_lower[-50:] if len(output_lower) >= 50 else output_lower
    if any(pattern in last_chars for pattern in prompt_patterns_with_space):
        return AgentState.IDLE

    # Check for exact prompt patterns at end (stripped)
    if any(output_stripped.endswith(pattern) for pattern in prompt_patterns_exact):
        return AgentState.IDLE

    # Check for keywords indicating ready state
    if any(keyword in output_stripped for keyword in prompt_keywords):
        return AgentState.IDLE

    return None
