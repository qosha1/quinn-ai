"""
Session-to-Worker state synchronization.

Ensures the worker runtime state stays in sync with the session state:
- Session STARTING → Worker runtime 'starting'
- Session RUNNING → Worker runtime 'running'
- Session IDLE → Worker runtime 'idle'
- Session STOPPED → Worker runtime 'stopped'
- Session CRASHED → Worker runtime 'crashed'

Also handles:
- PID-based crash detection
- Heartbeat timeout detection
- Clean unbind on termination
"""

import os
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import Database
    from ..session import SessionInterface, SessionState
    from .binding_manager import SessionBindingManager

# Default heartbeat threshold in seconds
DEFAULT_HEARTBEAT_THRESHOLD = 60


class StateSyncConfig:
    """Configuration for state sync monitoring."""

    heartbeat_threshold_seconds: int = DEFAULT_HEARTBEAT_THRESHOLD
    check_interval_seconds: int = 10
    auto_unbind_on_crash: bool = True
    auto_unbind_on_stop: bool = False


class SessionStateSync:
    """Synchronizes session state to worker runtime state.

    Monitors sessions and updates corresponding worker runtime states.
    Handles crash detection via PID monitoring and heartbeat checks.

    Example:
        sync = SessionStateSync(db, binding_manager)
        sync.register_session(session, worker_id)

        # Later, check for crashes
        sync.check_all()
    """

    def __init__(
        self,
        db: "Database",
        binding_manager: "SessionBindingManager",
        config: Optional[StateSyncConfig] = None,
    ):
        """Initialize state sync.

        Args:
            db: Database for updating worker state
            binding_manager: Binding manager to track sessions
            config: Optional configuration
        """
        self._db = db
        self._binding_manager = binding_manager
        self._config = config or StateSyncConfig()
        self._lock = threading.RLock()

        # Track last known states for change detection
        self._last_states: dict[str, "SessionState"] = {}

        # Crash callbacks
        self._on_crash_callbacks: list[Callable[[str, str], None]] = []

    def register_session(
        self,
        session: "SessionInterface",
        worker_id: str,
    ) -> None:
        """Register a session for state sync monitoring.

        Sets up callbacks to keep worker state in sync with session state.

        Args:
            session: Session to monitor
            worker_id: Worker ID to sync state to
        """
        from ..session import SessionState

        session_id = str(session.id)

        # Store initial state
        with self._lock:
            self._last_states[session_id] = session.state

        # Set up state change callback
        def on_state_change(old: "SessionState", new: "SessionState") -> None:
            self._handle_state_change(worker_id, session_id, old, new)

        session.on_state_change(on_state_change)

    def _handle_state_change(
        self,
        worker_id: str,
        session_id: str,
        old_state: "SessionState",
        new_state: "SessionState",
    ) -> None:
        """Handle session state change.

        Updates worker runtime state and optionally unbinds on terminal states.

        Args:
            worker_id: Worker to update
            session_id: Session that changed
            old_state: Previous session state
            new_state: New session state
        """
        from ..session import SessionState
        from ..queries import update_worker_runtime_status

        # Update tracking
        with self._lock:
            self._last_states[session_id] = new_state

        # Map session state to worker runtime status
        runtime_status = new_state.value

        # Update worker runtime state in DB
        update_worker_runtime_status(self._db, worker_id, runtime_status)

        # Handle crash detection
        if new_state == SessionState.CRASHED:
            self._handle_crash(worker_id, session_id)

        # Auto-unbind on terminal states if configured
        if new_state == SessionState.CRASHED and self._config.auto_unbind_on_crash:
            self._binding_manager.unbind(worker_id)
        elif new_state == SessionState.STOPPED and self._config.auto_unbind_on_stop:
            self._binding_manager.unbind(worker_id)

    def _handle_crash(self, worker_id: str, session_id: str) -> None:
        """Handle session crash.

        Notifies registered callbacks and logs the event.

        Args:
            worker_id: Worker whose session crashed
            session_id: Session that crashed
        """
        # Notify callbacks
        for callback in self._on_crash_callbacks:
            try:
                callback(worker_id, session_id)
            except Exception:
                # Intentionally swallowed: crash handling must complete even if
                # a callback fails. Callback errors are less critical than
                # notifying remaining callbacks about the crash.
                pass

    def on_crash(self, callback: Callable[[str, str], None]) -> None:
        """Register callback for session crashes.

        Args:
            callback: Function(worker_id, session_id) called on crash
        """
        self._on_crash_callbacks.append(callback)

    def check_all(self) -> dict:
        """Check all registered sessions for crashes.

        Uses PID monitoring to detect crashed processes.

        Returns:
            Dict with check results:
            - healthy: list of healthy (worker_id, session_id) tuples
            - crashed: list of crashed (worker_id, session_id) tuples
            - unknown: list of unknown state (worker_id, session_id) tuples
        """
        from ..session import SessionState

        results = {
            "healthy": [],
            "crashed": [],
            "unknown": [],
        }

        bindings = self._binding_manager.list_bindings()

        for binding in bindings:
            worker_id = binding.worker_id
            session_id = binding.session_id
            pid = binding.pid

            # Get session instance if available
            session = self._binding_manager.get_session(session_id)

            if session is not None:
                # Check session state directly
                if session.state == SessionState.CRASHED:
                    results["crashed"].append((worker_id, session_id))
                elif session.state in (
                    SessionState.STARTING,
                    SessionState.RUNNING,
                    SessionState.IDLE,
                ):
                    results["healthy"].append((worker_id, session_id))
                else:
                    results["unknown"].append((worker_id, session_id))
            elif pid is not None:
                # Check PID
                if self._is_process_alive(pid):
                    results["healthy"].append((worker_id, session_id))
                else:
                    results["crashed"].append((worker_id, session_id))
                    self._mark_crashed(worker_id, session_id)
            else:
                results["unknown"].append((worker_id, session_id))

        return results

    def check_heartbeats(self) -> dict:
        """Check worker heartbeats for stale sessions.

        Checks last_activity in worker_state against threshold.

        Returns:
            Dict with check results:
            - active: list of active worker_ids
            - stale: list of stale worker_ids
        """
        from ..queries import get_worker_state

        results = {
            "active": [],
            "stale": [],
        }

        threshold = datetime.now() - timedelta(
            seconds=self._config.heartbeat_threshold_seconds
        )

        bindings = self._binding_manager.list_bindings()

        for binding in bindings:
            worker_id = binding.worker_id

            state = get_worker_state(self._db, worker_id)
            if state is None:
                results["stale"].append(worker_id)
                continue

            last_activity = state.last_activity
            if last_activity is None:
                results["stale"].append(worker_id)
                continue

            # Parse datetime if string
            if isinstance(last_activity, str):
                last_activity = datetime.fromisoformat(last_activity)

            if last_activity < threshold:
                results["stale"].append(worker_id)
            else:
                results["active"].append(worker_id)

        return results

    def _mark_crashed(self, worker_id: str, session_id: str) -> None:
        """Mark a worker as crashed due to PID death.

        Args:
            worker_id: Worker to mark
            session_id: Session that died
        """
        from ..queries import update_worker_runtime_status

        update_worker_runtime_status(self._db, worker_id, "crashed")
        self._handle_crash(worker_id, session_id)

        if self._config.auto_unbind_on_crash:
            self._binding_manager.unbind(worker_id)

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process is still running.

        Args:
            pid: Process ID to check

        Returns:
            True if process exists
        """
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


# Module-level sync instance
_default_sync: Optional[SessionStateSync] = None
_sync_lock = threading.Lock()


def get_state_sync(
    db: "Database",
    binding_manager: "SessionBindingManager",
) -> SessionStateSync:
    """Get or create the default SessionStateSync.

    Args:
        db: Database for state updates
        binding_manager: Binding manager for session tracking

    Returns:
        SessionStateSync instance
    """
    global _default_sync

    with _sync_lock:
        if _default_sync is None:
            _default_sync = SessionStateSync(db, binding_manager)
        return _default_sync


def reset_state_sync() -> None:
    """Reset the default state sync (for testing)."""
    global _default_sync

    with _sync_lock:
        _default_sync = None
