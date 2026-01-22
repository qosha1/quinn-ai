"""
SessionBindingManager - Central registry for worker-session bindings.

Enforces the sacred 1:1 relationship between workers and sessions:
- One worker can have at most one session
- One session belongs to exactly one worker
- Session crash triggers worker state change
- Clean unbind on termination

Per CLAUDE.md: "Session = Worker's Brain. One session, one worker. Unbreakable 1:1."
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING
import threading

if TYPE_CHECKING:
    from ..db import Database
    from ..session import SessionInterface


class WorkerAlreadyBoundError(Exception):
    """Worker already has a bound session."""

    def __init__(self, worker_id: str, existing_session_id: str):
        self.worker_id = worker_id
        self.existing_session_id = existing_session_id
        super().__init__(
            f"Worker '{worker_id}' already bound to session '{existing_session_id}'"
        )


class SessionAlreadyBoundError(Exception):
    """Session already bound to a worker."""

    def __init__(self, session_id: str, existing_worker_id: str):
        self.session_id = session_id
        self.existing_worker_id = existing_worker_id
        super().__init__(
            f"Session '{session_id}' already bound to worker '{existing_worker_id}'"
        )


class BindingNotFoundError(Exception):
    """No binding found for the specified worker or session."""

    def __init__(self, lookup_type: str, lookup_id: str):
        self.lookup_type = lookup_type
        self.lookup_id = lookup_id
        super().__init__(f"No binding found for {lookup_type} '{lookup_id}'")


@dataclass
class SessionBinding:
    """Record of a worker-session binding."""

    worker_id: str
    session_id: str
    bound_at: datetime
    pid: Optional[int] = None
    metadata: Optional[dict] = None


class SessionBindingManager:
    """Central manager for worker-session bindings.

    Provides system-wide tracking and enforcement of the 1:1 relationship
    between workers and sessions. This is separate from the per-session
    binding in SessionInterface - it's the authoritative source for
    binding state across all sessions.

    Thread-safe for concurrent access.

    Example:
        manager = SessionBindingManager(db)

        # Bind session to worker
        manager.bind(worker_id="worker-123", session_id="session-abc", pid=12345)

        # Check bindings
        session_id = manager.get_session_for_worker("worker-123")
        worker_id = manager.get_worker_for_session("session-abc")

        # Unbind
        manager.unbind(worker_id="worker-123")
    """

    def __init__(self, db: Optional["Database"] = None):
        """Initialize binding manager.

        Args:
            db: Optional Database for persistent bindings.
                If None, bindings are in-memory only.
        """
        self._db = db
        self._lock = threading.RLock()

        # In-memory binding indices
        self._worker_to_session: dict[str, SessionBinding] = {}
        self._session_to_worker: dict[str, str] = {}

        # Session instances (for crash detection callbacks)
        self._sessions: dict[str, "SessionInterface"] = {}

    def bind(
        self,
        worker_id: str,
        session_id: str,
        pid: Optional[int] = None,
        session: Optional["SessionInterface"] = None,
        metadata: Optional[dict] = None,
    ) -> SessionBinding:
        """Bind a session to a worker.

        Enforces 1:1 relationship:
        - Worker cannot have multiple sessions
        - Session cannot belong to multiple workers

        Args:
            worker_id: Worker ID to bind
            session_id: Session ID to bind
            pid: Optional process ID for crash detection
            session: Optional SessionInterface for state callbacks
            metadata: Optional metadata about the binding

        Returns:
            SessionBinding record

        Raises:
            WorkerAlreadyBoundError: If worker already has a session
            SessionAlreadyBoundError: If session already bound to another worker
        """
        with self._lock:
            # Check for existing worker binding
            if worker_id in self._worker_to_session:
                existing = self._worker_to_session[worker_id]
                if existing.session_id != session_id:
                    raise WorkerAlreadyBoundError(worker_id, existing.session_id)
                # Same binding already exists - return it
                return existing

            # Check for existing session binding
            if session_id in self._session_to_worker:
                existing_worker = self._session_to_worker[session_id]
                if existing_worker != worker_id:
                    raise SessionAlreadyBoundError(session_id, existing_worker)

            # Create binding
            binding = SessionBinding(
                worker_id=worker_id,
                session_id=session_id,
                bound_at=datetime.now(),
                pid=pid,
                metadata=metadata,
            )

            # Update indices
            self._worker_to_session[worker_id] = binding
            self._session_to_worker[session_id] = worker_id

            # Store session instance if provided
            if session is not None:
                self._sessions[session_id] = session
                self._setup_state_callback(session, worker_id)

            # Persist if DB available
            if self._db:
                self._persist_binding(binding)

            return binding

    def unbind(self, worker_id: str) -> Optional[SessionBinding]:
        """Unbind a session from a worker.

        Args:
            worker_id: Worker ID to unbind

        Returns:
            The removed SessionBinding, or None if no binding existed
        """
        with self._lock:
            if worker_id not in self._worker_to_session:
                return None

            binding = self._worker_to_session[worker_id]
            session_id = binding.session_id

            # Remove from indices
            del self._worker_to_session[worker_id]
            if session_id in self._session_to_worker:
                del self._session_to_worker[session_id]

            # Remove session instance
            if session_id in self._sessions:
                del self._sessions[session_id]

            # Remove from DB if available
            if self._db:
                self._remove_binding(worker_id)

            return binding

    def unbind_session(self, session_id: str) -> Optional[SessionBinding]:
        """Unbind by session ID (reverse lookup unbind).

        Args:
            session_id: Session ID to unbind

        Returns:
            The removed SessionBinding, or None if no binding existed
        """
        with self._lock:
            if session_id not in self._session_to_worker:
                return None

            worker_id = self._session_to_worker[session_id]
            return self.unbind(worker_id)

    def get_session_for_worker(self, worker_id: str) -> Optional[str]:
        """Get session ID bound to a worker.

        Args:
            worker_id: Worker ID to look up

        Returns:
            Session ID or None if not bound
        """
        with self._lock:
            binding = self._worker_to_session.get(worker_id)
            return binding.session_id if binding else None

    def get_worker_for_session(self, session_id: str) -> Optional[str]:
        """Get worker ID that owns a session.

        Args:
            session_id: Session ID to look up

        Returns:
            Worker ID or None if not bound
        """
        with self._lock:
            return self._session_to_worker.get(session_id)

    def get_binding(self, worker_id: str) -> Optional[SessionBinding]:
        """Get full binding record for a worker.

        Args:
            worker_id: Worker ID to look up

        Returns:
            SessionBinding or None if not bound
        """
        with self._lock:
            return self._worker_to_session.get(worker_id)

    def is_worker_bound(self, worker_id: str) -> bool:
        """Check if worker has a bound session.

        Args:
            worker_id: Worker ID to check

        Returns:
            True if worker has a session
        """
        with self._lock:
            return worker_id in self._worker_to_session

    def is_session_bound(self, session_id: str) -> bool:
        """Check if session is bound to a worker.

        Args:
            session_id: Session ID to check

        Returns:
            True if session is bound
        """
        with self._lock:
            return session_id in self._session_to_worker

    def get_session(self, session_id: str) -> Optional["SessionInterface"]:
        """Get session instance by ID.

        Args:
            session_id: Session ID to look up

        Returns:
            SessionInterface or None if not tracked
        """
        with self._lock:
            return self._sessions.get(session_id)

    def list_bindings(self) -> list[SessionBinding]:
        """List all current bindings.

        Returns:
            List of SessionBinding records
        """
        with self._lock:
            return list(self._worker_to_session.values())

    def validate_bindings(self) -> dict:
        """Validate all bindings and clean up stale ones.

        Checks:
        - Session processes still running (via PID if available)
        - Session instances still alive
        - Index consistency

        Returns:
            Dict with validation results:
            - valid: list of valid binding worker_ids
            - stale: list of removed stale binding worker_ids
            - errors: list of error descriptions
        """
        from ..session import SessionState

        results = {
            "valid": [],
            "stale": [],
            "errors": [],
        }

        with self._lock:
            for worker_id, binding in list(self._worker_to_session.items()):
                is_valid = True

                # Check session instance if available
                session = self._sessions.get(binding.session_id)
                if session is not None:
                    if session.state in (SessionState.STOPPED, SessionState.CRASHED):
                        is_valid = False
                        results["stale"].append(worker_id)
                        self.unbind(worker_id)
                        continue

                # Check PID if available and no session instance
                if session is None and binding.pid is not None:
                    if not self._is_process_alive(binding.pid):
                        is_valid = False
                        results["stale"].append(worker_id)
                        self.unbind(worker_id)
                        continue

                if is_valid:
                    results["valid"].append(worker_id)

            # Check index consistency
            for session_id, worker_id in list(self._session_to_worker.items()):
                if worker_id not in self._worker_to_session:
                    results["errors"].append(
                        f"Orphaned session index: {session_id} -> {worker_id}"
                    )
                    del self._session_to_worker[session_id]

        return results

    def _setup_state_callback(
        self, session: "SessionInterface", worker_id: str
    ) -> None:
        """Set up callback to sync session state to worker runtime state.

        Args:
            session: SessionInterface to monitor
            worker_id: Worker ID to update on state changes
        """
        from ..session import SessionState

        def on_state_change(old: SessionState, new: SessionState) -> None:
            # Update worker runtime state in DB
            if self._db:
                from ..queries import update_worker_runtime_status

                runtime_status = new.value
                update_worker_runtime_status(self._db, worker_id, runtime_status)

            # Auto-unbind on terminal states
            if new in (SessionState.STOPPED, SessionState.CRASHED):
                # Don't unbind here - let explicit unbind handle it
                # But we could trigger worker state change
                pass

        session.on_state_change(on_state_change)

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process is still running.

        Args:
            pid: Process ID to check

        Returns:
            True if process exists
        """
        import os

        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _persist_binding(self, binding: SessionBinding) -> None:
        """Persist binding to database.

        Args:
            binding: SessionBinding to persist
        """
        if not self._db:
            return

        # Store in worker_state table by updating session info
        # Or create a dedicated session_bindings table
        # For now, we update the worker_state pid field
        self._db.execute(
            """UPDATE worker_state
               SET pid = ?, updated_at = CURRENT_TIMESTAMP
               WHERE worker_id = ?""",
            (binding.pid, binding.worker_id),
        )
        self._db.connection.commit()

    def _remove_binding(self, worker_id: str) -> None:
        """Remove binding from database.

        Args:
            worker_id: Worker ID to remove binding for
        """
        if not self._db:
            return

        # Clear PID in worker_state
        self._db.execute(
            """UPDATE worker_state
               SET pid = NULL, updated_at = CURRENT_TIMESTAMP
               WHERE worker_id = ?""",
            (worker_id,),
        )
        self._db.connection.commit()


# Module-level singleton
_default_manager: Optional[SessionBindingManager] = None
_manager_lock = threading.Lock()


def get_binding_manager(db: Optional["Database"] = None) -> SessionBindingManager:
    """Get the default SessionBindingManager.

    Creates one if it doesn't exist.

    Args:
        db: Optional Database to use (only used on first call)

    Returns:
        SessionBindingManager instance
    """
    global _default_manager

    with _manager_lock:
        if _default_manager is None:
            _default_manager = SessionBindingManager(db)
        return _default_manager


def reset_binding_manager() -> None:
    """Reset the default binding manager (for testing)."""
    global _default_manager

    with _manager_lock:
        _default_manager = None
