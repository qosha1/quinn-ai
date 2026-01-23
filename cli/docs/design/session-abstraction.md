# Session Abstraction Layer Design

## Overview

The Session Abstraction Layer provides a unified interface for QuinnAI to connect to ANY CLI-based AI agent (Claude Code, Codex CLI, Gemini CLI, etc.). This layer enforces the sacred contract: **"Session = Worker's Brain. One session, one worker. Unbreakable 1:1."**

### Design Principles

1. **Session = Worker's Brain**: One session, one worker. Session ON = awake. Session OFF = asleep.
2. **Interface-First Design**: Design for 10 providers even if you have 1.
3. **No Provider Lock-in**: Our Interface -> Provider Adapter -> [Any CLI]
4. **No String Dispatch**: Use polymorphism, not `if provider == "x"`
5. **No Magic Values**: All configuration explicit, passed at startup.
6. **No Module Side Effects**: Nothing runs at import except definitions.

---

## 1. SessionInterface - Abstract Base Class

All CLI adapters MUST implement this interface. The interface defines the contract between QuinnAI and any AI CLI session.

```python
"""
Session abstraction interface for QuinnAI.

Session = Worker's Brain. One session, one worker. Unbreakable 1:1.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, TypeVar, Generic
from pathlib import Path


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
```

### Session State vs Worker Runtime State

**Important**: SessionState and worker runtime_status are the SAME thing at different layers:

| Layer | Location | Values |
|-------|----------|--------|
| Session (in-memory) | `SessionInterface._state` | SessionState enum |
| Worker (database) | `worker_state.runtime_status` | String: starting, running, idle, stopped, crashed |

**Synchronization**: The `SessionStateSync` class (`cli/core/sessions/state_sync.py`) automatically
synchronizes session state changes to the database. When a session transitions (e.g., IDLE → RUNNING),
the corresponding worker's `runtime_status` is updated.

**Why both?**
- **SessionState**: In-memory, used by session implementations for lifecycle management
- **runtime_status**: Persisted, survives process crashes, enables cross-process visibility (e.g., board UI)

**State machine (identical for both)**:
```
STOPPED/CRASHED → STARTING → RUNNING ⇄ IDLE → STOPPED
                     ↓
                  CRASHED (on unexpected termination)
```

**Active sessions**: A worker is considered "awake" when runtime_status is: starting, running, or idle.

```python
@dataclass(frozen=True)
class SessionId:
    """Unique session identifier.

    Combines worker_id with session instance for traceability.
    """
    worker_id: str
    instance_id: str  # UUID or timestamp-based

    def __str__(self) -> str:
        return f"{self.worker_id}:{self.instance_id}"

    @classmethod
    def create(cls, worker_id: str) -> "SessionId":
        """Create new session ID for a worker."""
        import uuid
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
    working_directory: Path | None = None
    env_vars: dict[str, str] = field(default_factory=dict)

    # Terminal settings
    cols: int = 120
    rows: int = 40

    # Timeouts (milliseconds)
    startup_timeout_ms: int = 30000
    idle_timeout_ms: int = 300000    # 5 minutes
    response_timeout_ms: int = 600000 # 10 minutes

    # Resource limits
    max_context_tokens: int = 100000
    memory_limit_mb: int | None = None

    # Session persistence
    persist_transcript: bool = True
    transcript_db_path: Path | None = None


@dataclass
class SessionMetrics:
    """Runtime metrics for a session."""
    created_at: datetime
    started_at: datetime | None = None
    stopped_at: datetime | None = None

    # Activity tracking
    last_activity: datetime | None = None
    prompts_sent: int = 0
    responses_received: int = 0
    tokens_consumed: int = 0

    # Error tracking
    errors_count: int = 0
    last_error: str | None = None

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
        self._state = SessionState.STARTING
        self._metrics = SessionMetrics(created_at=datetime.now())
        self._bound_worker_id: str | None = None

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
    def bound_worker_id(self) -> str | None:
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
    def pid(self) -> int | None:
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
    def _read_output(self, timeout_ms: int | None = None) -> SessionOutput:
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

        self._set_state(SessionState.STARTING)
        self._metrics.started_at = datetime.now()

        try:
            self._spawn_process()
            self._set_state(SessionState.RUNNING)

            # Wait for ready state
            self._wait_for_ready()
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
        if self._state in (SessionState.STOPPED, SessionState.CRASHED):
            return

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
        timeout_ms: int | None = None,
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
            self._set_state(SessionState.IDLE)

    def cancel(self) -> None:
        """Cancel current operation.

        Sends interrupt signal to CLI process.
        """
        if self._state == SessionState.RUNNING:
            self._send_interrupt()
            self._set_state(SessionState.IDLE)

    @abstractmethod
    def _send_interrupt(self) -> None:
        """Send interrupt signal to CLI (e.g., Ctrl+C)."""
        pass

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
```

