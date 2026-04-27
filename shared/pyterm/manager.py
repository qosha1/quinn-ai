"""
Session Manager - Manages multiple worker sessions.

Each worker has exactly one session (1:1, unbreakable).
Session = Worker's brain.
"""

import threading
from dataclasses import dataclass, field
from typing import Iterator

from shared.pyterm.protocols import Session, PytermSessionConfig, PytermSessionState, WorkerState
from shared.pyterm.tmux_session import TmuxSession
from shared.pyterm.lifecycle import LifecycleHooks
from shared.pyterm.patterns import PatternMatcher


@dataclass
class ManagedSession:
    """A session with its associated lifecycle and patterns."""

    worker_id: str
    session: Session
    lifecycle: LifecycleHooks
    patterns: PatternMatcher | None = None

    @property
    def state(self) -> PytermSessionState:
        return self.session.state

    @property
    def worker_state(self) -> WorkerState:
        return self.lifecycle.state


class SessionManager:
    """
    Manages multiple worker sessions.

    Enforces the 1:1 mapping between workers and sessions.
    Tracks session state and provides lookup by worker_id.
    """

    def __init__(self):
        self._sessions: dict[str, ManagedSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        worker_id: str,
        config: PytermSessionConfig | None = None,
        session_name: str | None = None,
    ) -> ManagedSession:
        """
        Create a new session for a worker.

        Raises if worker already has a session (1:1 mapping).
        """
        with self._lock:
            if worker_id in self._sessions:
                raise ValueError(f"Worker {worker_id} already has a session")

            # Create tmux session with worker-specific name
            name = session_name or f"qn-{worker_id}"
            session = TmuxSession(session_name=name)

            # Create lifecycle hooks
            lifecycle = LifecycleHooks()

            # Create pattern matcher
            patterns = PatternMatcher(session)

            managed = ManagedSession(
                worker_id=worker_id,
                session=session,
                lifecycle=lifecycle,
                patterns=patterns,
            )

            self._sessions[worker_id] = managed
            return managed

    def get(self, worker_id: str) -> ManagedSession | None:
        """Get session by worker ID."""
        return self._sessions.get(worker_id)

    def remove(self, worker_id: str, force: bool = False) -> bool:
        """
        Remove a worker's session.

        Stops the session if running.
        Returns True if session was removed.
        """
        with self._lock:
            managed = self._sessions.get(worker_id)
            if not managed:
                return False

            # Stop pattern watching
            if managed.patterns:
                managed.patterns.stop_watching()

            # Stop session
            if managed.session.state == PytermSessionState.RUNNING:
                managed.session.stop(force=force)

            # Transition lifecycle to terminated
            managed.lifecycle.transition(WorkerState.TERMINATED)

            del self._sessions[worker_id]
            return True

    def list_active(self) -> list[ManagedSession]:
        """List all sessions in RUNNING state."""
        return [
            m for m in self._sessions.values()
            if m.session.state == PytermSessionState.RUNNING
        ]

    def list_by_worker_state(self, state: WorkerState) -> list[ManagedSession]:
        """List sessions by worker lifecycle state."""
        return [
            m for m in self._sessions.values()
            if m.lifecycle.state == state
        ]

    def __iter__(self) -> Iterator[ManagedSession]:
        """Iterate over all managed sessions."""
        return iter(self._sessions.values())

    def __len__(self) -> int:
        """Number of managed sessions."""
        return len(self._sessions)

    def __contains__(self, worker_id: str) -> bool:
        """Check if worker has a session."""
        return worker_id in self._sessions

    def cleanup_exited(self) -> int:
        """
        Remove all sessions in EXITED or ERROR state.

        Returns number of sessions cleaned up.
        """
        to_remove = [
            worker_id
            for worker_id, managed in self._sessions.items()
            if managed.session.state in (PytermSessionState.EXITED, PytermSessionState.ERROR)
        ]

        for worker_id in to_remove:
            self.remove(worker_id)

        return len(to_remove)

    def stop_all(self, force: bool = False) -> None:
        """Stop all sessions."""
        for managed in list(self._sessions.values()):
            if managed.session.state == PytermSessionState.RUNNING:
                managed.session.stop(force=force)
