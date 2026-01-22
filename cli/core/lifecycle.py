"""
Lifecycle state validation for beads.

Enforces valid state transitions based on bead type configuration.
Validates that beads can only be closed when in terminal states.
"""

from dataclasses import dataclass
from typing import Optional

from .constants import LIFECYCLE_INITIAL_STATES, LIFECYCLE_STATES


class LifecycleError(Exception):
    """Base exception for lifecycle validation errors."""

    pass


class InvalidStateTransitionError(LifecycleError):
    """Raised when attempting an invalid state transition."""

    def __init__(
        self,
        bead_id: str,
        bead_type: str,
        current_state: str,
        target_state: str,
        allowed_states: list[str],
    ):
        self.bead_id = bead_id
        self.bead_type = bead_type
        self.current_state = current_state
        self.target_state = target_state
        self.allowed_states = allowed_states

        if allowed_states:
            allowed_str = ", ".join(allowed_states)
            message = (
                f"Cannot transition bead '{bead_id}' from '{current_state}' to '{target_state}'. "
                f"Allowed transitions: {allowed_str}"
            )
        else:
            message = (
                f"Cannot transition bead '{bead_id}' from '{current_state}'. "
                f"State '{current_state}' is terminal."
            )
        super().__init__(message)


class CannotCloseBeadError(LifecycleError):
    """Raised when attempting to close a bead in a non-terminal state."""

    def __init__(
        self,
        bead_id: str,
        bead_type: str,
        current_state: str,
        terminal_states: list[str],
    ):
        self.bead_id = bead_id
        self.bead_type = bead_type
        self.current_state = current_state
        self.terminal_states = terminal_states

        terminal_str = ", ".join(terminal_states)
        # Provide actionable guidance
        if bead_type == "task":
            if current_state == "review":
                guidance = "Complete the review first."
            elif current_state == "implementation":
                guidance = "Move to review state before closing."
            elif current_state == "planning":
                guidance = "Begin implementation or reject the task."
            elif current_state == "investigation":
                guidance = "Complete investigation and move to planning."
            else:
                guidance = f"Move to a terminal state: {terminal_str}"
        elif bead_type == "bug":
            if current_state == "review":
                guidance = "Complete the fix review."
            elif current_state == "fixing":
                guidance = "Submit for review or mark as wontfix."
            elif current_state == "investigation":
                guidance = "Move to fixing or mark as wontfix/duplicate."
            elif current_state == "triage":
                guidance = "Triage the bug first."
            else:
                guidance = f"Move to a terminal state: {terminal_str}"
        elif bead_type == "feature":
            if current_state == "review":
                guidance = "Complete the feature review."
            elif current_state == "implementation":
                guidance = "Submit for review or defer the feature."
            elif current_state == "design":
                guidance = "Begin implementation or reject/defer."
            elif current_state == "discovery":
                guidance = "Complete discovery and move to design."
            else:
                guidance = f"Move to a terminal state: {terminal_str}"
        else:
            guidance = f"Move to a terminal state: {terminal_str}"

        message = (
            f"Cannot close bead '{bead_id}': in '{current_state}' state. {guidance}"
        )
        super().__init__(message)


class BeadBlockedError(LifecycleError):
    """Raised when attempting to close a bead that has unresolved dependencies."""

    def __init__(
        self,
        bead_id: str,
        blocking_beads: list[str],
    ):
        self.bead_id = bead_id
        self.blocking_beads = blocking_beads

        blockers_str = ", ".join(blocking_beads[:5])
        if len(blocking_beads) > 5:
            blockers_str += f" (and {len(blocking_beads) - 5} more)"

        message = (
            f"Cannot close bead '{bead_id}': blocked by {len(blocking_beads)} "
            f"unresolved dependencies: {blockers_str}. "
            "Resolve or close blocking beads first."
        )
        super().__init__(message)


class InvalidStateError(LifecycleError):
    """Raised when a state is not valid for a bead type."""

    def __init__(
        self,
        bead_id: str,
        bead_type: str,
        invalid_state: str,
        valid_states: list[str],
    ):
        self.bead_id = bead_id
        self.bead_type = bead_type
        self.invalid_state = invalid_state
        self.valid_states = valid_states

        valid_str = ", ".join(valid_states)
        message = (
            f"Invalid state '{invalid_state}' for {bead_type} bead '{bead_id}'. "
            f"Valid states: {valid_str}"
        )
        super().__init__(message)


