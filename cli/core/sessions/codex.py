"""
CodexSession - SessionInterface implementation for Codex CLI.

Wraps shared/pyterm's AgentSession to provide the SessionInterface contract
expected by the Worker class. Codex is an interactive AI coding assistant
CLI similar to Claude Code.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from cli.core.session import (
    SessionInterface,
    SessionConfig,
    SessionOutput,
    SessionState,
    SessionSpawnError,
    SessionTimeoutError,
)
from cli.core.constants import TMUX_SESSION_PREFIX

from shared.pyterm import (
    AgentSession,
    AgentSessionConfig,
    PytermConfig,
)
from shared.pyterm.agent_state import AgentState
from shared.pyterm.protocols import SessionState as PytermSessionState


class CodexSession(SessionInterface):
    """
    SessionInterface implementation for Codex CLI.

    Uses shared/pyterm's AgentSession for the underlying terminal management,
    parsing, and state tracking. This class adapts that interface to the
    SessionInterface contract expected by cli/core/worker.py.

    Codex is an interactive AI coding assistant similar to Claude Code,
    with its own CLI interface and interaction patterns.

    Example:
        config = SessionConfig(
            worker_id="alice",
            provider="codex",
            command="codex",
            args=["--dangerously-skip-permissions"],
        )
        session = CodexSession(config, pyterm_config)
        session.start()
        result = session.send_prompt("Hello!")
        session.stop()
    """

    def __init__(self, config: SessionConfig, pyterm_config: Optional[PytermConfig] = None):
        """Initialize Codex session.

        Args:
            config: SessionConfig with provider settings
            pyterm_config: Pyterm configuration for terminal behavior.
                          Defaults to PytermConfig.standard() if not provided.
        """
        super().__init__(config)

        self._pyterm_config = pyterm_config or PytermConfig.standard()

        # AgentSession will be created on start()
        self._agent_session: Optional[AgentSession] = None
        self._pid: Optional[int] = None

    # =========================================================================
    # Abstract property implementations
    # =========================================================================

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "codex"

    @property
    def pid(self) -> Optional[int]:
        """Process ID of the underlying CLI process."""
        return self._pid

    @property
    def platform_session_name(self) -> Optional[str]:
        """Tmux session name used for this session."""
        return f"{TMUX_SESSION_PREFIX}{self._config.worker_id}"

    # =========================================================================
    # Abstract method implementations
    # =========================================================================

    def _spawn_process(self) -> None:
        """Spawn the Codex CLI process via pyterm AgentSession."""
        try:
            # Create AgentSession config
            # Note: Codex uses a "generic" parser since we don't have a codex-specific parser yet
            agent_config = AgentSessionConfig.create(
                worker_id=self._config.worker_id,
                provider="generic",  # Use generic parser for Codex
                db_path=self._config.transcript_db_path,
                session_name=f"{TMUX_SESSION_PREFIX}{self._config.worker_id}",
                pyterm_config=self._pyterm_config,
            )

            # Create and start the agent session
            self._agent_session = AgentSession(agent_config)

            # Start with session config that includes our command and args
            from shared.pyterm.protocols import SessionConfig as PytermSessionConfig
            session_config = PytermSessionConfig(
                shell=self._config.command,
                args=self._config.args,
                cwd=str(self._config.working_directory) if self._config.working_directory else None,
                env=self._config.env_vars,
                cols=self._config.cols,
                rows=self._config.rows,
            )
            self._agent_session.start(session_config)

            # Try to get PID from tmux session
            try:
                self._pid = self._agent_session._session.pid
            except (AttributeError, TypeError):
                self._pid = None

        except Exception as e:
            raise SessionSpawnError(self._id, str(e))

    def _terminate_process(self, force: bool = False) -> None:
        """Terminate the Codex CLI process."""
        if self._agent_session:
            self._agent_session.stop(force=force)
            self._agent_session = None
        self._pid = None

    def _send_input(self, text: str) -> None:
        """Send text input to the CLI process."""
        if not self._agent_session:
            return
        # Use the underlying session's send method
        self._agent_session._session.send(text)

    def _read_output(self, timeout_ms: Optional[int] = None) -> SessionOutput:
        """Read output from the CLI process."""
        if not self._agent_session:
            return SessionOutput(content="", timestamp=datetime.now())

        # Get parsed output from controller
        parsed = self._agent_session.get_current_output()

        return SessionOutput(
            content=parsed.raw,
            timestamp=datetime.now(),
            is_complete=parsed.prompt_ready,
            tool_calls=[
                {"name": tc.name, "arguments": tc.arguments}
                for tc in parsed.tool_calls
            ],
            metadata={
                "state": parsed.state.value if parsed.state else None,
                "assistant_response": parsed.assistant_response,
                "error": parsed.error_message,
            },
        )

    def _detect_ready(self, output: str) -> bool:
        """Detect if Codex is ready for input."""
        if not self._agent_session:
            return False
        return self._agent_session.is_idle

    def _detect_completion(self, output: str) -> bool:
        """Detect if CLI has completed its response."""
        if not self._agent_session:
            return True
        # Completed when back to idle state
        return self._agent_session.is_idle

    def _get_context_usage(self) -> int:
        """Get current context token usage."""
        # pyterm doesn't track this directly yet
        return 0

    def _send_interrupt(self) -> None:
        """Send interrupt signal to CLI (Ctrl+C)."""
        if self._agent_session:
            self._agent_session.cancel()

    # =========================================================================
    # State mapping
    # =========================================================================

    def _map_pyterm_state_to_session_state(self, pyterm_state: PytermSessionState) -> SessionState:
        """Map pyterm session state to our SessionState."""
        mapping = {
            PytermSessionState.IDLE: SessionState.IDLE,
            PytermSessionState.RUNNING: SessionState.RUNNING,
            PytermSessionState.EXITED: SessionState.STOPPED,
            PytermSessionState.ERROR: SessionState.CRASHED,
        }
        return mapping.get(pyterm_state, SessionState.STOPPED)

    def _map_agent_state_to_session_state(self, agent_state: AgentState) -> SessionState:
        """Map pyterm agent state to our SessionState."""
        # Map agent states to session states
        if agent_state == AgentState.IDLE:
            return SessionState.IDLE
        elif agent_state in (AgentState.THINKING, AgentState.EXECUTING_TOOL, AgentState.WAITING_INPUT):
            return SessionState.RUNNING
        elif agent_state == AgentState.ERROR:
            return SessionState.CRASHED
        else:
            return SessionState.RUNNING

    # =========================================================================
    # Extended functionality
    # =========================================================================

    def get_transcript(self) -> list[dict]:
        """Get the conversation transcript.

        Returns:
            List of turn dictionaries with prompt/response pairs
        """
        if not self._agent_session:
            return []

        return self._agent_session.transcript.to_dict().get("turns", [])

    def get_tool_calls(self) -> list[dict]:
        """Get all tool calls from the session.

        Returns:
            List of tool call dictionaries
        """
        if not self._agent_session:
            return []

        return [
            {
                "id": tc.id,
                "name": tc.name,
                "arguments": tc.arguments,
                "result": tc.result,
                "status": tc.status.value if tc.status else None,
            }
            for tc in self._agent_session.get_tool_calls()
        ]

    @property
    def agent_session(self) -> Optional[AgentSession]:
        """Access the underlying AgentSession for advanced operations."""
        return self._agent_session
