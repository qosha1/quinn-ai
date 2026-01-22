"""
AgentSession - Unified interface for AI agent terminal sessions.

Combines session management, state tracking, parsing, persistence,
and control operations into a single class.

This is the main entry point for controlling AI agents in pyterm.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from shared.pyterm.protocols import Session, SessionConfig, SessionState, WorkerState
from shared.pyterm.tmux_session import TmuxSession
from shared.pyterm.agent_state import AgentState, AgentStateMachine
from shared.pyterm.conversation import Transcript, Turn, Message, ToolCall
from shared.pyterm.control import (
    AgentController,
    ControlConfig,
    PromptResult,
    TimeoutError,
    CancelledError,
)
from shared.pyterm.parsers import OutputParser, ParsedOutput, get_parser
from shared.pyterm.persistence import TranscriptStore
from shared.pyterm.tools import ToolCallTracker
from shared.pyterm.config import PytermConfig


@dataclass
class AgentSessionConfig:
    """Configuration for an agent session."""

    worker_id: str
    pyterm_config: PytermConfig
    """Required pyterm configuration - no defaults."""

    session_name: str | None = None
    """Session name (auto-generated if not provided)."""

    provider: str = "claude_code"
    """Parser provider name."""

    db_path: Path | None = None
    """SQLite path for persistence."""

    auto_persist: bool = True
    """Auto-save transcript on changes."""

    @classmethod
    def create(
        cls,
        worker_id: str,
        provider: str = "claude_code",
        db_path: Path | str | None = None,
        session_name: str | None = None,
        auto_persist: bool = True,
        pyterm_config: PytermConfig | None = None,
    ) -> "AgentSessionConfig":
        """
        Factory method to create config with optional standard defaults.

        Args:
            worker_id: Unique identifier for this worker
            provider: AI provider to use
            db_path: Path to SQLite database
            session_name: Name for tmux session
            auto_persist: Whether to auto-save
            pyterm_config: Pyterm config (uses standard if None)
        """
        return cls(
            worker_id=worker_id,
            pyterm_config=pyterm_config or PytermConfig.standard(),
            session_name=session_name,
            provider=provider,
            db_path=Path(db_path) if db_path else None,
            auto_persist=auto_persist,
        )


class AgentSession:
    """
    Unified interface for AI agent terminal sessions.

    Provides:
    - Session lifecycle (start, stop, restart)
    - Prompt/response handling (send_prompt, cancel, pause/resume)
    - State tracking (idle, thinking, executing, etc.)
    - Transcript management (conversation history)
    - Persistence (SQLite storage)
    - Tool tracking

    Example usage:
        config = AgentSessionConfig.create("worker-1", provider="claude_code")
        session = AgentSession(config)
        session.start()

        result = session.send_prompt("Hello, how are you?")
        print(result.turn.response.content)

        session.stop()
    """

    def __init__(
        self,
        config: AgentSessionConfig,
        session: Session | None = None,
        parser: OutputParser | None = None,
    ):
        self._config = config
        self._worker_id = config.worker_id

        # Create or use provided session
        session_name = config.session_name or f"agent-{config.worker_id}"
        self._session = session or TmuxSession(
            session_name=session_name,
            config=config.pyterm_config,
        )

        # Create parser
        self._parser = parser or get_parser(config.provider)

        # Create controller with explicit config
        control_config = ControlConfig.from_pyterm_config(
            config.pyterm_config,
            parser=self._parser,
        )
        self._controller = AgentController(
            self._session,
            config=control_config,
            parser=self._parser,
        )

        # Persistence
        self._store: TranscriptStore | None = None
        if config.db_path:
            self._store = TranscriptStore(str(config.db_path))

        # Track if we need to persist
        self._needs_persist = False

        # Worker state tracking
        self._worker_state = WorkerState.PENDING

        # Register callback for auto-persist
        if config.auto_persist and self._store:
            self._controller.on_state_change(self._on_state_change_persist)

    @classmethod
    def create(
        cls,
        worker_id: str,
        provider: str = "claude_code",
        db_path: Path | str | None = None,
        session_name: str | None = None,
        auto_persist: bool = True,
        pyterm_config: PytermConfig | None = None,
    ) -> "AgentSession":
        """
        Factory method to create an AgentSession.

        Args:
            worker_id: Unique identifier for this worker
            provider: AI provider to use (claude_code, generic, etc.)
            db_path: Path to SQLite database for persistence
            session_name: Name for tmux session (auto-generated if not provided)
            auto_persist: Whether to auto-save transcript on changes
            pyterm_config: Pyterm configuration (uses standard if None)

        Returns:
            Configured AgentSession instance
        """
        config = AgentSessionConfig.create(
            worker_id=worker_id,
            provider=provider,
            db_path=db_path,
            session_name=session_name,
            auto_persist=auto_persist,
            pyterm_config=pyterm_config,
        )
        return cls(config)

    def _on_state_change_persist(self, old: AgentState, new: AgentState) -> None:
        """Callback to mark session as needing persistence."""
        # Mark for persist when completing a turn (back to idle)
        if new == AgentState.IDLE and old != AgentState.IDLE:
            self._needs_persist = True
            self._maybe_persist()

    def _maybe_persist(self) -> None:
        """Persist transcript if needed and auto_persist is enabled."""
        if self._needs_persist and self._store and self._config.auto_persist:
            self.save()
            self._needs_persist = False

    # =========================================================================
    # Session Lifecycle
    # =========================================================================

    def start(self, config: SessionConfig | None = None) -> None:
        """
        Start the agent session.

        Args:
            config: Optional session configuration
        """
        self._session.start(config)
        self._worker_state = WorkerState.ONBOARDING

    def stop(self, force: bool = False) -> None:
        """
        Stop the agent session.

        Args:
            force: If True, force kill the session
        """
        self._maybe_persist()
        self._worker_state = WorkerState.OFFBOARDING
        self._session.stop(force=force)
        self._worker_state = WorkerState.TERMINATED

    def restart(self, config: SessionConfig | None = None) -> None:
        """
        Restart the agent session.

        Stops the current session (if running) and starts a new one.
        """
        if self._session.state == SessionState.RUNNING:
            self.stop()
        self.start(config)

    @property
    def is_running(self) -> bool:
        """Check if the session is running."""
        return self._session.state == SessionState.RUNNING

    @property
    def session_state(self) -> SessionState:
        """Get the session state."""
        return self._session.state

    # =========================================================================
    # Worker State
    # =========================================================================

    @property
    def worker_state(self) -> WorkerState:
        """Get the worker lifecycle state."""
        return self._worker_state

    def activate(self) -> bool:
        """
        Transition worker to ACTIVE state.

        Returns True if transition was valid.
        """
        if self._worker_state == WorkerState.ONBOARDING:
            self._worker_state = WorkerState.ACTIVE
            return True
        return False

    def begin_offboarding(self) -> bool:
        """
        Begin worker offboarding.

        Returns True if transition was valid.
        """
        if self._worker_state == WorkerState.ACTIVE:
            self._worker_state = WorkerState.OFFBOARDING
            return True
        return False

    # =========================================================================
    # Agent State
    # =========================================================================

    @property
    def state(self) -> AgentState:
        """Current agent state (idle, thinking, executing, etc.)."""
        return self._controller.state

    @property
    def is_idle(self) -> bool:
        """Check if agent is idle and ready for input."""
        return self._controller.is_idle

    @property
    def is_paused(self) -> bool:
        """Check if agent is paused."""
        return self._controller.is_paused

    # =========================================================================
    # Prompt/Response Operations
    # =========================================================================

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
            timeout: Max seconds to wait for response
            **metadata: Additional metadata for the turn

        Returns:
            PromptResult with turn details and response

        Raises:
            TimeoutError: If response times out
            CancelledError: If cancelled during execution
        """
        result = self._controller.send_prompt(prompt, timeout=timeout, **metadata)
        self._needs_persist = True
        self._maybe_persist()
        return result

    def cancel(self) -> None:
        """Cancel the current operation."""
        self._controller.cancel()

    def pause(self) -> bool:
        """
        Pause the agent.

        Returns True if successfully paused.
        """
        return self._controller.pause()

    def resume(self) -> bool:
        """
        Resume the agent from paused state.

        Returns True if successfully resumed.
        """
        return self._controller.resume()

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        """
        Block until agent is idle.

        Args:
            timeout: Max seconds to wait

        Returns:
            True if agent became idle, False if timed out
        """
        return self._controller.wait_for_idle(timeout)

    # =========================================================================
    # Output Inspection
    # =========================================================================

    def get_current_output(self) -> ParsedOutput:
        """Get and parse the current session output."""
        return self._controller.get_current_output()

    def get_raw_output(self) -> str:
        """Get the raw session output without parsing."""
        return self._session.extract().text

    # =========================================================================
    # Transcript & History
    # =========================================================================

    @property
    def transcript(self) -> Transcript:
        """Get the conversation transcript."""
        return self._controller.transcript

    def get_messages(self) -> list[Message]:
        """Get all messages from the transcript."""
        return self._controller.transcript.get_messages()

    def get_turn(self, turn_id: str) -> Turn | None:
        """Get a specific turn by ID."""
        return self._controller.transcript.get_turn(turn_id)

    def current_turn(self) -> Turn | None:
        """Get the current (most recent) turn."""
        return self._controller.transcript.current_turn()

    # =========================================================================
    # Tool Tracking
    # =========================================================================

    @property
    def tool_tracker(self) -> ToolCallTracker:
        """Get the tool call tracker."""
        return self._controller.tool_tracker

    def get_tool_calls(self) -> list[ToolCall]:
        """Get all tool calls from the transcript."""
        return self._controller.transcript.get_tool_calls()

    # =========================================================================
    # Persistence
    # =========================================================================

    def save(self) -> bool:
        """
        Save the transcript to the database.

        Returns True if saved successfully, False if no database configured.
        """
        if not self._store:
            return False
        self._store.save_transcript(self._worker_id, self._controller.transcript)
        return True

    def load(self) -> bool:
        """
        Load transcript from the database.

        Returns True if loaded successfully, False if not found or no database.
        """
        if not self._store:
            return False
        transcript = self._store.load_transcript(self._worker_id)
        if transcript:
            # Replace current transcript
            self._controller._transcript = transcript
            return True
        return False

    def delete_history(self) -> bool:
        """
        Delete saved transcript from the database.

        Returns True if deleted, False if no database configured.
        """
        if not self._store:
            return False
        self._store.delete_transcript(self._worker_id)
        return True

    # =========================================================================
    # Callbacks
    # =========================================================================

    def on_state_change(self, callback: Callable[[AgentState, AgentState], None]) -> None:
        """Register callback for state changes."""
        self._controller.on_state_change(callback)

    def on_response(self, callback: Callable[[ParsedOutput], None]) -> None:
        """Register callback for output updates during prompt processing."""
        self._controller.on_response(callback)

    # =========================================================================
    # Reset & Cleanup
    # =========================================================================

    def reset(self) -> None:
        """Reset the session state (transcript, tool tracker, state machine)."""
        self._controller.reset()
        self._needs_persist = False

    def clear_transcript(self) -> None:
        """Clear the transcript but keep the session running."""
        self._controller.transcript.clear()
        self._needs_persist = True
        self._maybe_persist()

    # =========================================================================
    # Serialization
    # =========================================================================

    @property
    def worker_id(self) -> str:
        """Get the worker ID."""
        return self._worker_id

    @property
    def provider(self) -> str:
        """Get the provider name."""
        return self._parser.provider_name

    def to_dict(self) -> dict:
        """Serialize session state to dict."""
        return {
            "worker_id": self._worker_id,
            "provider": self.provider,
            "session_state": self._session.state.value,
            "worker_state": self._worker_state.value,
            "agent_state": self.state.value,
            "is_idle": self.is_idle,
            "is_paused": self.is_paused,
            "is_running": self.is_running,
            "transcript": self._controller.transcript.to_dict(),
            "tool_tracker": self._controller.tool_tracker.to_dict(),
            "has_persistence": self._store is not None,
        }

    # =========================================================================
    # Context Manager
    # =========================================================================

    def __enter__(self) -> "AgentSession":
        """Context manager entry - starts the session."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - stops the session."""
        self.stop()
