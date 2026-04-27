"""
Session abstraction interface for QuinnAI.

Session = Worker's Brain. One session, one worker. Unbreakable 1:1.

Public surface re-exported here so 'from cli.core.session import X' keeps
working after the file → package split. Internals live in:
- types.py       SessionId, SessionMetrics, SessionOutput
- exceptions.py  SessionError + 7 specific subclasses
- interface.py   SessionInterface ABC

SessionConfig and PromptResult are canonical in shared.core.session;
re-exported here to preserve the 'from cli.core.session import SessionConfig'
import sites that existed before the split.
"""

# ruff: noqa: F401 — these are re-exports for the public package surface

from shared.core.session import PromptResult, SessionConfig
from shared.core.state import SESSION_STATE_TRANSITIONS, SessionState
from shared.exceptions import SessionSpawnError

from .exceptions import (
    InvalidSessionStateTransition,
    SessionAlreadyBoundError,
    SessionAlreadyRunningError,
    SessionError,
    SessionNotReadyError,
    SessionNotRunningError,
    SessionTimeoutError,
)
from .interface import SessionInterface
from .types import SessionId, SessionMetrics, SessionOutput

__all__ = [
    # Re-exports
    "PromptResult",
    "SessionConfig",
    "SessionState",
    "SESSION_STATE_TRANSITIONS",
    "SessionSpawnError",
    # types
    "SessionId",
    "SessionMetrics",
    "SessionOutput",
    # exceptions
    "SessionError",
    "SessionAlreadyRunningError",
    "SessionNotRunningError",
    "SessionNotReadyError",
    "SessionTimeoutError",
    "SessionAlreadyBoundError",
    "InvalidSessionStateTransition",
    # interface
    "SessionInterface",
]
