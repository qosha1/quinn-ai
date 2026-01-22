"""Worker state machine with explicit state transitions.

This module defines the WorkerState enum and state transition logic for
managing worker lifecycle states in the agentic tools system.
"""

from enum import Enum
from typing import Dict, List


class WorkerState(Enum):
    """Enumeration of possible worker states in the lifecycle."""

    PENDING = "pending"
    """Initial state when worker is created but not yet started."""

    ONBOARDING = "onboarding"
    """Worker is being initialized and configured."""

    ACTIVE = "active"
    """Worker is ready and waiting for work assignments."""

    WORKING = "working"
    """Worker is currently executing a task."""

    STUCK = "stuck"
    """Worker encountered an issue and needs escalation."""

    OFFBOARDING = "offboarding"
    """Worker is gracefully shutting down."""

    TERMINATED = "terminated"
    """Final state - worker has been shut down."""


class InvalidTransition(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: WorkerState, to_state: WorkerState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition from {from_state.value} to {to_state.value}"
        )


# Valid state transitions mapping
VALID_TRANSITIONS: Dict[WorkerState, List[WorkerState]] = {
    WorkerState.PENDING: [WorkerState.ONBOARDING, WorkerState.TERMINATED],
    WorkerState.ONBOARDING: [WorkerState.ACTIVE, WorkerState.TERMINATED],
    WorkerState.ACTIVE: [WorkerState.WORKING, WorkerState.OFFBOARDING, WorkerState.STUCK],
    WorkerState.WORKING: [WorkerState.ACTIVE, WorkerState.STUCK, WorkerState.OFFBOARDING],
    WorkerState.STUCK: [WorkerState.ACTIVE, WorkerState.OFFBOARDING],
    WorkerState.OFFBOARDING: [WorkerState.TERMINATED],
    WorkerState.TERMINATED: [],  # Final state - no transitions allowed
}


def can_transition(from_state: WorkerState, to_state: WorkerState) -> bool:
    """Check if a state transition is valid.

    Args:
        from_state: The current worker state.
        to_state: The desired target state.

    Returns:
        True if the transition is valid, False otherwise.
    """
    valid_targets = VALID_TRANSITIONS.get(from_state, [])
    return to_state in valid_targets


def transition(from_state: WorkerState, to_state: WorkerState) -> WorkerState:
    """Perform a state transition if valid.

    Args:
        from_state: The current worker state.
        to_state: The desired target state.

    Returns:
        The new state if transition is valid.

    Raises:
        InvalidTransition: If the transition is not allowed.
    """
    if not can_transition(from_state, to_state):
        raise InvalidTransition(from_state, to_state)
    return to_state
