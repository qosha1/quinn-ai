"""
State monitoring abstraction for pyterm.

Provides provider-agnostic state monitoring with support for:
- Background polling via dedicated thread
- Explicit polling on-demand
- Callback-based state change notifications
- Provider-specific state detection logic
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from shared.pyterm.protocols import PytermSessionState


class MonitoringMode(Enum):
    """How state monitoring operates."""

    BACKGROUND = "background"
    """Continuous background polling via dedicated thread."""

    EXPLICIT = "explicit"
    """Manual polling only - no background thread."""

    CALLBACK = "callback"
    """Provider pushes state via callbacks (e.g., event stream)."""


@dataclass
class StateMonitorConfig:
    """Configuration for state monitoring.

    All values explicit - no defaults in interface.
    """

    mode: MonitoringMode
    """How monitoring operates (background, explicit, or callback)."""

    poll_interval: float
    """Seconds between polls in background mode (ignored for explicit/callback)."""

    idle_timeout: float
    """Seconds of no activity before assuming idle state."""

    error_retry_interval: float = 5.0
    """Seconds to wait before retrying after polling error."""

    max_consecutive_errors: int = 10
    """Max consecutive errors before stopping background monitor."""


StateChangeCallback = Callable[[PytermSessionState, PytermSessionState], None]
"""Callback signature: (old_state, new_state) -> None"""


class StateMonitor(ABC):
    """
    Abstract interface for monitoring session state.

    Implementations detect state changes from provider-specific signals
    (ANSI output patterns, event streams, file watchers, etc.) and notify
    subscribers via callbacks.

    Thread Safety:
    - All public methods must be thread-safe
    - Background polling runs in dedicated thread
    - Callbacks invoked outside locks to prevent deadlock
    """

    @abstractmethod
    def start_monitoring(self) -> None:
        """Start state monitoring according to configured mode.

        - BACKGROUND: Spawns background thread that polls continuously
        - EXPLICIT: No-op (user calls poll() manually)
        - CALLBACK: Registers with provider's event system

        Thread-safe. Idempotent (multiple calls are safe).
        """
        pass

    @abstractmethod
    def stop_monitoring(self) -> None:
        """Stop all monitoring and cleanup resources.

        - BACKGROUND: Signals thread to stop and joins
        - EXPLICIT: No-op
        - CALLBACK: Unregisters from provider events

        Thread-safe. Idempotent. Blocks until cleanup complete.
        """
        pass

    @abstractmethod
    def poll(self) -> PytermSessionState:
        """Explicitly check current state and update if changed.

        Performs one state detection cycle:
        1. Extract current session output
        2. Detect state from output (provider-specific)
        3. Compare to last known state
        4. If changed, notify subscribers

        Returns:
            Current session state after check

        Thread-safe. Can be called from any thread at any time.
        """
        pass

    @abstractmethod
    def subscribe(self, callback: StateChangeCallback) -> str:
        """Subscribe to state change notifications.

        Args:
            callback: Function called with (old_state, new_state) when state changes

        Returns:
            Subscription ID for later unsubscribe

        Thread-safe. Callback is invoked from monitoring thread in BACKGROUND mode.
        """
        pass

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a state change subscription.

        Args:
            subscription_id: ID returned from subscribe()

        Thread-safe. No-op if ID doesn't exist.
        """
        pass

    @property
    @abstractmethod
    def current_state(self) -> PytermSessionState:
        """Get last known state without polling.

        Returns cached state from last poll/detection.
        Thread-safe.
        """
        pass

    @property
    @abstractmethod
    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active.

        Thread-safe.
        """
        pass

    @abstractmethod
    def get_stats(self) -> dict:
        """Get monitoring statistics for diagnostics.

        Returns dict with:
        - poll_count: Total polls performed
        - state_changes: Total state changes detected
        - last_poll_time: Timestamp of last poll
        - error_count: Total errors encountered

        Thread-safe.
        """
        pass


class StateDetectionError(Exception):
    """Raised when state detection fails."""
    pass