@dataclass
class LifecycleConfig:
    """Configuration for a bead type's lifecycle."""

    bead_type: str
    states: list[str]
    terminal: list[str]
    transitions: dict[str, list[str]]

    @classmethod
    def for_type(cls, bead_type: str) -> "LifecycleConfig":
        """Get lifecycle configuration for a bead type.

        Args:
            bead_type: The bead type (task, bug, feature, etc.)

        Returns:
            LifecycleConfig for the bead type
        """
        config = LIFECYCLE_STATES.get(bead_type, LIFECYCLE_STATES["default"])
        return cls(
            bead_type=bead_type,
            states=config["states"],
            terminal=config["terminal"],
            transitions=config["transitions"],
        )

    def get_initial_state(self) -> str:
        """Get the initial state for this bead type.

        Returns:
            Initial state name
        """
        return LIFECYCLE_INITIAL_STATES.get(
            self.bead_type, LIFECYCLE_INITIAL_STATES["default"]
        )

    def is_valid_state(self, state: str) -> bool:
        """Check if a state is valid for this bead type.

        Args:
            state: State to check

        Returns:
            True if state is valid
        """
        all_states = set(self.states) | set(self.terminal)
        return state in all_states

    def is_terminal(self, state: str) -> bool:
        """Check if a state is a terminal state.

        Args:
            state: State to check

        Returns:
            True if state is terminal
        """
        return state in self.terminal

    def get_allowed_transitions(self, current_state: str) -> list[str]:
        """Get list of states that can be transitioned to from current state.

        Args:
            current_state: Current state

        Returns:
            List of allowed target states
        """
        return self.transitions.get(current_state, [])

    def can_transition(self, current_state: str, target_state: str) -> bool:
        """Check if a transition from current to target state is allowed.

        Args:
            current_state: Current state
            target_state: Target state

        Returns:
            True if transition is allowed
        """
        allowed = self.get_allowed_transitions(current_state)
        return target_state in allowed


def validate_state_transition(
    bead_id: str,
    bead_type: str,
    current_state: str,
    target_state: str,
) -> None:
    """Validate that a state transition is allowed.

    Args:
        bead_id: Bead identifier
        bead_type: Type of bead (task, bug, feature, etc.)
        current_state: Current lifecycle state
        target_state: Target lifecycle state

    Raises:
        InvalidStateTransitionError: If transition is not allowed
        InvalidStateError: If current or target state is invalid
    """
    config = LifecycleConfig.for_type(bead_type)

    # Check if current state is valid
    if not config.is_valid_state(current_state):
        all_states = list(set(config.states) | set(config.terminal))
        raise InvalidStateError(bead_id, bead_type, current_state, all_states)

    # Check if target state is valid
    if not config.is_valid_state(target_state):
        all_states = list(set(config.states) | set(config.terminal))
        raise InvalidStateError(bead_id, bead_type, target_state, all_states)

    # Check if transition is allowed
    if not config.can_transition(current_state, target_state):
        allowed = config.get_allowed_transitions(current_state)
        raise InvalidStateTransitionError(
            bead_id, bead_type, current_state, target_state, allowed
        )


def validate_can_close(
    bead_id: str,
    bead_type: str,
    current_state: str,
) -> None:
    """Validate that a bead can be closed.

    A bead can only be closed when in a terminal state.

    Args:
        bead_id: Bead identifier
        bead_type: Type of bead
        current_state: Current lifecycle state

    Raises:
        CannotCloseBeadError: If bead is not in a terminal state
        InvalidStateError: If current state is invalid
    """
    config = LifecycleConfig.for_type(bead_type)

    # Check if current state is valid
    if not config.is_valid_state(current_state):
        all_states = list(set(config.states) | set(config.terminal))
        raise InvalidStateError(bead_id, bead_type, current_state, all_states)

    # Check if in terminal state
    if not config.is_terminal(current_state):
        raise CannotCloseBeadError(bead_id, bead_type, current_state, config.terminal)


def get_initial_state(bead_type: str) -> str:
    """Get the initial state for a bead type.

    Args:
        bead_type: Type of bead

    Returns:
        Initial state name
    """
    config = LifecycleConfig.for_type(bead_type)
    return config.get_initial_state()


def get_valid_states(bead_type: str) -> list[str]:
    """Get all valid states for a bead type.

    Args:
        bead_type: Type of bead

    Returns:
        List of valid state names
    """
    config = LifecycleConfig.for_type(bead_type)
    return list(set(config.states) | set(config.terminal))


def get_terminal_states(bead_type: str) -> list[str]:
    """Get terminal states for a bead type.

    Args:
        bead_type: Type of bead

    Returns:
        List of terminal state names
    """
    config = LifecycleConfig.for_type(bead_type)
    return config.terminal


def get_next_states(bead_type: str, current_state: str) -> list[str]:
    """Get allowed next states from current state.

    Args:
        bead_type: Type of bead
        current_state: Current state

    Returns:
        List of allowed target states
    """
    config = LifecycleConfig.for_type(bead_type)
    return config.get_allowed_transitions(current_state)


def parse_status_from_args(args: list[str]) -> Optional[str]:
    """Parse the status/state value from bd command arguments.

    Looks for --status or --state flags and extracts the value.

    Args:
        args: Command line arguments

    Returns:
        Status value or None if not found
    """
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--status", "--state", "-s"):
            # Value is next argument
            if i + 1 < len(args):
                return args[i + 1]
        elif arg.startswith("--status="):
            return arg.split("=", 1)[1]
        elif arg.startswith("--state="):
            return arg.split("=", 1)[1]
        i += 1
    return None