---

## 2. Session Lifecycle State Machine

### State Diagram (ASCII)

```
                                    +----------+
                                    |          |
                                    |  STOPPED |<------------------+
                                    |          |                   |
                                    +----+-----+                   |
                                         |                         |
                                         | start()                 | stop()
                                         v                         |
                                    +----------+                   |
                           +------->|          |                   |
                           |        | STARTING |---+               |
                           |        |          |   |               |
                           |        +----+-----+   |               |
                           |             |         | error         |
                           |             | ready   |               |
                           |             v         v               |
                           |        +----------+   +----------+    |
       restart()           |        |          |   |          |    |
       (after crash)       +--------|  RUNNING |   | CRASHED  |----+
                                    |          |   |          |
                                    +----+-----+   +----------+
                                         |
                       prompt            |  response
                       received          |  complete
                                         v
                                    +----------+
                                    |          |
                                    |   IDLE   |
                                    |          |
                                    +----+-----+
                                         |
                                         | new prompt
                                         |
                                         v
                                    +----+-----+
                                    |          |
                                    |  RUNNING |
                                    |          |
                                    +----------+
```

### State Transition Table

| Current State | Event            | Next State | Actions                              |
|---------------|------------------|------------|--------------------------------------|
| STOPPED       | start()          | STARTING   | Spawn process                        |
| STARTING      | process ready    | RUNNING    | None                                 |
| STARTING      | error            | CRASHED    | Log error, cleanup                   |
| RUNNING       | response done    | IDLE       | Update metrics                       |
| RUNNING       | timeout          | CRASHED    | Kill process, log error              |
| RUNNING       | process exit     | CRASHED    | Log error                            |
| IDLE          | new prompt       | RUNNING    | Send input                           |
| IDLE          | stop()           | STOPPED    | Graceful shutdown                    |
| IDLE          | timeout          | STOPPED    | Graceful shutdown (idle too long)    |
| CRASHED       | restart()        | STARTING   | Spawn new process                    |
| CRASHED       | stop()           | STOPPED    | Cleanup resources                    |

### State Invariants

```python
STATE_INVARIANTS = {
    SessionState.STARTING: {
        "process_spawning": True,
        "accepts_input": False,
        "has_pid": False,  # May not yet have PID
    },
    SessionState.RUNNING: {
        "process_alive": True,
        "accepts_input": False,  # Busy processing
        "has_pid": True,
    },
    SessionState.IDLE: {
        "process_alive": True,
        "accepts_input": True,
        "has_pid": True,
    },
    SessionState.STOPPED: {
        "process_alive": False,
        "accepts_input": False,
        "has_pid": False,
    },
    SessionState.CRASHED: {
        "process_alive": False,
        "accepts_input": False,
        "has_pid": False,
    },
}
```

---

## 3. Spawning Mechanism

QuinnAI supports multiple spawning strategies to accommodate different deployment scenarios.

### Strategy 1: Subprocess (Default)

Direct subprocess spawning for local development and single-machine deployments.

```python
from abc import ABC, abstractmethod
import subprocess
import os
from typing import IO


class SpawnStrategy(ABC):
    """Abstract spawning strategy."""

    @abstractmethod
    def spawn(self, config: SessionConfig) -> "SpawnedProcess":
        """Spawn a new process."""
        pass


@dataclass
class SpawnedProcess:
    """Handle to a spawned process."""
    pid: int
    stdin: IO[bytes]
    stdout: IO[bytes]
    stderr: IO[bytes] | None
    cleanup: Callable[[], None]


class SubprocessSpawner(SpawnStrategy):
    """Spawn sessions as local subprocesses."""

    def spawn(self, config: SessionConfig) -> SpawnedProcess:
        """Spawn using subprocess.Popen."""
        cmd = [config.command] + config.args

        env = os.environ.copy()
        env.update(config.env_vars)

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(config.working_directory) if config.working_directory else None,
            env=env,
            bufsize=0,  # Unbuffered for real-time I/O
        )

        return SpawnedProcess(
            pid=process.pid,
            stdin=process.stdin,
            stdout=process.stdout,
            stderr=process.stderr,
            cleanup=lambda: process.terminate(),
        )
```

### Strategy 2: Tmux Session (Production)

Tmux-based spawning for persistent sessions that survive SSH disconnects.

