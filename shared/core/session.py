"""
Canonical session types for QuinnAI.

Per CLAUDE.md: "Session = Worker's Brain. One session, one worker. Unbreakable 1:1."

This module provides the canonical session-related types:
    - SessionConfig: Configuration for spawning a session
    - SessionId: Unique session identifier
    - SessionMetrics: Runtime metrics
    - SessionOutput: Output from session

The SessionState enum is in shared/core/state.py (with Worker/Session mapping).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .state import SessionState


# =============================================================================
# Session Identification
# =============================================================================


@dataclass(frozen=True)
class SessionId:
    """Unique session identifier.

    Combines worker_id with session instance for traceability.
    The 1:1 worker binding is enforced through worker_id.
    """

    worker_id: str
    """Worker this session belongs to."""

    instance_id: str
    """Unique instance identifier (UUID-based)."""

    def __str__(self) -> str:
        return f"{self.worker_id}:{self.instance_id}"

    def __hash__(self) -> int:
        return hash((self.worker_id, self.instance_id))

    @classmethod
    def create(cls, worker_id: str) -> SessionId:
        """Create new session ID for a worker."""
        return cls(worker_id=worker_id, instance_id=uuid.uuid4().hex[:12])


# =============================================================================
# Session Configuration
# =============================================================================


@dataclass
class SessionConfig:
    """Configuration for spawning a session.

    All values explicit - no discovery, no defaults from environment.
    Per CLAUDE.md: "No Config Discovery. Configuration passed explicitly at startup."
    """

    # Worker binding (immutable after creation)
    worker_id: str
    """Worker this session is for."""

    # Provider settings
    provider: str
    """Provider name (e.g., 'claude_code', 'codex', 'gemini')."""

    command: str
    """Full path to CLI executable."""

    args: list[str] = field(default_factory=list)
    """Command line arguments."""

    model: Optional[str] = None
    """Provider-specific model identifier (e.g., 'claude-sonnet-4-6',
    'claude-opus-4-7'). When set on a claude_code session, the
    adapter prepends '--model <id>' to the claude CLI args so the
    spawned session uses that model instead of whatever the user is
    logged into. Default: None means 'use the provider's default'.
    See quinn-ai-875q."""

    # Environment
    working_directory: Optional[Path] = None
    """Working directory for the session."""

    env_vars: dict[str, str] = field(default_factory=dict)
    """Environment variables to set."""

    # Terminal settings
    cols: int = 120
    """Terminal columns."""

    rows: int = 40
    """Terminal rows."""

    # Timeouts (milliseconds)
    startup_timeout_ms: int = 30000
    """Timeout for session startup (default 30s)."""

    idle_timeout_ms: int = 300000
    """Timeout for idle sessions (default 5 min)."""

    response_timeout_ms: int = 600000
    """Timeout for responses (default 10 min)."""

    # Resource limits
    max_context_tokens: int = 100000
    """Maximum context tokens."""

    memory_limit_mb: Optional[int] = None
    """Optional memory limit in MB."""

    # Session persistence
    persist_transcript: bool = True
    """Whether to persist transcript to DB."""

    transcript_db_path: Optional[Path] = None
    """Path to transcript database."""

    # Onboarding
    welcome_message: Optional[str] = None
    """Optional welcome message for worker onboarding."""

    # Legacy compatibility fields (for pyterm)
    shell: str = "/bin/bash"
    """Shell to use (legacy, prefer command)."""

    cwd: str | None = None
    """Working directory as string (legacy, prefer working_directory)."""

    env: dict[str, str] = field(default_factory=dict)
    """Environment variables (legacy, prefer env_vars)."""

    def __post_init__(self):
        """Sync legacy fields with preferred fields."""
        # Sync cwd <-> working_directory
        if self.cwd and not self.working_directory:
            self.working_directory = Path(self.cwd)
        elif self.working_directory and not self.cwd:
            self.cwd = str(self.working_directory)

        # Sync env <-> env_vars
        if self.env and not self.env_vars:
            self.env_vars = dict(self.env)
        elif self.env_vars and not self.env:
            self.env = dict(self.env_vars)


# =============================================================================
# Session Metrics
# =============================================================================


@dataclass
class SessionMetrics:
    """Runtime metrics for a session."""

    created_at: datetime
    """When session was created."""

    started_at: Optional[datetime] = None
    """When session was started."""

    stopped_at: Optional[datetime] = None
    """When session was stopped."""

    # Activity tracking
    last_activity: Optional[datetime] = None
    """Last activity timestamp."""

    prompts_sent: int = 0
    """Number of prompts sent."""

    responses_received: int = 0
    """Number of responses received."""

    tokens_consumed: int = 0
    """Total tokens consumed."""

    # Error tracking
    errors_count: int = 0
    """Number of errors encountered."""

    last_error: Optional[str] = None
    """Last error message."""

    # Resource usage
    peak_memory_mb: float = 0.0
    """Peak memory usage in MB."""

    context_tokens_used: int = 0
    """Current context token usage."""

    @property
    def duration_ms(self) -> int | None:
        """Session duration in milliseconds."""
        if not self.started_at:
            return None
        end = self.stopped_at or datetime.now()
        return int((end - self.started_at).total_seconds() * 1000)

    @property
    def is_running(self) -> bool:
        """Whether session is currently running."""
        return self.started_at is not None and self.stopped_at is None


# =============================================================================
# Session Output
# =============================================================================


@dataclass
class SessionOutput:
    """Output from a session."""

    content: str
    """Output content."""

    timestamp: datetime
    """When output was received."""

    is_complete: bool = False
    """Whether output is complete (response finished)."""

    tool_calls: list[dict] = field(default_factory=list)
    """Tool calls in output."""

    metadata: dict = field(default_factory=dict)
    """Additional metadata."""


@dataclass
class PromptResult:
    """Result of sending a prompt to a session."""

    prompt: str
    """The prompt that was sent."""

    response: SessionOutput
    """The response received."""

    duration_ms: int
    """Time taken in milliseconds."""

    tokens_used: int
    """Tokens used for this exchange."""

    turn_id: str
    """Unique identifier for this turn."""


# =============================================================================
# Extracted Output (for pyterm compatibility)
# =============================================================================


@dataclass
class ExtractedOutput:
    """Output extracted from a session (pyterm format)."""

    text: str
    """Extracted text."""

    timestamp: float
    """Unix timestamp."""

    raw: bytes | None = None
    """Raw bytes if available."""

    def to_session_output(self) -> SessionOutput:
        """Convert to SessionOutput."""
        return SessionOutput(
            content=self.text,
            timestamp=datetime.fromtimestamp(self.timestamp),
        )
