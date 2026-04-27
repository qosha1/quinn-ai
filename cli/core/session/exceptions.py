"""Session-related exceptions.

The 8 specific session errors live here so cli.core.session.interface
stays focused on the SessionInterface ABC.
"""

from shared.core.state import SessionState

from .types import SessionId


class SessionError(Exception):
    """Base exception for session errors."""

    def __init__(self, session_id: SessionId, message: str):
        super().__init__(f"Session {session_id}: {message}")
        self.session_id = session_id


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

    def __init__(
        self,
        session_id: SessionId,
        current_worker: str,
        requested_worker: str,
    ):
        super().__init__(
            session_id,
            f"Already bound to worker '{current_worker}', cannot bind to '{requested_worker}'",
        )
        self.current_worker = current_worker
        self.requested_worker = requested_worker


class InvalidSessionStateTransition(Exception):
    """Invalid state transition attempted."""

    def __init__(
        self,
        current: SessionState,
        attempted: SessionState,
        valid: list[SessionState],
    ):
        valid_names = [s.value for s in valid]
        super().__init__(
            f"Cannot transition from '{current.value}' to '{attempted.value}'. "
            f"Valid transitions: {valid_names}"
        )
        self.current = current
        self.attempted = attempted
        self.valid = valid