```python
class TmuxSpawner(SpawnStrategy):
    """Spawn sessions inside tmux for persistence."""

    def __init__(self, socket_name: str = "quinnai"):
        self._socket = socket_name

    def spawn(self, config: SessionConfig) -> SpawnedProcess:
        """Spawn inside a tmux session."""
        session_name = f"qn-{config.worker_id}"

        # Create tmux session
        cmd = [
            "tmux", "-L", self._socket,
            "new-session", "-d",
            "-s", session_name,
            "-x", str(config.cols),
            "-y", str(config.rows),
            config.command, *config.args
        ]

        subprocess.run(cmd, check=True)

        # Get PID
        pid = self._get_pane_pid(session_name)

        return SpawnedProcess(
            pid=pid,
            stdin=TmuxPipe(self._socket, session_name, "stdin"),
            stdout=TmuxPipe(self._socket, session_name, "stdout"),
            stderr=None,
            cleanup=lambda: self._kill_session(session_name),
        )

    def _get_pane_pid(self, session_name: str) -> int:
        result = subprocess.run(
            ["tmux", "-L", self._socket, "display-message",
             "-t", session_name, "-p", "#{pane_pid}"],
            capture_output=True, text=True
        )
        return int(result.stdout.strip())

    def _kill_session(self, session_name: str) -> None:
        subprocess.run(
            ["tmux", "-L", self._socket, "kill-session", "-t", session_name],
            check=False
        )
```

### Strategy 3: Container (Isolated)

Container-based spawning for resource isolation and security.

```python
class ContainerSpawner(SpawnStrategy):
    """Spawn sessions in containers for isolation."""

    def __init__(self, image: str, runtime: str = "docker"):
        self._image = image
        self._runtime = runtime  # docker, podman, etc.

    def spawn(self, config: SessionConfig) -> SpawnedProcess:
        """Spawn inside a container."""
        container_name = f"qn-{config.worker_id}-{config.instance_id}"

        cmd = [
            self._runtime, "run",
            "--name", container_name,
            "--interactive",
            "--rm",
        ]

        # Resource limits
        if config.memory_limit_mb:
            cmd.extend(["--memory", f"{config.memory_limit_mb}m"])

        # Environment
        for k, v in config.env_vars.items():
            cmd.extend(["--env", f"{k}={v}"])

        # Working directory
        if config.working_directory:
            cmd.extend(["--workdir", str(config.working_directory)])
            cmd.extend(["--volume", f"{config.working_directory}:{config.working_directory}"])

        cmd.extend([self._image, config.command] + config.args)

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return SpawnedProcess(
            pid=process.pid,
            stdin=process.stdin,
            stdout=process.stdout,
            stderr=process.stderr,
            cleanup=lambda: self._cleanup_container(container_name),
        )

    def _cleanup_container(self, name: str) -> None:
        subprocess.run([self._runtime, "stop", name], check=False)
        subprocess.run([self._runtime, "rm", "-f", name], check=False)
```

### Spawner Factory

```python
class SpawnerFactory:
    """Factory for creating spawn strategies."""

    _strategies: dict[str, type[SpawnStrategy]] = {
        "subprocess": SubprocessSpawner,
        "tmux": TmuxSpawner,
        "container": ContainerSpawner,
    }

    @classmethod
    def create(cls, strategy: str, **kwargs) -> SpawnStrategy:
        """Create a spawner by name.

        Args:
            strategy: Strategy name (subprocess, tmux, container)
            **kwargs: Strategy-specific arguments

        Returns:
            Configured SpawnStrategy instance
        """
        if strategy not in cls._strategies:
            raise ValueError(f"Unknown spawn strategy: {strategy}")

        return cls._strategies[strategy](**kwargs)

    @classmethod
    def register(cls, name: str, strategy_class: type[SpawnStrategy]) -> None:
        """Register a custom spawn strategy."""
        cls._strategies[name] = strategy_class
```

---

## 4. Session-Worker Binding

The 1:1 session-worker binding is enforced through a binding manager that tracks all active bindings.

### SessionBindingManager

