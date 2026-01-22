"""
Lifecycle hooks for worker state management.

Worker lifecycle: pending -> onboarding -> active -> offboarding -> terminated
Session state maps to worker state.
"""

from dataclasses import dataclass, field
from typing import Callable

from shared.pyterm.protocols import SessionState, WorkerState


# Valid state transitions
VALID_TRANSITIONS: dict[WorkerState, list[WorkerState]] = {
    WorkerState.PENDING: [WorkerState.ONBOARDING, WorkerState.TERMINATED],
    WorkerState.ONBOARDING: [WorkerState.ACTIVE, WorkerState.TERMINATED],
    WorkerState.ACTIVE: [WorkerState.OFFBOARDING, WorkerState.TERMINATED],
    WorkerState.OFFBOARDING: [WorkerState.TERMINATED],
    WorkerState.TERMINATED: [],  # Terminal state
}


def session_to_worker_state(session_state: SessionState) -> WorkerState:
    """Map session state to worker state."""
    mapping = {
        SessionState.IDLE: WorkerState.PENDING,
        SessionState.RUNNING: WorkerState.ACTIVE,
        SessionState.EXITED: WorkerState.TERMINATED,
        SessionState.ERROR: WorkerState.TERMINATED,
    }
    return mapping[session_state]


StateChangeCallback = Callable[[WorkerState, WorkerState], None]
StateEnterCallback = Callable[[WorkerState], None]
StateExitCallback = Callable[[WorkerState], None]


@dataclass
class LifecycleHooks:
    """
    Manages lifecycle hooks for worker state transitions.

    Hooks can be registered for:
    - State changes (any transition)
    - Entering a specific state
    - Exiting a specific state
    """

    _state: WorkerState = WorkerState.PENDING
    _on_change: list[StateChangeCallback] = field(default_factory=list)
    _on_enter: dict[WorkerState, list[StateEnterCallback]] = field(default_factory=dict)
    _on_exit: dict[WorkerState, list[StateExitCallback]] = field(default_factory=dict)

    @property
    def state(self) -> WorkerState:
        """Current worker state."""
        return self._state

    def transition(self, new_state: WorkerState) -> bool:
        """
        Transition to a new state.

        Returns True if transition was valid, False otherwise.
        Fires hooks in order: exit(old) -> change(old, new) -> enter(new)
        """
        if new_state not in VALID_TRANSITIONS.get(self._state, []):
            return False

        old_state = self._state

        # Fire exit hooks for old state
        for cb in self._on_exit.get(old_state, []):
            cb(old_state)

        self._state = new_state

        # Fire change hooks
        for cb in self._on_change:
            cb(old_state, new_state)

        # Fire enter hooks for new state
        for cb in self._on_enter.get(new_state, []):
            cb(new_state)

        return True

    def on_change(self, callback: StateChangeCallback) -> None:
        """Register callback for any state change."""
        self._on_change.append(callback)

    def on_enter(self, state: WorkerState, callback: StateEnterCallback) -> None:
        """Register callback for entering a specific state."""
        if state not in self._on_enter:
            self._on_enter[state] = []
        self._on_enter[state].append(callback)

    def on_exit(self, state: WorkerState, callback: StateExitCallback) -> None:
        """Register callback for exiting a specific state."""
        if state not in self._on_exit:
            self._on_exit[state] = []
        self._on_exit[state].append(callback)

    def can_transition(self, new_state: WorkerState) -> bool:
        """Check if transition to new_state is valid."""
        return new_state in VALID_TRANSITIONS.get(self._state, [])

    def reset(self) -> None:
        """Reset to initial state (for testing)."""
        self._state = WorkerState.PENDING
