"""Worker state machine with explicit state transitions.

This module re-exports WorkerState and transition logic from the canonical
source (shared.core.state) with local naming conventions for backwards
compatibility.

The canonical source is shared.core.state - this module provides:
- WorkerState enum (re-exported)
- VALID_TRANSITIONS (alias for WORKER_STATE_TRANSITIONS)
- InvalidTransition (alias for InvalidStateTransition)
- can_transition (alias for can_transition_worker)
- transition (alias for transition_worker)
"""

from shared.core.state import (
    InvalidStateTransition,
    WorkerState,
    WORKER_STATE_TRANSITIONS,
    can_transition_worker,
    transition_worker,
)

# Re-export WorkerState directly
__all__ = [
    "WorkerState",
    "InvalidTransition",
    "VALID_TRANSITIONS",
    "can_transition",
    "transition",
]

# Alias for backwards compatibility with existing code
VALID_TRANSITIONS = WORKER_STATE_TRANSITIONS


class InvalidTransition(InvalidStateTransition):
    """Raised when an invalid state transition is attempted.

    Alias for InvalidStateTransition with simplified signature.
    """

    def __init__(self, from_state: WorkerState, to_state: WorkerState) -> None:
        valid = VALID_TRANSITIONS.get(from_state, [])
        super().__init__(from_state, to_state, valid)


def can_transition(from_state: WorkerState, to_state: WorkerState) -> bool:
    """Check if a state transition is valid.

    Args:
        from_state: The current worker state.
        to_state: The desired target state.

    Returns:
        True if the transition is valid, False otherwise.
    """
    return can_transition_worker(from_state, to_state)


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