```python
from threading import Lock
from typing import Dict, Optional
import weakref


class SessionBindingManager:
    """
    Enforces 1:1 session-worker binding.

    Core rules:
    1. One worker can have at most one active session
    2. One session can be bound to at most one worker
    3. Bindings are immutable once established
    4. Bindings are released when session stops

    Thread-safe for concurrent access.
    """

    def __init__(self):
        self._lock = Lock()
        self._worker_to_session: Dict[str, SessionId] = {}
        self._session_to_worker: Dict[SessionId, str] = {}
        self._sessions: Dict[SessionId, weakref.ref[SessionInterface]] = {}

    def bind(self, worker_id: str, session: SessionInterface) -> None:
        """Bind a session to a worker.

        Args:
            worker_id: Worker ID
            session: Session instance

        Raises:
            WorkerAlreadyBoundError: Worker already has a session
            SessionAlreadyBoundError: Session already bound to different worker
        """
        with self._lock:
            # Check worker doesn't already have a session
            if worker_id in self._worker_to_session:
                existing = self._worker_to_session[worker_id]
                raise WorkerAlreadyBoundError(worker_id, existing)

            # Check session isn't bound elsewhere
            if session.id in self._session_to_worker:
                existing_worker = self._session_to_worker[session.id]
                if existing_worker != worker_id:
                    raise SessionAlreadyBoundError(session.id, existing_worker, worker_id)

            # Establish binding
            self._worker_to_session[worker_id] = session.id
            self._session_to_worker[session.id] = worker_id
            self._sessions[session.id] = weakref.ref(session)

            # Also bind on session side
            session.bind_to_worker(worker_id)

    def unbind(self, worker_id: str) -> None:
        """Release binding for a worker.

        Args:
            worker_id: Worker ID to unbind
        """
        with self._lock:
            if worker_id not in self._worker_to_session:
                return

            session_id = self._worker_to_session.pop(worker_id)
            self._session_to_worker.pop(session_id, None)
            self._sessions.pop(session_id, None)

    def get_session(self, worker_id: str) -> Optional[SessionInterface]:
        """Get session for a worker.

        Args:
            worker_id: Worker ID

        Returns:
            Session if bound, None otherwise
        """
        with self._lock:
            if worker_id not in self._worker_to_session:
                return None

            session_id = self._worker_to_session[worker_id]
            ref = self._sessions.get(session_id)
            if ref is None:
                return None

            session = ref()
            if session is None:
                # Session was garbage collected, cleanup
                self._worker_to_session.pop(worker_id, None)
                self._session_to_worker.pop(session_id, None)
                self._sessions.pop(session_id, None)
                return None

            return session

    def get_worker(self, session_id: SessionId) -> Optional[str]:
        """Get worker for a session.

        Args:
            session_id: Session ID

        Returns:
            Worker ID if bound, None otherwise
        """
        with self._lock:
            return self._session_to_worker.get(session_id)

    def is_bound(self, worker_id: str) -> bool:
        """Check if worker has a bound session."""
        with self._lock:
            return worker_id in self._worker_to_session

    def list_bindings(self) -> Dict[str, SessionId]:
        """List all active bindings.

        Returns:
            Dict mapping worker_id to session_id
        """
        with self._lock:
            return dict(self._worker_to_session)


class WorkerAlreadyBoundError(Exception):
    """Worker already has a bound session."""
    def __init__(self, worker_id: str, existing_session: SessionId):
        super().__init__(
            f"Worker '{worker_id}' already bound to session {existing_session}"
        )
        self.worker_id = worker_id
        self.existing_session = existing_session
```

### Integration with Worker State Machine

```python
def integrate_session_with_worker(
    worker: "Worker",
    session: SessionInterface,
    binding_manager: SessionBindingManager
) -> None:
    """Integrate session lifecycle with worker state machine.

    Automatically:
    - Binds session to worker on creation
    - Updates worker runtime_status based on session state
    - Unbinds on session stop
    """

    # Establish binding
    binding_manager.bind(worker.id, session)

    # Map session states to worker runtime states
    def on_session_state_change(old: SessionState, new: SessionState) -> None:
        state_mapping = {
            SessionState.STARTING: "starting",
            SessionState.RUNNING: "running",
            SessionState.IDLE: "idle",
            SessionState.STOPPED: "stopped",
            SessionState.CRASHED: "crashed",
        }
        worker_runtime = state_mapping.get(new)
        if worker_runtime:
            worker._update_runtime_status(worker_runtime)

        # Unbind on stop
        if new in (SessionState.STOPPED, SessionState.CRASHED):
            binding_manager.unbind(worker.id)

    session.on_state_change(on_session_state_change)
```

---

## 5. CLI Adapter Interface

Each CLI provider (Claude Code, Codex, Gemini) implements the `CLIAdapter` interface.

### CLIAdapter Abstract Base

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Pattern
import re


@dataclass
class CLICapabilities:
    """Capabilities of a CLI provider."""
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_images: bool = False
    supports_files: bool = True
    max_context_tokens: int = 100000
    max_output_tokens: int = 16000


