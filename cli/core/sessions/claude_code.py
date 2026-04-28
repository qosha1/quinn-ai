"""
ClaudeCodeSession - SessionInterface implementation for Claude Code CLI.

Wraps shared/pyterm's AgentSession to provide the SessionInterface contract
expected by the Worker class.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

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
    TmuxSession,
)
from shared.pyterm.agent_state import AgentState
from shared.pyterm.protocols import PytermSessionState

if TYPE_CHECKING:
    from shared.pyterm.state_monitor import StateMonitor


class ClaudeCodeSession(SessionInterface):
    """
    SessionInterface implementation for Claude Code CLI.

    Uses shared/pyterm's AgentSession for the underlying terminal management,
    parsing, and state tracking. This class adapts that interface to the
    SessionInterface contract expected by cli/core/worker.py.

    Example:
        config = SessionConfig(
            worker_id="ceo",
            provider="claude_code",
            command="claude",
            args=["--dangerously-skip-permissions"],
        )
        session = ClaudeCodeSession(config, pyterm_config)
        session.start()
        result = session.send_prompt("Hello!")
        session.stop()
    """

    # Provider capabilities - used by registry and CLI commands
    CAPABILITIES = [
        "shell",
        "file_edit",
        "file_read",
        "web_search",
        "web_browse",
        "vision",
        "extended_thinking",
        "function_calling",
        "mcp",
        "multi_turn",
        "streaming",
        "code_interpreter",
        "git",
        "testing",
        "large_context",
        "context_caching",
    ]

    def __init__(self, config: SessionConfig, pyterm_config: Optional[PytermConfig] = None):
        """Initialize Claude Code session.

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
        return "claude_code"

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
        """Spawn the Claude Code CLI process via pyterm AgentSession."""
        try:
            session_name = f"{TMUX_SESSION_PREFIX}{self._config.worker_id}"

            # If a stale tmux session with this name exists from a previously
            # failed spawn, kill it. tmux new-session refuses to overwrite an
            # existing session, so without this the retry-after-failure path
            # always fails (quinn-ai-3tsi).
            if TmuxSession.exists(session_name):
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    f"Killing stale tmux session '{session_name}' before respawn"
                )
                import subprocess
                subprocess.run(
                    ["tmux", "kill-session", "-t", session_name],
                    capture_output=True,
                    check=False,
                )

            # Create AgentSession config
            agent_config = AgentSessionConfig.create(
                worker_id=self._config.worker_id,
                provider="claude_code",
                db_path=self._config.transcript_db_path,
                session_name=session_name,
                pyterm_config=self._pyterm_config,
            )

            # Create and start the agent session
            self._agent_session = AgentSession(agent_config)

            # Register callback to monitor agent state changes and update session state
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(
                f"[ClaudeCodeSession] Registering state change callback for worker "
                f"{self._config.worker_id}"
            )
            self._agent_session._controller.on_state_change(self._on_agent_state_change)
            logger.debug("[ClaudeCodeSession] Callback registered successfully")

            # Build shell command
            shell_cmd = self._config.command

            # Start with session config that includes our command and args
            from shared.pyterm.protocols import PytermSessionConfig
            session_config = PytermSessionConfig(
                shell=shell_cmd,
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
        """Terminate the Claude Code CLI process."""
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
        """Detect if Claude Code is ready for input."""
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

    def _create_state_monitor(self) -> Optional["StateMonitor"]:
        """Create Claude Code-specific state monitor.

        Returns:
            ClaudeCodeStateMonitor instance if agent session exists, None otherwise
        """
        from cli.core.sessions.monitors.claude_code import ClaudeCodeStateMonitor
        from shared.pyterm.state_monitor import StateMonitorConfig, MonitoringMode
        from cli.core.constants import (
            DEFAULT_STATE_POLL_INTERVAL,
            DEFAULT_STATE_IDLE_TIMEOUT,
            DEFAULT_STATE_ERROR_RETRY,
            DEFAULT_STATE_MAX_ERRORS,
        )

        # Session hasn't been created yet during __init__,
        # so we need to pass the underlying pyterm session once it exists
        # This is called from start() after _spawn_process()
        if not self._agent_session:
            return None

        config = StateMonitorConfig(
            mode=MonitoringMode.BACKGROUND,
            poll_interval=DEFAULT_STATE_POLL_INTERVAL,
            idle_timeout=DEFAULT_STATE_IDLE_TIMEOUT,
            error_retry_interval=DEFAULT_STATE_ERROR_RETRY,
            max_consecutive_errors=DEFAULT_STATE_MAX_ERRORS,
        )

        return ClaudeCodeStateMonitor(
            config=config,
            session=self._agent_session._session,
        )

    # =========================================================================
    # State mapping and monitoring
    # =========================================================================

    def _on_agent_state_change(self, old_state: AgentState, new_state: AgentState) -> None:
        """Callback for agent state changes - syncs to session state.

        This is called by pyterm's AgentController whenever the agent state changes.
        It maps agent states to session states and triggers session state transitions.

        Args:
            old_state: Previous agent state
            new_state: New agent state
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[ClaudeCodeSession] Agent state changed: {old_state} -> {new_state}")

        # Map new agent state to session state
        new_session_state = self._map_agent_state_to_session_state(new_state)
        logger.info(f"[ClaudeCodeSession] Mapped to session state: {new_session_state}, current: {self._state}")

        # Update session state if it differs from current
        if new_session_state != self._state:
            logger.info(f"[ClaudeCodeSession] Calling _set_state({new_session_state})")
            self._set_state(new_session_state)
        else:
            logger.info(f"[ClaudeCodeSession] State unchanged, skipping update")

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
