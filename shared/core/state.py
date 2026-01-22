"""
Canonical state definitions for QuinnAI.

Worker state is the primary state - Session state maps to/from it.
Per CLAUDE.md: "Session = Worker's Brain. Session ON = awake. Session OFF = asleep."

State Hierarchy:
    WorkerState: The worker's lifecycle state (what the worker IS doing)
    SessionState: The session's runtime state (HOW the brain is running)

Mapping:
    WorkerState.PENDING     -> SessionState.STOPPED (not yet started)
    WorkerState.ONBOARDING  -> SessionState.STARTING (initializing)
    WorkerState.ACTIVE      -> SessionState.IDLE (ready for work)
    WorkerState.WORKING     -> SessionState.RUNNING (processing)
    WorkerState.STUCK       -> SessionState.IDLE (needs escalation, but brain still works)
    WorkerState.OFFBOARDING -> SessionState.STOPPED (graceful shutdown)
    WorkerState.TERMINATED  -> SessionState.STOPPED (final)

    SessionState.CRASHED has no direct WorkerState mapping - handled via error recovery.
"""

from enum import Enum
from typing import Dict, List


# =============================================================================
# WorkerState - Primary State (What the worker IS doing)
# =============================================================================


class WorkerState(Enum):
    """Worker lifecycle states.

    This is the canonical state enum for workers. All worker state
    transitions must use this enum.
    """

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


# Valid state transitions for workers
WORKER_STATE_TRANSITIONS: Dict[WorkerState, List[WorkerState]] = {
    WorkerState.PENDING: [WorkerState.ONBOARDING, WorkerState.TERMINATED],
    WorkerState.ONBOARDING: [WorkerState.ACTIVE, WorkerState.TERMINATED],
    WorkerState.ACTIVE: [WorkerState.WORKING, WorkerState.OFFBOARDING, WorkerState.STUCK],
    WorkerState.WORKING: [WorkerState.ACTIVE, WorkerState.STUCK, WorkerState.OFFBOARDING],
    WorkerState.STUCK: [WorkerState.ACTIVE, WorkerState.OFFBOARDING],
    WorkerState.OFFBOARDING: [WorkerState.TERMINATED],
    WorkerState.TERMINATED: [],  # Final state - no transitions allowed
}


# =============================================================================
# SessionState - Runtime State (How the brain is running)
# =============================================================================


class SessionState(Enum):
    """Session runtime states.

    SessionState describes the runtime status of a worker's session (brain).
    It maps to WorkerState but operates at a lower level of abstraction.
    """

    STOPPED = "stopped"
    """Session is not running (worker asleep)."""

    STARTING = "starting"
    """Session is initializing (worker waking up)."""

    IDLE = "idle"
    """Session is running, waiting for input (worker ready)."""

    RUNNING = "running"
    """Session is actively processing (worker working)."""

    CRASHED = "crashed"
    """Session terminated unexpectedly (error state)."""


# Valid state transitions for sessions
SESSION_STATE_TRANSITIONS: Dict[SessionState, List[SessionState]] = {
    SessionState.STOPPED: [SessionState.STARTING],
    SessionState.STARTING: [SessionState.IDLE, SessionState.RUNNING, SessionState.CRASHED],
    SessionState.IDLE: [SessionState.RUNNING, SessionState.STOPPED, SessionState.CRASHED],
    SessionState.RUNNING: [SessionState.IDLE, SessionState.CRASHED],
    SessionState.CRASHED: [SessionState.STARTING, SessionState.STOPPED],
}


# =============================================================================
# State Mapping - Worker <-> Session
# =============================================================================


# Worker -> Session mapping (many-to-one)
WORKER_TO_SESSION_STATE: Dict[WorkerState, SessionState] = {
    WorkerState.PENDING: SessionState.STOPPED,
    WorkerState.ONBOARDING: SessionState.STARTING,
    WorkerState.ACTIVE: SessionState.IDLE,
    WorkerState.WORKING: SessionState.RUNNING,
    WorkerState.STUCK: SessionState.IDLE,  # Brain still works, worker just needs help
    WorkerState.OFFBOARDING: SessionState.STOPPED,
    WorkerState.TERMINATED: SessionState.STOPPED,
}


# Session -> Worker mapping (for recovery/sync)
# Note: This is lossy - STOPPED could be PENDING, OFFBOARDING, or TERMINATED
SESSION_TO_WORKER_STATE: Dict[SessionState, WorkerState] = {
    SessionState.STOPPED: WorkerState.PENDING,  # Default assumption
    SessionState.STARTING: WorkerState.ONBOARDING,
    SessionState.IDLE: WorkerState.ACTIVE,
    SessionState.RUNNING: WorkerState.WORKING,
    SessionState.CRASHED: WorkerState.STUCK,  # Crash = stuck, needs intervention
}


# =============================================================================
# Transition Functions
# =============================================================================


class InvalidStateTransition(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: Enum, to_state: Enum, valid: List[Enum]) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.valid = valid
        valid_names = [s.value for s in valid]
        super().__init__(
            f"Invalid transition from {from_state.value} to {to_state.value}. "
            f"Valid: {valid_names}"
        )


def can_transition_worker(from_state: WorkerState, to_state: WorkerState) -> bool:
    """Check if a worker state transition is valid."""
    valid = WORKER_STATE_TRANSITIONS.get(from_state, [])
    return to_state in valid