class CLIAdapter(ABC):
    """
    Abstract base for CLI adapters.

    Each CLI provider (Claude Code, Codex CLI, Gemini CLI) implements this
    interface to provide QuinnAI with a consistent way to interact with
    different AI CLIs.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name (e.g., 'claude_code', 'codex', 'gemini')."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> CLICapabilities:
        """CLI capabilities."""
        pass

    @property
    @abstractmethod
    def command(self) -> str:
        """CLI command to execute."""
        pass

    @property
    @abstractmethod
    def default_args(self) -> list[str]:
        """Default CLI arguments."""
        pass

    @property
    @abstractmethod
    def prompt_pattern(self) -> Pattern:
        """Regex pattern to detect CLI prompt (ready for input)."""
        pass

    @property
    @abstractmethod
    def completion_pattern(self) -> Pattern:
        """Regex pattern to detect response completion."""
        pass

    @abstractmethod
    def parse_output(self, raw: str) -> SessionOutput:
        """Parse raw CLI output into structured SessionOutput.

        Args:
            raw: Raw text from CLI stdout

        Returns:
            Parsed SessionOutput with content and tool calls
        """
        pass

    @abstractmethod
    def format_prompt(self, prompt: str, **context) -> str:
        """Format a prompt for this CLI.

        Some CLIs need special formatting (escaping, prefixes, etc.)

        Args:
            prompt: Raw prompt text
            **context: Additional context (files, images, etc.)

        Returns:
            Formatted prompt string
        """
        pass

    def get_env_vars(self) -> dict[str, str]:
        """Get required environment variables.

        Returns:
            Dict of env var name to value (or placeholder)
        """
        return {}

    def validate_config(self, config: SessionConfig) -> list[str]:
        """Validate session config for this adapter.

        Args:
            config: Session configuration

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        if config.max_context_tokens > self.capabilities.max_context_tokens:
            errors.append(
                f"max_context_tokens ({config.max_context_tokens}) exceeds "
                f"CLI limit ({self.capabilities.max_context_tokens})"
            )
        return errors


# =========================================================================
# Concrete Adapters
# =========================================================================

class ClaudeCodeAdapter(CLIAdapter):
    """Adapter for Claude Code CLI (claude)."""

    @property
    def name(self) -> str:
        return "claude_code"

    @property
    def capabilities(self) -> CLICapabilities:
        return CLICapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_images=True,
            supports_files=True,
            max_context_tokens=200000,
            max_output_tokens=64000,
        )

    @property
    def command(self) -> str:
        return "claude"

    @property
    def default_args(self) -> list[str]:
        return ["--dangerously-skip-permissions"]

    @property
    def prompt_pattern(self) -> Pattern:
        # Claude Code shows ">" when ready
        return re.compile(r"^>\s*$", re.MULTILINE)

    @property
    def completion_pattern(self) -> Pattern:
        # Claude Code shows prompt again when done
        return re.compile(r"^>\s*$", re.MULTILINE)

    def parse_output(self, raw: str) -> SessionOutput:
        """Parse Claude Code output."""
        # Extract tool calls (between specific markers)
        tool_calls = []
        tool_pattern = re.compile(
            r"<tool_call>(.*?)</tool_call>",
            re.DOTALL
        )
        for match in tool_pattern.finditer(raw):
            tool_calls.append({"raw": match.group(1)})

        # Remove tool call markers from content
        content = tool_pattern.sub("", raw).strip()

        return SessionOutput(
            content=content,
            timestamp=datetime.now(),
            is_complete=True,
            tool_calls=tool_calls,
        )

    def format_prompt(self, prompt: str, **context) -> str:
        """Format prompt for Claude Code."""
        return prompt  # Claude Code accepts plain text

    def get_env_vars(self) -> dict[str, str]:
        return {
            "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
        }


