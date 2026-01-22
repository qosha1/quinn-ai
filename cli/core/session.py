"""
Session abstraction interface for QuinnAI.

Session = Worker's Brain. One session, one worker. Unbreakable 1:1.

This module provides the abstract base class for CLI session management,
allowing QuinnAI to connect to ANY CLI-based AI agent (Claude Code, Codex CLI,
Gemini CLI, etc.) through a unified interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional
from pathlib import Path
import uuid


class SessionState(Enum):
    """Session lifecycle states.

    State machine: starting -> running <-> idle -> stopped
                              |
                              v
                           crashed
    """
    STARTING = "starting"   # Session initializing
    RUNNING = "running"     # Actively processing
    IDLE = "idle"           # Waiting for input
    STOPPED = "stopped"     # Gracefully shutdown
    CRASHED = "crashed"     # Unexpected termination


# Valid state transitions for session state machine
SESSION_STATE_TRANSITIONS: dict[SessionState, list[SessionState]] = {
    SessionState.STARTING: [SessionState.RUNNING, SessionState.CRASHED],
    SessionState.RUNNING: [SessionState.IDLE, SessionState.CRASHED],
    SessionState.IDLE: [SessionState.RUNNING, SessionState.STOPPED, SessionState.CRASHED],
    SessionState.STOPPED: [SessionState.STARTING],
    SessionState.CRASHED: [SessionState.STARTING, SessionState.STOPPED],
}


@dataclass(frozen=True)
class SessionId:
    """Unique session identifier.

    Combines worker_id with session instance for traceability.
    """
    worker_id: str
    instance_id: str  # UUID or timestamp-based

    def __str__(self) -> str:
        return f"{self.worker_id}:{self.instance_id}"

    def __hash__(self) -> int:
        return hash((self.worker_id, self.instance_id))

    @classmethod
    def create(cls, worker_id: str) -> "SessionId":
        """Create new session ID for a worker."""
        return cls(worker_id=worker_id, instance_id=uuid.uuid4().hex[:12])


@dataclass
class SessionConfig:
    """Configuration for spawning a session.

    All values explicit - no discovery, no defaults from environment.
    """
    # Worker binding (immutable after creation)
    worker_id: str

    # Provider settings
    provider: str               # e.g., "claude_code", "codex", "gemini"
    command: str                # Full path to CLI executable
    args: list[str] = field(default_factory=list)

    # Environment
    working_directory: Optional[Path] = None
    env_vars: dict[str, str] = field(default_factory=dict)

    # Terminal settings
    cols: int = 120
    rows: int = 40

    # Timeouts (milliseconds)
    startup_timeout_ms: int = 30000
    idle_timeout_ms: int = 300000    # 5 minutes
    response_timeout_ms: int = 600000  # 10 minutes

    # Resource limits
    max_context_tokens: int = 100000
    memory_limit_mb: Optional[int] = None

    # Session persistence
    persist_transcript: bool = True
    transcript_db_path: Optional[Path] = None


@dataclass
class SessionMetrics:
    """Runtime metrics for a session."""
    created_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None

    # Activity tracking
    last_activity: Optional[datetime] = None
    prompts_sent: int = 0
    responses_received: int = 0
    tokens_consumed: int = 0

    # Error tracking
    errors_count: int = 0
    last_error: Optional[str] = None

    # Resource usage
    peak_memory_mb: float = 0.0
    context_tokens_used: int = 0


@dataclass
class SessionOutput:
    """Output from a session."""
    content: str
    timestamp: datetime
    is_complete: bool = False
    tool_calls: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class PromptResult:
    """Result of sending a prompt to a session."""
    prompt: str
    response: SessionOutput
    duration_ms: int
    tokens_used: int
    turn_id: str


# =========================================================================
# Exceptions
# =========================================================================

class SessionError(Exception):
    """Base exception for session errors."""
    def __init__(self, session_id: SessionId, message: str):
        super().__init__(f"Session {session_id}: {message}")
        self.session_id = session_id


class SessionSpawnError(SessionError):
    """Failed to spawn session process."""
    def __init__(self, session_id: SessionId, cause: str):
        super().__init__(session_id, f"Failed to spawn: {cause}")
        self.cause = cause


class SessionAlreadyRunningError(SessionError):
    """Session is already running."""
    def __init__(self, session_id: SessionId):
        super().__init__(session_id, "Already running")


class SessionNotRunningError(SessionError):
    """Session is not running."""
    def __init__(self, session_id: SessionId, state: SessionState):
        super().__init__(session_id, f"Not running (state={state.value})")
        self.state = state


class SessionNotReadyError(SessionError):
    """Session is not ready for input."""
    def __init__(self, session_id: SessionId, state: SessionState):
        super().__init__(session_id, f"Not ready (state={state.value})")
        self.state = state


class SessionTimeoutError(SessionError):
    """Session operation timed out."""
    def __init__(self, session_id: SessionId, operation: str, timeout_ms: int):
        super().__init__(session_id, f"{operation} timed out after {timeout_ms}ms")
        self.operation = operation
        self.timeout_ms = timeout_ms


class SessionAlreadyBoundError(SessionError):
    """Session is already bound to a different worker."""
    def __init__(self, session_id: SessionId, current_worker: str, requested_worker: str):
        super().__init__(
            session_id,
            f"Already bound to worker '{current_worker}', cannot bind to '{requested_worker}'"
        )
        self.current_worker = current_worker
        self.requested_worker = requested_worker


class InvalidSessionStateTransition(Exception):
    """Invalid state transition attempted."""
    def __init__(self, current: SessionState, attempted: SessionState, valid: list[SessionState]):
        valid_names = [s.value for s in valid]
        super().__init__(
            f"Cannot transition from '{current.value}' to '{attempted.value}'. "
            f"Valid transitions: {valid_names}"
        )
        self.current = current
        self.attempted = attempted
        self.valid = valid


# =========================================================================
# SessionInterface - Abstract Base Class
# =========================================================================

class SessionInterface(ABC):
    """
    Abstract base class for CLI session management.

    ALL CLI adapters MUST implement this interface to ensure:
    1. Consistent lifecycle management
    2. Proper 1:1 worker binding
    3. Resource cleanup
    4. State tracking

    The session lifecycle:
        STARTING -> RUNNING <-> IDLE -> STOPPED
                       |
                       v
                    CRASHED

    Usage:
        session = ClaudeCodeSession(config)
        session.start()
        result = session.send_prompt("Hello")
        session.stop()
    """

    def __init__(self, config: SessionConfig):
        """Initialize session with configuration.

        Args:
            config: Session configuration (passed explicitly, not discovered)
        """
        self._config = config
        self._id = SessionId.create(config.worker_id)
        self._state = SessionState.STOPPED  # Start in STOPPED, transition to STARTING on start()
        self._metrics = SessionMetrics(created_at=datetime.now())
        self._bound_worker_id: Optional[str] = None

        # Callbacks
        self._state_callbacks: list[Callable[[SessionState, SessionState], None]] = []
        self._output_callbacks: list[Callable[[SessionOutput], None]] = []

    # =========================================================================
    # Properties - Immutable session identity
    # =========================================================================

    @property
    def id(self) -> SessionId:
        """Unique session identifier."""
        return self._id

    @property
    def config(self) -> SessionConfig:
        """Session configuration (read-only)."""
        return self._config

    @property
    def state(self) -> SessionState:
        """Current session state."""
        return self._state

    @property
    def metrics(self) -> SessionMetrics:
        """Session metrics (read-only snapshot)."""
        return self._metrics

    @property
    def bound_worker_id(self) -> Optional[str]:
        """Worker ID this session is bound to (immutable after binding)."""
        return self._bound_worker_id

    @property
    def is_alive(self) -> bool:
        """Check if session is in a running state."""
        return self._state in (SessionState.STARTING, SessionState.RUNNING, SessionState.IDLE)

    @property
    def is_ready(self) -> bool:
        """Check if session is ready to accept prompts."""
        return self._state == SessionState.IDLE

    # =========================================================================
    # Abstract Methods - Provider-specific implementation required
    # =========================================================================

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name (e.g., 'claude_code', 'codex', 'gemini')."""
        pass

    @property
    @abstractmethod
    def pid(self) -> Optional[int]:
        """Process ID of the underlying CLI process."""
        pass

    @abstractmethod
    def _spawn_process(self) -> None:
        """Spawn the underlying CLI process.

        Implementation must:
        1. Start the CLI subprocess
        2. Set up I/O streams
        3. Wait for CLI to be ready
        4. NOT change session state (caller handles)

        Raises:
            SessionSpawnError: If process cannot be started
        """
        pass

    @abstractmethod
    def _terminate_process(self, force: bool = False) -> None:
        """Terminate the underlying CLI process.

        Args:
            force: If True, kill immediately (SIGKILL). Otherwise graceful (SIGTERM).

        Implementation must:
        1. Send appropriate signal
        2. Clean up resources
        3. NOT change session state (caller handles)
        """
        pass

    @abstractmethod
    def _send_input(self, text: str) -> None:
        """Send text input to the CLI process.

        Args:
            text: Text to send (may include newlines)

        Raises:
            SessionNotRunningError: If session not in running state
        """
        pass

    @abstractmethod
    def _read_output(self, timeout_ms: Optional[int] = None) -> SessionOutput:
        """Read output from the CLI process.

        Args:
            timeout_ms: Timeout in milliseconds (None = use config default)

        Returns:
            SessionOutput with current content

        Raises:
            SessionTimeoutError: If timeout exceeded
            SessionNotRunningError: If session not running
        """
        pass

    @abstractmethod
    def _detect_ready(self, output: str) -> bool:
        """Detect if CLI is ready for input.

        Args:
            output: Current output text

        Returns:
            True if CLI is at prompt, False otherwise
        """
        pass

    @abstractmethod
    def _detect_completion(self, output: str) -> bool:
        """Detect if CLI has completed its response.

        Args:
            output: Current output text

        Returns:
            True if response is complete, False if still generating
        """
        pass

    @abstractmethod
    def _get_context_usage(self) -> int:
        """Get current context token usage.

        Returns:
            Number of tokens currently in context
        """
        pass

    @abstractmethod
    def _send_interrupt(self) -> None:
        """Send interrupt signal to CLI (e.g., Ctrl+C)."""
        pass

    # =========================================================================
    # State Machine Validation
    # =========================================================================

    def _validate_state_transition(self, new_state: SessionState) -> None:
        """Validate state transition.

        Args:
            new_state: Attempted new state

        Raises:
            InvalidSessionStateTransition: If transition is not allowed
        """
        valid = SESSION_STATE_TRANSITIONS.get(self._state, [])
        if new_state not in valid:
            raise InvalidSessionStateTransition(self._state, new_state, valid)

    def _set_state(self, new_state: SessionState) -> None:
        """Set state and notify callbacks."""
        if new_state != self._state:
            old_state = self._state
            self._state = new_state
            for cb in self._state_callbacks:
                try:
                    cb(old_state, new_state)
                except Exception:
                    pass  # Don't let callback errors break state machine

    # =========================================================================
    # Lifecycle Methods - Template pattern with hooks
    # =========================================================================

    def start(self) -> None:
        """Start the session.

        Transitions: STOPPED/CRASHED -> STARTING -> RUNNING -> IDLE

        Raises:
            SessionAlreadyRunningError: If session already started
            SessionSpawnError: If process cannot be started
        """
        if self._state in (SessionState.RUNNING, SessionState.IDLE, SessionState.STARTING):
            raise SessionAlreadyRunningError(self._id)

        self._validate_state_transition(SessionState.STARTING)
        self._set_state(SessionState.STARTING)
        self._metrics.started_at = datetime.now()

        try:
            self._spawn_process()
            self._validate_state_transition(SessionState.RUNNING)
            self._set_state(SessionState.RUNNING)

            # Wait for ready state
            self._wait_for_ready()
            self._validate_state_transition(SessionState.IDLE)
            self._set_state(SessionState.IDLE)
        except Exception as e:
            self._set_state(SessionState.CRASHED)
            self._metrics.errors_count += 1
            self._metrics.last_error = str(e)
            raise

    def stop(self, force: bool = False) -> None:
        """Stop the session gracefully.

        Transitions: RUNNING/IDLE -> STOPPED

        Args:
            force: If True, force kill without cleanup
        """
        if self._state in (SessionState.STOPPED,):
            return

        # Allow stopping from CRASHED without validation
        if self._state != SessionState.CRASHED:
            try:
                self._validate_state_transition(SessionState.STOPPED)
            except InvalidSessionStateTransition:
                # If we can't transition to STOPPED directly (e.g., from RUNNING),
                # we need to force it for cleanup
                pass

        try:
            self._terminate_process(force=force)
        finally:
            self._set_state(SessionState.STOPPED)
            self._metrics.stopped_at = datetime.now()

    def restart(self) -> None:
        """Restart the session.

        Equivalent to stop() + start().
        """
        self.stop(force=True)
        self.start()

    # =========================================================================
    # Communication Methods
    # =========================================================================

    def send_prompt(
        self,
        prompt: str,
        timeout_ms: Optional[int] = None,
        **metadata
    ) -> PromptResult:
        """Send a prompt and wait for response.

        Args:
            prompt: The prompt text to send
            timeout_ms: Override response timeout
            **metadata: Additional metadata to attach to result

        Returns:
            PromptResult with response

        Raises:
            SessionNotReadyError: If session not in IDLE state
            SessionTimeoutError: If response times out
        """
        if self._state != SessionState.IDLE:
            raise SessionNotReadyError(self._id, self._state)

        self._validate_state_transition(SessionState.RUNNING)
        self._set_state(SessionState.RUNNING)
        start_time = datetime.now()
        turn_id = f"turn-{self._metrics.prompts_sent + 1}"

        try:
            # Send the prompt
            self._send_input(prompt + "\n")
            self._metrics.prompts_sent += 1

            # Wait for completion
            timeout = timeout_ms or self._config.response_timeout_ms
            output = self._wait_for_completion(timeout)

            # Update metrics
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self._metrics.responses_received += 1
            self._metrics.last_activity = datetime.now()
            self._metrics.context_tokens_used = self._get_context_usage()

            return PromptResult(
                prompt=prompt,
                response=output,
                duration_ms=duration_ms,
                tokens_used=output.metadata.get("tokens", 0),
                turn_id=turn_id,
            )
        finally:
            self._validate_state_transition(SessionState.IDLE)
            self._set_state(SessionState.IDLE)

    def cancel(self) -> None:
        """Cancel current operation.

        Sends interrupt signal to CLI process.
        """
        if self._state == SessionState.RUNNING:
            self._send_interrupt()
            self._set_state(SessionState.IDLE)

    # =========================================================================
    # Worker Binding - Enforces 1:1 relationship
    # =========================================================================

    def bind_to_worker(self, worker_id: str) -> None:
        """Bind this session to a worker (one-time, immutable).

        Args:
            worker_id: Worker ID to bind to

        Raises:
            SessionAlreadyBoundError: If already bound to a different worker
        """
        if self._bound_worker_id is not None and self._bound_worker_id != worker_id:
            raise SessionAlreadyBoundError(self._id, self._bound_worker_id, worker_id)

        self._bound_worker_id = worker_id

    def verify_binding(self, worker_id: str) -> bool:
        """Verify this session is bound to the specified worker.

        Args:
            worker_id: Expected worker ID

        Returns:
            True if bound to this worker, False otherwise
        """
        return self._bound_worker_id == worker_id

    # =========================================================================
    # Callbacks
    # =========================================================================

    def on_state_change(self, callback: Callable[[SessionState, SessionState], None]) -> None:
        """Register callback for state changes."""
        self._state_callbacks.append(callback)

    def on_output(self, callback: Callable[[SessionOutput], None]) -> None:
        """Register callback for output events."""
        self._output_callbacks.append(callback)

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _wait_for_ready(self) -> None:
        """Wait for CLI to be ready for input."""
        timeout = self._config.startup_timeout_ms
        start = datetime.now()

        while True:
            output = self._read_output(timeout_ms=1000)
            if self._detect_ready(output.content):
                return

            elapsed = (datetime.now() - start).total_seconds() * 1000
            if elapsed > timeout:
                raise SessionTimeoutError(self._id, "startup", timeout)

    def _wait_for_completion(self, timeout_ms: int) -> SessionOutput:
        """Wait for CLI to complete its response."""
        start = datetime.now()
        accumulated = ""

        while True:
            output = self._read_output(timeout_ms=1000)
            accumulated = output.content

            for cb in self._output_callbacks:
                try:
                    cb(output)
                except Exception:
                    pass

            if self._detect_completion(accumulated):
                output.is_complete = True
                return output

            elapsed = (datetime.now() - start).total_seconds() * 1000
            if elapsed > timeout_ms:
                raise SessionTimeoutError(self._id, "response", timeout_ms)