def can_transition_session(from_state: SessionState, to_state: SessionState) -> bool:
    """Check if a session state transition is valid."""
    valid = SESSION_STATE_TRANSITIONS.get(from_state, [])
    return to_state in valid


def transition_worker(from_state: WorkerState, to_state: WorkerState) -> WorkerState:
    """Perform a worker state transition if valid.

    Raises:
        InvalidStateTransition: If the transition is not allowed.
    """
    if not can_transition_worker(from_state, to_state):
        valid = WORKER_STATE_TRANSITIONS.get(from_state, [])
        raise InvalidStateTransition(from_state, to_state, valid)
    return to_state


def transition_session(from_state: SessionState, to_state: SessionState) -> SessionState:
    """Perform a session state transition if valid.

    Raises:
        InvalidStateTransition: If the transition is not allowed.
    """
    if not can_transition_session(from_state, to_state):
        valid = SESSION_STATE_TRANSITIONS.get(from_state, [])
        raise InvalidStateTransition(from_state, to_state, valid)
    return to_state


def worker_state_to_session(worker_state: WorkerState) -> SessionState:
    """Map worker state to corresponding session state."""
    return WORKER_TO_SESSION_STATE[worker_state]


def session_state_to_worker(
    session_state: SessionState,
    current_worker_state: WorkerState | None = None,
) -> WorkerState:
    """Map session state to worker state.

    Args:
        session_state: Current session state
        current_worker_state: Optional current worker state for context
            (helps disambiguate STOPPED -> PENDING vs TERMINATED)

    Returns:
        Inferred worker state
    """
    # If we have context and session is STOPPED, preserve terminal states
    if session_state == SessionState.STOPPED and current_worker_state:
        if current_worker_state in (WorkerState.TERMINATED, WorkerState.OFFBOARDING):
            return current_worker_state

    return SESSION_TO_WORKER_STATE[session_state]


def is_worker_awake(worker_state: WorkerState) -> bool:
    """Check if worker should have an active session (brain awake)."""
    session_state = worker_state_to_session(worker_state)
    return session_state not in (SessionState.STOPPED,)


def is_worker_responsive(worker_state: WorkerState) -> bool:
    """Check if worker can accept new work."""
    return worker_state in (WorkerState.ACTIVE, WorkerState.WORKING)


# =============================================================================
# WorkState - Work Item Lifecycle (Beads)
# =============================================================================


class WorkState(Enum):
    """Work item (bead) lifecycle states.

    Per CLAUDE.md: "Lifecycles = State Determines Behavior. Everything has
    state (org, worker, work). State determines behavior, not commands."

    Work items progress through a lifecycle from creation to completion:
        DRAFT -> OPEN -> IN_PROGRESS -> REVIEW -> CLOSED

    Additional states handle exceptional cases:
        BLOCKED: Waiting on external dependency
        CANCELLED: Work was abandoned
    """

    DRAFT = "draft"
    """Work item created but not yet ready for work."""

    OPEN = "open"
    """Work item is ready to be picked up by a worker."""

    IN_PROGRESS = "in_progress"
    """Work item is actively being worked on."""

    REVIEW = "review"
    """Work is complete, awaiting review/approval."""

    BLOCKED = "blocked"
    """Work is paused, waiting on external dependency."""

    CLOSED = "closed"
    """Work is complete and accepted."""

    CANCELLED = "cancelled"
    """Work was abandoned before completion."""


# Valid state transitions for work items
WORK_STATE_TRANSITIONS: Dict[WorkState, List[WorkState]] = {
    WorkState.DRAFT: [WorkState.OPEN, WorkState.CANCELLED],
    WorkState.OPEN: [WorkState.IN_PROGRESS, WorkState.BLOCKED, WorkState.CANCELLED],
    WorkState.IN_PROGRESS: [
        WorkState.REVIEW,
        WorkState.BLOCKED,
        WorkState.OPEN,  # Return to queue
        WorkState.CANCELLED,
    ],
    WorkState.REVIEW: [
        WorkState.CLOSED,
        WorkState.IN_PROGRESS,  # Needs more work
        WorkState.CANCELLED,
    ],
    WorkState.BLOCKED: [
        WorkState.OPEN,  # Unblocked, back to queue
        WorkState.IN_PROGRESS,  # Unblocked, continue work
        WorkState.CANCELLED,
    ],
    WorkState.CLOSED: [],  # Final state - no transitions
    WorkState.CANCELLED: [],  # Final state - no transitions
}


def can_transition_work(from_state: WorkState, to_state: WorkState) -> bool:
    """Check if a work state transition is valid."""
    valid = WORK_STATE_TRANSITIONS.get(from_state, [])
    return to_state in valid


def transition_work(from_state: WorkState, to_state: WorkState) -> WorkState:
    """Perform a work state transition if valid.

    Raises:
        InvalidStateTransition: If the transition is not allowed.
    """
    if not can_transition_work(from_state, to_state):
        valid = WORK_STATE_TRANSITIONS.get(from_state, [])
        raise InvalidStateTransition(from_state, to_state, valid)
    return to_state


def is_work_terminal(work_state: WorkState) -> bool:
    """Check if work is in a terminal state (no further transitions)."""
    return work_state in (WorkState.CLOSED, WorkState.CANCELLED)


def is_work_active(work_state: WorkState) -> bool:
    """Check if work is in an active state (being worked on)."""
    return work_state in (WorkState.IN_PROGRESS, WorkState.REVIEW)