class CodexAdapter(CLIAdapter):
    """Adapter for OpenAI Codex CLI."""

    @property
    def name(self) -> str:
        return "codex"

    @property
    def capabilities(self) -> CLICapabilities:
        return CLICapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_images=True,
            supports_files=True,
            max_context_tokens=128000,
            max_output_tokens=16000,
        )

    @property
    def command(self) -> str:
        return "codex"

    @property
    def default_args(self) -> list[str]:
        return ["--approval-mode", "full-auto"]

    @property
    def prompt_pattern(self) -> Pattern:
        return re.compile(r"codex>\s*$", re.MULTILINE)

    @property
    def completion_pattern(self) -> Pattern:
        return re.compile(r"codex>\s*$", re.MULTILINE)

    def parse_output(self, raw: str) -> SessionOutput:
        # Implementation similar to Claude adapter
        return SessionOutput(
            content=raw.strip(),
            timestamp=datetime.now(),
            is_complete=True,
        )

    def format_prompt(self, prompt: str, **context) -> str:
        return prompt

    def get_env_vars(self) -> dict[str, str]:
        return {
            "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        }


class GeminiAdapter(CLIAdapter):
    """Adapter for Google Gemini CLI."""

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def capabilities(self) -> CLICapabilities:
        return CLICapabilities(
            supports_streaming=True,
            supports_tools=True,
            supports_images=True,
            supports_files=True,
            max_context_tokens=1000000,  # Gemini has large context
            max_output_tokens=32000,
        )

    @property
    def command(self) -> str:
        return "gemini"

    @property
    def default_args(self) -> list[str]:
        return []

    @property
    def prompt_pattern(self) -> Pattern:
        return re.compile(r"gemini>\s*$", re.MULTILINE)

    @property
    def completion_pattern(self) -> Pattern:
        return re.compile(r"gemini>\s*$", re.MULTILINE)

    def parse_output(self, raw: str) -> SessionOutput:
        return SessionOutput(
            content=raw.strip(),
            timestamp=datetime.now(),
            is_complete=True,
        )

    def format_prompt(self, prompt: str, **context) -> str:
        return prompt

    def get_env_vars(self) -> dict[str, str]:
        return {
            "GOOGLE_API_KEY": "${GOOGLE_API_KEY}",
        }
```

### CLI Adapter Registry

```python
class CLIAdapterRegistry:
    """Registry for CLI adapters."""

    _adapters: dict[str, CLIAdapter] = {}

    @classmethod
    def register(cls, adapter: CLIAdapter) -> None:
        """Register a CLI adapter."""
        cls._adapters[adapter.name] = adapter

    @classmethod
    def get(cls, name: str) -> CLIAdapter:
        """Get adapter by name.

        Raises:
            AdapterNotFoundError: If adapter not registered
        """
        if name not in cls._adapters:
            raise AdapterNotFoundError(name)
        return cls._adapters[name]

    @classmethod
    def list_adapters(cls) -> list[str]:
        """List registered adapter names."""
        return list(cls._adapters.keys())

    @classmethod
    def initialize_defaults(cls) -> None:
        """Register default adapters."""
        cls.register(ClaudeCodeAdapter())
        cls.register(CodexAdapter())
        cls.register(GeminiAdapter())


class AdapterNotFoundError(Exception):
    """CLI adapter not found."""
    def __init__(self, name: str):
        super().__init__(f"CLI adapter not found: {name}")
        self.name = name
```

---

## 6. Resource Management

### Memory Management

```python
import psutil
from threading import Thread, Event
from typing import Callable


class SessionResourceMonitor:
    """Monitors resource usage for a session."""

    def __init__(
        self,
        session_id: SessionId,
        pid: int,
        memory_limit_mb: int | None = None,
        on_limit_exceeded: Callable[[str, float], None] | None = None,
    ):
        self._session_id = session_id
        self._pid = pid
        self._memory_limit_mb = memory_limit_mb
        self._on_limit_exceeded = on_limit_exceeded
        self._stop_event = Event()
        self._monitor_thread: Thread | None = None

        # Metrics
        self._peak_memory_mb: float = 0.0
        self._current_memory_mb: float = 0.0

    def start(self, interval_seconds: float = 5.0) -> None:
        """Start resource monitoring."""
        self._stop_event.clear()

        def monitor_loop():
            while not self._stop_event.is_set():
                try:
                    process = psutil.Process(self._pid)
                    memory_info = process.memory_info()
                    self._current_memory_mb = memory_info.rss / (1024 * 1024)
                    self._peak_memory_mb = max(self._peak_memory_mb, self._current_memory_mb)

                    # Check limits
                    if self._memory_limit_mb and self._current_memory_mb > self._memory_limit_mb:
                        if self._on_limit_exceeded:
                            self._on_limit_exceeded("memory", self._current_memory_mb)
                except psutil.NoSuchProcess:
                    break
                except Exception:
                    pass

                self._stop_event.wait(interval_seconds)

        self._monitor_thread = Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop(self) -> None:
        """Stop resource monitoring."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)

    @property
    def current_memory_mb(self) -> float:
        return self._current_memory_mb

    @property
    def peak_memory_mb(self) -> float:
        return self._peak_memory_mb
```

### Context Window Management

```python
@dataclass
class ContextWindowState:
    """Tracks context window usage."""
    max_tokens: int
    used_tokens: int = 0
    warning_threshold: float = 0.8  # Warn at 80%

    @property
    def remaining_tokens(self) -> int:
        return self.max_tokens - self.used_tokens

    @property
    def usage_fraction(self) -> float:
        return self.used_tokens / self.max_tokens if self.max_tokens > 0 else 0.0

    @property
    def is_near_limit(self) -> bool:
        return self.usage_fraction >= self.warning_threshold

    @property
    def is_at_limit(self) -> bool:
        return self.used_tokens >= self.max_tokens


class ContextWindowManager:
    """Manages context window for a session."""

    def __init__(self, max_tokens: int, warning_threshold: float = 0.8):
        self._state = ContextWindowState(
            max_tokens=max_tokens,
            warning_threshold=warning_threshold,
        )
        self._callbacks: list[Callable[[ContextWindowState], None]] = []

    def update(self, used_tokens: int) -> None:
        """Update token usage."""
        self._state.used_tokens = used_tokens
        for cb in self._callbacks:
            cb(self._state)

    def on_update(self, callback: Callable[[ContextWindowState], None]) -> None:
        """Register callback for context updates."""
        self._callbacks.append(callback)

    @property
    def state(self) -> ContextWindowState:
        return self._state

    def should_compact(self) -> bool:
        """Check if context should be compacted."""
        return self._state.is_near_limit

    def can_accept_prompt(self, estimated_tokens: int) -> bool:
        """Check if prompt can fit in remaining context."""
        return self._state.remaining_tokens >= estimated_tokens
```

### Session Cleanup

```python
class SessionCleanup:
    """Handles cleanup when session ends."""

    def __init__(self, session: SessionInterface):
        self._session = session
        self._cleanup_tasks: list[Callable[[], None]] = []

    def register(self, task: Callable[[], None]) -> None:
        """Register a cleanup task."""
        self._cleanup_tasks.append(task)

    def execute(self) -> list[str]:
        """Execute all cleanup tasks.

        Returns:
            List of errors (empty if all succeeded)
        """
        errors = []
        for task in self._cleanup_tasks:
            try:
                task()
            except Exception as e:
                errors.append(str(e))
        return errors

    @classmethod
    def standard_cleanup(cls, session: SessionInterface) -> "SessionCleanup":
        """Create cleanup with standard tasks."""
        cleanup = cls(session)

        # Persist transcript
        cleanup.register(lambda: session._maybe_persist_transcript())

        # Release binding
        cleanup.register(lambda: session._release_binding())

        # Kill process if still running
        cleanup.register(lambda: session._terminate_process(force=True)
                        if session.pid else None)

        return cleanup
```

---

## 7. Putting It All Together - SessionManager

```python
class SessionManager:
    """
    Central manager for all sessions.

    Responsibilities:
    - Creates and tracks all sessions
    - Enforces worker-session bindings
    - Manages session lifecycle
    - Provides discovery and monitoring
    """

    def __init__(
        self,
        spawner: SpawnStrategy | None = None,
        db_path: Path | None = None,
    ):
        self._spawner = spawner or SubprocessSpawner()
        self._db_path = db_path
        self._binding_manager = SessionBindingManager()
        self._sessions: dict[SessionId, SessionInterface] = {}
        self._lock = Lock()

    def create_session(
        self,
        worker_id: str,
        adapter_name: str,
        **config_overrides
    ) -> SessionInterface:
        """Create and bind a new session for a worker.

        Args:
            worker_id: Worker ID to bind to
            adapter_name: CLI adapter name (claude_code, codex, gemini)
            **config_overrides: Override default config values

        Returns:
            Bound session instance

        Raises:
            WorkerAlreadyBoundError: Worker already has a session
            AdapterNotFoundError: Unknown adapter
        """
        # Check worker doesn't already have a session
        if self._binding_manager.is_bound(worker_id):
            existing = self._binding_manager.get_session(worker_id)
            raise WorkerAlreadyBoundError(worker_id, existing.id)

        # Get adapter
        adapter = CLIAdapterRegistry.get(adapter_name)

        # Build config
        config = SessionConfig(
            worker_id=worker_id,
            provider=adapter_name,
            command=adapter.command,
            args=adapter.default_args,
            max_context_tokens=adapter.capabilities.max_context_tokens,
            transcript_db_path=self._db_path,
            **config_overrides,
        )

        # Create session
        session = self._create_session_for_adapter(adapter, config)

        # Bind and track
        with self._lock:
            self._binding_manager.bind(worker_id, session)
            self._sessions[session.id] = session

        return session

    def _create_session_for_adapter(
        self,
        adapter: CLIAdapter,
        config: SessionConfig,
    ) -> SessionInterface:
        """Create concrete session for adapter."""
        # This would be implemented based on adapter type
        # For now, return a generic implementation
        return GenericCLISession(config, adapter, self._spawner)

    def get_session(self, worker_id: str) -> SessionInterface | None:
        """Get session for a worker."""
        return self._binding_manager.get_session(worker_id)

    def stop_session(self, worker_id: str, force: bool = False) -> None:
        """Stop session for a worker."""
        session = self._binding_manager.get_session(worker_id)
        if session:
            session.stop(force=force)
            with self._lock:
                self._sessions.pop(session.id, None)
            self._binding_manager.unbind(worker_id)

    def restart_session(self, worker_id: str) -> SessionInterface:
        """Restart session for a worker."""
        session = self._binding_manager.get_session(worker_id)
        if not session:
            raise ValueError(f"No session for worker {worker_id}")

        # Get adapter and config from existing session
        adapter_name = session.config.provider
        config_dict = {
            "working_directory": session.config.working_directory,
            "env_vars": session.config.env_vars,
        }

        # Stop existing
        self.stop_session(worker_id, force=True)

        # Create new
        return self.create_session(worker_id, adapter_name, **config_dict)

    def list_sessions(self) -> list[dict]:
        """List all active sessions."""
        with self._lock:
            return [
                {
                    "session_id": str(s.id),
                    "worker_id": s.bound_worker_id,
                    "state": s.state.value,
                    "provider": s.config.provider,
                }
                for s in self._sessions.values()
            ]
```

---

## 8. Configuration Example

```yaml
# config/sessions.yaml

defaults:
  spawn_strategy: tmux
  startup_timeout_ms: 30000
  idle_timeout_ms: 300000
  response_timeout_ms: 600000
  cols: 120
  rows: 40
  persist_transcript: true

adapters:
  claude_code:
    command: /usr/local/bin/claude
    args:
      - --dangerously-skip-permissions
    env:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    max_context_tokens: 200000

  codex:
    command: /usr/local/bin/codex
    args:
      - --approval-mode
      - full-auto
    env:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    max_context_tokens: 128000

  gemini:
    command: /usr/local/bin/gemini
    env:
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
    max_context_tokens: 1000000

spawn_strategies:
  subprocess:
    # No additional config needed

  tmux:
    socket_name: quinnai

  container:
    runtime: docker
    image: quinnai/agent:latest
```

---

## 9. Implementation Roadmap

### Phase 1: Core Interfaces (P1)
1. Define `SessionInterface` ABC
2. Define `SessionState` enum and state machine
3. Define `SessionConfig` and related data classes
4. Create exception hierarchy

### Phase 2: Spawning Layer (P2)
1. Implement `SubprocessSpawner`
2. Implement `TmuxSpawner`
3. Create `SpawnerFactory`

### Phase 3: Binding System (P2)
1. Implement `SessionBindingManager`
2. Add binding validation
3. Integrate with Worker state machine

### Phase 4: CLI Adapters (P2)
1. Implement `CLIAdapter` ABC
2. Create `ClaudeCodeAdapter`
3. Create `CodexAdapter`
4. Create `GeminiAdapter`
5. Create `CLIAdapterRegistry`

### Phase 5: Resource Management (P3)
1. Implement `SessionResourceMonitor`
2. Implement `ContextWindowManager`
3. Implement `SessionCleanup`

### Phase 6: Integration (P3)
1. Create `SessionManager`
2. Integrate with existing `Worker` class
3. Add CLI commands for session management

---

## 10. Testing Strategy

### Unit Tests
- State machine transitions
- Binding enforcement
- Config validation
- Adapter pattern matching

### Integration Tests
- Full session lifecycle (start -> prompt -> stop)
- Crash recovery
- Resource limit enforcement
- Multi-session scenarios

### Mock Providers
```python
class MockCLISession(SessionInterface):
    """Mock session for testing."""

    def __init__(self, config: SessionConfig):
        super().__init__(config)
        self._mock_responses: list[str] = []
        self._response_index = 0

    def set_responses(self, responses: list[str]) -> None:
        self._mock_responses = responses

    def _spawn_process(self) -> None:
        pass  # No-op for mock

    def _terminate_process(self, force: bool = False) -> None:
        pass

    def _send_input(self, text: str) -> None:
        pass

    def _read_output(self, timeout_ms: int | None = None) -> SessionOutput:
        if self._response_index < len(self._mock_responses):
            content = self._mock_responses[self._response_index]
            self._response_index += 1
        else:
            content = ""
        return SessionOutput(content=content, timestamp=datetime.now())

    def _detect_ready(self, output: str) -> bool:
        return True

    def _detect_completion(self, output: str) -> bool:
        return True

    def _get_context_usage(self) -> int:
        return 0

    def _send_interrupt(self) -> None:
        pass
```
