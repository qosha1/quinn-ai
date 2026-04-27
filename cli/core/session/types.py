"""Session value-object types.

SessionId, SessionMetrics, SessionOutput live here. SessionConfig and
PromptResult are canonical in shared.core.session and re-exported by
cli.core.session.__init__.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
