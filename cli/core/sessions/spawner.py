"""
SpawnStrategy ABC - Abstract base for session spawning strategies.

Different spawn strategies handle how worker sessions are created:
- SubprocessSpawner: Direct subprocess spawning (simple, ephemeral)
- TmuxSpawner: Tmux sessions (persistent, can reattach)
- ContainerSpawner: Docker/Podman containers (isolated)

Per CLAUDE.md: "Session = Worker's Brain" - the spawn strategy determines
how that brain is embodied.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import subprocess


@dataclass
class SpawnerConfig:
    """Configuration for a spawn strategy."""

    # Process configuration
    command: str
    """Command to run."""

    args: list[str] = field(default_factory=list)
    """Arguments to pass to command."""

    working_directory: Optional[Path] = None
    """Working directory for the process."""

    env_vars: dict[str, str] = field(default_factory=dict)
    """Environment variables to set."""

    # Terminal configuration
    cols: int = 120
    """Terminal columns."""

    rows: int = 40
    """Terminal rows."""

    # Identification
    session_name: Optional[str] = None
    """Name for the session (used by tmux/container)."""

    worker_id: Optional[str] = None
    """Worker ID this session belongs to."""

    # Strategy-specific options
    options: dict[str, Any] = field(default_factory=dict)
    """Strategy-specific configuration options."""


@dataclass
class SpawnResult:
    """Result of spawning a session."""

    success: bool
    """Whether spawn succeeded."""

    pid: Optional[int] = None
    """Process ID if available."""

    session_id: Optional[str] = None
    """Session identifier (e.g., tmux session name)."""

    error: Optional[str] = None
    """Error message if spawn failed."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional spawn metadata."""


class SpawnStrategy(ABC):
    """Abstract base class for session spawning strategies.

    Each strategy handles:
    - Starting a new session
    - Stopping the session (graceful or forced)
    - Checking if session is alive
    - Attaching to the session for debugging
    - Reading output from the session
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for identification."""
        pass

    @abstractmethod
    def spawn(self, config: SpawnerConfig) -> SpawnResult:
        """Spawn a new session.

        Args:
            config: Spawner configuration

        Returns:
            SpawnResult with status and identifiers
        """
        pass

    @abstractmethod
    def stop(self, session_id: str, force: bool = False) -> bool:
        """Stop a running session.

        Args:
            session_id: Session identifier (pid, tmux name, container id)
            force: If True, force kill without graceful shutdown

        Returns:
            True if session was stopped successfully
        """
        pass

    @abstractmethod
    def is_alive(self, session_id: str) -> bool:
        """Check if session is still running.

        Args:
            session_id: Session identifier

        Returns:
            True if session is alive
        """
        pass

    @abstractmethod
    def send_input(self, session_id: str, text: str) -> bool:
        """Send input to the session.

        Args:
            session_id: Session identifier
            text: Text to send

        Returns:
            True if input was sent successfully
        """
        pass

    @abstractmethod
    def read_output(self, session_id: str, timeout_ms: Optional[int] = None) -> str:
        """Read output from the session.

        Args:
            session_id: Session identifier
            timeout_ms: Optional timeout in milliseconds

        Returns:
            Output text
        """
        pass

    def attach(self, session_id: str) -> bool:
        """Attach to session for interactive debugging.

        Default implementation returns False (not supported).
        Override in strategies that support attachment.

        Args:
            session_id: Session identifier

        Returns:
            True if attachment succeeded
        """
        return False

    def send_signal(self, session_id: str, signal: int) -> bool:
        """Send a signal to the session.

        Args:
            session_id: Session identifier
            signal: Signal number (e.g., signal.SIGINT)

        Returns:
            True if signal was sent
        """
        return False


class SpawnError(Exception):
    """Base exception for spawn errors."""

    def __init__(self, strategy: str, message: str):
        self.strategy = strategy
        self.message = message
        super().__init__(f"[{strategy}] {message}")


class SessionNotFoundError(SpawnError):
    """Raised when session doesn't exist."""

    def __init__(self, strategy: str, session_id: str):
        super().__init__(strategy, f"Session not found: {session_id}")
        self.session_id = session_id


class SpawnFailedError(SpawnError):
    """Raised when spawn fails."""

    def __init__(self, strategy: str, reason: str):
        super().__init__(strategy, f"Spawn failed: {reason}")
        self.reason = reason
