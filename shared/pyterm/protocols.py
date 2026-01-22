"""
pyterm protocols - Abstract interfaces for session and provider management.

Session = Worker's brain (1:1, unbreakable)
Session ON = awake, Session OFF = asleep
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol, runtime_checkable

# Import WorkerState from canonical source
from shared.core.state import WorkerState


class SessionState(Enum):
    """Session lifecycle states for pyterm.

    Note: This is pyterm-specific SessionState designed for terminal session
    management. The canonical SessionState in shared.core.state has different
    values (STOPPED, STARTING, etc.) designed for the worker state mapping.
    """

    IDLE = "idle"
    RUNNING = "running"
    EXITED = "exited"
    ERROR = "error"


@dataclass
class SessionConfig:
    """Configuration for spawning a session.

    This is the pyterm-specific SessionConfig for terminal sessions.
    For the full canonical SessionConfig, see shared.core.session.
    """

    shell: str = "/bin/bash"
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    cols: int = 80
    rows: int = 24


@dataclass
class ExtractedOutput:
    """Output extracted from a session."""

    text: str
    timestamp: float
    raw: bytes | None = None


@runtime_checkable
class Session(Protocol):
    """
    Abstract session interface.

    A session wraps a terminal process (via tmux or other backend).
    One session = one worker brain. This mapping is unbreakable.
    """

    @property
    def id(self) -> str:
        """Unique session identifier."""
        ...

    @property
    def state(self) -> SessionState:
        """Current session state."""
        ...

    @property
    def pid(self) -> int | None:
        """Process ID of the underlying shell, if running."""
        ...

    def start(self, config: SessionConfig | None = None) -> None:
        """
        Start the session.

        Transitions: IDLE -> RUNNING
        Raises if session already running.
        """
        ...

    def stop(self, force: bool = False) -> None:
        """
        Stop the session.

        Transitions: RUNNING -> EXITED
        If force=True, kill immediately without graceful shutdown.
        """
        ...

    def inject(self, text: str) -> None:
        """
        Inject text into the session (send input).

        Equivalent to typing on the keyboard.
        """
        ...

    def inject_keys(self, keys: list[str]) -> None:
        """
        Inject key sequences (e.g., ['Enter', 'C-c', 'Escape']).

        For special keys that aren't plain text.
        """
        ...

    def extract(self) -> ExtractedOutput:
        """
        Extract current session output.

        Returns the current visible screen content.
        """
        ...

    def extract_history(self, lines: int | None = None) -> list[str]:
        """
        Extract session history (scrollback buffer).

        If lines is None, returns all available history.
        """
        ...

    def resize(self, cols: int, rows: int) -> None:
        """Resize the terminal."""
        ...

    def on_output(self, callback: Callable[[ExtractedOutput], None]) -> None:
        """Register callback for output events."""
        ...

    def on_state_change(
        self, callback: Callable[[SessionState, SessionState], None]
    ) -> None:
        """Register callback for state changes (old_state, new_state)."""
        ...


@dataclass
class ProviderConfig:
    """Configuration for a CLI provider."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    prompt_pattern: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class Provider(Protocol):
    """
    Abstract provider interface.

    A provider represents a CLI tool (Claude, Codex, Gemini, etc.)
    that can be spawned inside a session.
    """

    @property
    def name(self) -> str:
        """Provider name (e.g., 'claude', 'codex', 'gemini')."""
        ...

    @property
    def config(self) -> ProviderConfig:
        """Provider configuration."""
        ...

    def configure_session(self, session: Session) -> SessionConfig:
        """
        Configure a session for this provider.

        Returns SessionConfig with provider-specific settings
        (command, args, env vars, etc.)
        """
        ...

    def detect_prompt(self, output: str) -> bool:
        """
        Detect if output contains a prompt (ready for input).

        Used to know when the CLI is waiting for user input.
        """
        ...

    def detect_completion(self, output: str) -> bool:
        """
        Detect if output contains a completion (response finished).

        Used to know when the CLI has finished responding.
        """
        ...
