"""SessionInterface — abstract base class for CLI session management.

The 25+-method ABC that every session adapter (claude_code, codex,
gemini, openai) implements. Errors live in .exceptions, value-object
types in .types, SessionConfig + PromptResult re-exported from
shared.core.session via .__init__.
"""

import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

from shared.core.session import SessionConfig, PromptResult
from shared.core.state import SessionState, SESSION_STATE_TRANSITIONS

from .exceptions import (
    InvalidSessionStateTransition,
    SessionAlreadyBoundError,
    SessionAlreadyRunningError,
    SessionError,
    SessionNotReadyError,
    SessionNotRunningError,
    SessionTimeoutError,
)
from .types import SessionId, SessionMetrics, SessionOutput

if TYPE_CHECKING:
    from shared.pyterm.state_monitor import StateMonitor


_logger = logging.getLogger(__name__)


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
        # Get provider-specific adapter from registry
        registry = get_default_registry()
        session = registry.create(provider_name, config, pyterm_config=pyterm_config)
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
        self._state_version = 0  # Version for optimistic locking
        self._state_lock = threading.RLock()  # Protects state transitions
        self._metrics = SessionMetrics(created_at=datetime.now())
        self._bound_worker_id: Optional[str] = None

        # Callbacks
        self._state_callbacks: list[Callable[[SessionState, SessionState], None]] = []
        self._output_callbacks: list[Callable[[SessionOutput], None]] = []

        # State monitor (created during start() via factory method)
        self._state_monitor: Optional["StateMonitor"] = None

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
        with self._state_lock:
            return self._state

    @property
    def state_version(self) -> int:
        """State version for optimistic locking."""
        with self._state_lock:
            return self._state_version

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

    @property
    def platform_session_name(self) -> Optional[str]:
        """Platform-specific session identifier (e.g., tmux session name).

        Override in subclasses that use platform-specific session management.
        Returns None by default for sessions without platform identifiers.
        """
        return None

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

    @abstractmethod
    def _create_state_monitor(self) -> Optional["StateMonitor"]:
        """Factory method for provider-specific state monitor.

        Returns:
            StateMonitor instance, or None if provider doesn't support monitoring

        Called during start() to create the monitor with appropriate config.
        Subclasses should construct their provider-specific monitor here.
        """
        pass

    # =========================================================================
    # State Machine Validation (Thread-Safe)
    # =========================================================================

    def _validate_state_transition(self, new_state: SessionState) -> None:
        """Validate state transition.

        Thread-safe: acquires state lock.

        Args:
            new_state: Attempted new state

        Raises:
            InvalidSessionStateTransition: If transition is not allowed
        """
        with self._state_lock:
            valid = SESSION_STATE_TRANSITIONS.get(self._state, [])
            if new_state not in valid:
                raise InvalidSessionStateTransition(self._state, new_state, valid)

    def _set_state(self, new_state: SessionState) -> None:
        """Set state and notify callbacks.

        Thread-safe: acquires state lock for the state change,
        then releases before calling callbacks.
        """
        with self._state_lock:
            if new_state == self._state:
                return
            old_state = self._state
            self._state = new_state
            self._state_version += 1
            callbacks = list(self._state_callbacks)  # Copy to release lock

        # Call callbacks outside lock to prevent deadlocks
        for cb in callbacks:
            try:
                cb(old_state, new_state)
            except (TypeError, ValueError, RuntimeError, OSError) as e:
                # Intentionally swallowed: callback errors must not break state machine.
                # State transitions are critical; callbacks are observers only.
                _logger.warning(f"State callback error (ignored): {e}")
                pass

    def _on_monitored_state_change(self, old, new) -> None:
        """Callback from state monitor - update our state.

        This bridges the state monitor to the session's state management,
        ensuring database updates happen when monitor detects changes.

        State monitors emit PytermSessionState (terminal-lifecycle:
        IDLE/RUNNING/EXITED/ERROR), which we translate to SessionState
        (worker-lifecycle: STOPPED/STARTING/IDLE/RUNNING/CRASHED). Without
        this translation, _set_state stores a PytermSessionState into
        self._state, after which SESSION_STATE_TRANSITIONS.get(self._state)
        returns [] (the dict is keyed on SessionState) and the next
        validate_state_transition crashes with 'Valid transitions: []'.
        Closes quinn-ai-mcef.

        Args:
            old: Previous state from monitor (PytermSessionState or SessionState)
            new: New state detected by monitor (PytermSessionState or SessionState)
        """
        from shared.pyterm.protocols import PytermSessionState

        if isinstance(new, PytermSessionState):
            mapping = {
                PytermSessionState.IDLE: SessionState.IDLE,
                PytermSessionState.RUNNING: SessionState.RUNNING,
                PytermSessionState.EXITED: SessionState.STOPPED,
                PytermSessionState.ERROR: SessionState.CRASHED,
            }
            new = mapping.get(new, SessionState.CRASHED)

        if new != self._state:
            self._set_state(new)

    def _atomic_transition(
        self,
        expected_state: SessionState,
        new_state: SessionState,
        expected_version: Optional[int] = None,
    ) -> bool:
        """Atomically transition state if current state matches expected.

        This provides optimistic locking semantics - the transition only
        succeeds if the current state (and optionally version) matches
        the expected values.

        Args:
            expected_state: The state we expect to transition from
            new_state: The state to transition to
            expected_version: Optional version to match (for stricter locking)

        Returns:
            True if transition succeeded, False if state didn't match

        Raises:
            InvalidSessionStateTransition: If the transition is not valid
        """
        with self._state_lock:
            # Check expected state
            if self._state != expected_state:
                return False

            # Check version if provided
            if expected_version is not None and self._state_version != expected_version:
                return False

            # Validate transition
            valid = SESSION_STATE_TRANSITIONS.get(self._state, [])
            if new_state not in valid:
                raise InvalidSessionStateTransition(self._state, new_state, valid)

            # Perform transition
            old_state = self._state
            self._state = new_state
            self._state_version += 1
            callbacks = list(self._state_callbacks)

        # Call callbacks outside lock
        for cb in callbacks:
            try:
                cb(old_state, new_state)
            except (TypeError, ValueError, RuntimeError, OSError) as e:
                # Intentionally swallowed: callback errors must not break state machine.
                _logger.warning(f"State callback error (ignored): {e}")
                pass

        return True

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

            # Create and start state monitor
            self._state_monitor = self._create_state_monitor()
            if self._state_monitor:
                self._state_monitor.subscribe(self._on_monitored_state_change)
                self._state_monitor.start_monitoring()

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
            # Stop state monitoring first
            if self._state_monitor:
                self._state_monitor.stop_monitoring()

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
                except (TypeError, ValueError, RuntimeError, OSError) as e:
                    # Intentionally swallowed: callback errors must not break output streaming.
                    _logger.warning(f"Output callback error (ignored): {e}")
                    pass

            if self._detect_completion(accumulated):
                output.is_complete = True
                return output

            elapsed = (datetime.now() - start).total_seconds() * 1000
            if elapsed > timeout_ms:
                raise SessionTimeoutError(self._id, "response", timeout_ms)
