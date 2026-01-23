"""
Agent control operations.

High-level operations for controlling AI agents:
- send_prompt: Send a prompt and wait for response
- cancel: Cancel current operation
- wait_for_idle: Block until agent is idle
- pause/resume: Pause and resume agent
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from shared.pyterm.protocols import Session, ExtractedOutput
from shared.pyterm.agent_state import AgentState, AgentStateMachine
from shared.pyterm.conversation import Transcript, Turn, Message, ToolCall, ToolResult
from shared.pyterm.parsers import OutputParser, ParsedOutput
from shared.pyterm.tools import ToolCallTracker
from shared.pyterm.config import PytermConfig


@dataclass
class ControlConfig:
    """
    Configuration for agent control operations.

    Wraps PytermConfig to provide backward compatibility while
    using the centralized configuration.
    """

    pyterm_config: PytermConfig
    """The underlying pyterm configuration."""

    parser: OutputParser | None = None
    """Parser to use (if None, must be provided to AgentController)."""

    @classmethod
    def from_pyterm_config(
        cls,
        config: PytermConfig,
        parser: OutputParser | None = None,
    ) -> "ControlConfig":
        """Create ControlConfig from PytermConfig."""
        return cls(pyterm_config=config, parser=parser)

    @classmethod
    def standard(cls, parser: OutputParser | None = None) -> "ControlConfig":
        """Create ControlConfig with standard pyterm settings."""
        return cls(pyterm_config=PytermConfig.standard(), parser=parser)

    @property
    def poll_interval(self) -> float:
        """Seconds between output polls."""
        return self.pyterm_config.timing.poll_interval

    @property
    def idle_timeout(self) -> float:
        """Max seconds to wait for idle."""
        return self.pyterm_config.timing.idle_timeout

    @property
    def response_timeout(self) -> float:
        """Max seconds to wait for response."""
        return self.pyterm_config.timing.response_timeout

    @property
    def cancel_signal(self) -> str:
        """Signal to send for cancellation."""
        return self.pyterm_config.session.cancel_signal


class TimeoutError(Exception):
    """Raised when an operation times out."""

    pass


class CancelledError(Exception):
    """Raised when an operation is cancelled."""

    pass


@dataclass
class PromptResult:
    """Result of sending a prompt to the agent."""

    turn: Turn
    final_state: AgentState
    duration_ms: int
    was_cancelled: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn.id,
            "final_state": self.final_state.value,
            "duration_ms": self.duration_ms,
            "was_cancelled": self.was_cancelled,
            "error": self.error,
            "response": self.turn.response.content if self.turn.response else None,
            "tool_calls_count": len(self.turn.tool_calls),
        }


ResponseCallback = Callable[[ParsedOutput], None]
StateChangeCallback = Callable[[AgentState, AgentState], None]


class AgentController:
    """
    High-level controller for AI agents.

    Provides operations like send_prompt, cancel, wait_for_idle
    that work with the underlying session and state machine.
    """

    def __init__(
        self,
        session: Session,
        config: ControlConfig,
        parser: OutputParser,
    ):
        """
        Initialize the agent controller.

        Args:
            session: The underlying session
            config: Control configuration (required - no defaults)
            parser: Output parser (required - no defaults)
        """
        self._session = session
        self._config = config
        self._parser = parser

        self._state_machine = AgentStateMachine()
        self._transcript = Transcript()
        self._tool_tracker = ToolCallTracker()

        self._cancel_requested = threading.Event()
        self._pause_requested = threading.Event()
        self._lock = threading.RLock()

        # Callbacks
        self._response_callbacks: list[ResponseCallback] = []
        self._state_callbacks: list[StateChangeCallback] = []

        # Register state callback
        self._state_machine.on_change(self._handle_state_change)

    @property
    def state(self) -> AgentState:
        """Current agent state."""
        return self._state_machine.state

    @property
    def transcript(self) -> Transcript:
        """Conversation transcript."""
        return self._transcript

    @property
    def tool_tracker(self) -> ToolCallTracker:
        """Tool call tracker."""
        return self._tool_tracker

    @property
    def is_idle(self) -> bool:
        """Check if agent is idle."""
        return self._state_machine.is_idle()

    @property
    def is_paused(self) -> bool:
        """Check if agent is paused."""
        return self._state_machine.is_paused()

    def on_response(self, callback: ResponseCallback) -> None:
        """Register callback for output updates."""
        with self._lock:
            self._response_callbacks.append(callback)

    def on_state_change(self, callback: StateChangeCallback) -> None:
        """Register callback for state changes."""
        with self._lock:
            self._state_callbacks.append(callback)

    def _handle_state_change(self, old: AgentState, new: AgentState) -> None:
        """Internal state change handler."""
        # Copy callback list to avoid race condition during iteration
        with self._lock:
            callbacks = list(self._state_callbacks)
        for cb in callbacks:
            cb(old, new)

    def send_prompt(
        self,
        prompt: str,
        timeout: float | None = None,
        **metadata,
    ) -> PromptResult:
        """
        Send a prompt to the agent and wait for response.

        Args:
            prompt: The prompt text to send
            timeout: Max seconds to wait (default from config)
            **metadata: Additional metadata for the turn

        Returns:
            PromptResult with the turn and final state

        Raises:
            TimeoutError: If response times out
            CancelledError: If cancelled during execution
        """
        timeout = timeout or self._config.response_timeout

        with self._lock:
            # Create new turn
            turn = self._transcript.new_turn(prompt, **metadata)
            start_time = time.time()

            # Reset cancel flag
            self._cancel_requested.clear()

            # Transition to thinking
            if self._state_machine.can_transition(AgentState.THINKING):
                self._state_machine.transition(AgentState.THINKING)

            # Send prompt to session
            self._session.inject(prompt + "\n")

            # Poll for completion with hard iteration limit to prevent infinite loops
            # Max iterations = timeout / poll_interval * 2 (with some margin)
            max_iterations = int((timeout / self._config.poll_interval) * 2) + 100
            last_output = ""
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # Check for cancellation
                if self._cancel_requested.is_set():
                    self._handle_cancel(turn)
                    duration_ms = int((time.time() - start_time) * 1000)
                    return PromptResult(
                        turn=turn,
                        final_state=self.state,
                        duration_ms=duration_ms,
                        was_cancelled=True,
                    )

                # Check for pause
                while self._pause_requested.is_set():
                    time.sleep(self._config.poll_interval)
                    if self._cancel_requested.is_set():
                        break

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    # Clear cancel flag on timeout to prevent next operation from failing
                    self._cancel_requested.clear()
                    self._state_machine.force_transition(AgentState.ERROR)
                    turn.complete(Message.assistant(""))
                    raise TimeoutError(
                        f"Response timed out after {elapsed:.1f}s"
                    )

                # Extract and parse output
                output = self._session.extract()
                if output.text != last_output:
                    last_output = output.text
                    parsed = self._parser.parse_output(output.text)

                    # Update state from output
                    detected_state = self._parser.detect_state(output.text)
                    if detected_state and self._state_machine.can_transition(detected_state):
                        self._state_machine.transition(detected_state)

                    # Process tool calls
                    for tc in parsed.tool_calls:
                        if not self._tool_tracker.get_call(tc.id):
                            turn.add_tool_call(tc)
                            self._tool_tracker.add_call(tc)

                    # Notify callbacks - copy list to avoid race condition
                    callbacks = list(self._response_callbacks)
                    for cb in callbacks:
                        cb(parsed)

                    # Check if complete (back to idle with response)
                    if detected_state == AgentState.IDLE and parsed.assistant_response:
                        response = Message.assistant(parsed.assistant_response)
                        turn.complete(response)
                        duration_ms = int((time.time() - start_time) * 1000)
                        return PromptResult(
                            turn=turn,
                            final_state=self.state,
                            duration_ms=duration_ms,
                        )

                time.sleep(self._config.poll_interval)

            # Exceeded max iterations - treat as timeout
            self._cancel_requested.clear()
            self._state_machine.force_transition(AgentState.ERROR)
            turn.complete(Message.assistant(""))
            raise TimeoutError(
                f"Response exceeded max iterations ({max_iterations})"
            )

    def _handle_cancel(self, turn: Turn) -> None:
        """Handle cancellation of current operation."""
        # Send cancel signal
        self._session.inject(self._config.cancel_signal)

        # Transition to error state
        if self._state_machine.can_transition(AgentState.ERROR):
            self._state_machine.transition(AgentState.ERROR)

        # Complete turn with empty response
        if not turn.is_complete:
            turn.complete(Message.assistant(""))

    def cancel(self) -> None:
        """Cancel the current operation."""
        self._cancel_requested.set()

    def pause(self) -> bool:
        """
        Pause the agent.

        Returns True if successfully paused.
        """
        if not self._state_machine.can_transition(AgentState.PAUSED):
            return False

        self._pause_requested.set()
        self._state_machine.transition(AgentState.PAUSED)
        return True

    def resume(self) -> bool:
        """
        Resume the agent from paused state.

        Returns True if successfully resumed.
        """
        if not self.is_paused:
            return False

        self._pause_requested.clear()

        # Transition back to idle
        if self._state_machine.can_transition(AgentState.IDLE):
            self._state_machine.transition(AgentState.IDLE)
            return True

        return False

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        """
        Block until agent is idle.

        Args:
            timeout: Max seconds to wait (default from config)

        Returns:
            True if agent became idle, False if timed out
        """
        timeout = timeout or self._config.idle_timeout
        start_time = time.time()

        while not self.is_idle:
            if time.time() - start_time > timeout:
                return False
            time.sleep(self._config.poll_interval)

        return True

    def get_current_output(self) -> ParsedOutput:
        """Get and parse the current session output."""
        output = self._session.extract()
        return self._parser.parse_output(output.text)

    def add_tool_result(self, tool_call_id: str, output: str, success: bool = True, error: str | None = None) -> None:
        """
        Add a tool result to the current turn.

        This is called when the controller observes a tool result in the output.
        """
        result = ToolResult(
            tool_call_id=tool_call_id,
            output=output,
            success=success,
            error=error,
        )
        self._tool_tracker.add_result(result)

        current = self._transcript.current_turn()
        if current and not current.is_complete:
            current.add_tool_result(result)

    def reset(self) -> None:
        """Reset the controller state."""
        self._state_machine.reset()
        self._transcript.clear()
        self._tool_tracker.clear()
        self._cancel_requested.clear()
        self._pause_requested.clear()

    def to_dict(self) -> dict:
        """Serialize controller state to dict."""
        return {
            "state": self.state.value,
            "is_idle": self.is_idle,
            "is_paused": self.is_paused,
            "transcript": self._transcript.to_dict(),
            "tool_tracker": self._tool_tracker.to_dict(),
            "state_machine": self._state_machine.to_dict(),
        }
