"""Tests for the worker state machine.

Tests the WorkerState enum, state transitions, and InvalidTransition exception.
"""

import pytest

from shared.wrkr.core.state import (
    VALID_TRANSITIONS,
    InvalidTransition,
    WorkerState,
    can_transition,
    transition,
)


class TestWorkerState:
    """Tests for WorkerState enum values."""

    def test_all_states_exist(self) -> None:
        """Verify all expected states are defined."""
        expected_states = [
            "PENDING",
            "ONBOARDING",
            "ACTIVE",
            "WORKING",
            "STUCK",
            "OFFBOARDING",
            "TERMINATED",
        ]
        for state_name in expected_states:
            assert hasattr(WorkerState, state_name)

    def test_state_values(self) -> None:
        """Verify state values are lowercase string versions."""
        assert WorkerState.PENDING.value == "pending"
        assert WorkerState.ONBOARDING.value == "onboarding"
        assert WorkerState.ACTIVE.value == "active"
        assert WorkerState.WORKING.value == "working"
        assert WorkerState.STUCK.value == "stuck"
        assert WorkerState.OFFBOARDING.value == "offboarding"
        assert WorkerState.TERMINATED.value == "terminated"

    def test_state_count(self) -> None:
        """Verify exactly 7 states are defined."""
        assert len(WorkerState) == 7


class TestValidTransitions:
    """Tests for the VALID_TRANSITIONS mapping."""

    def test_all_states_have_transitions_defined(self) -> None:
        """Every state should have an entry in VALID_TRANSITIONS."""
        for state in WorkerState:
            assert state in VALID_TRANSITIONS

    def test_pending_transitions(self) -> None:
        """PENDING can go to ONBOARDING or TERMINATED."""
        valid = VALID_TRANSITIONS[WorkerState.PENDING]
        assert WorkerState.ONBOARDING in valid
        assert WorkerState.TERMINATED in valid
        assert len(valid) == 2

    def test_onboarding_transitions(self) -> None:
        """ONBOARDING can go to ACTIVE or TERMINATED."""
        valid = VALID_TRANSITIONS[WorkerState.ONBOARDING]
        assert WorkerState.ACTIVE in valid
        assert WorkerState.TERMINATED in valid
        assert len(valid) == 2

    def test_active_transitions(self) -> None:
        """ACTIVE can go to WORKING, OFFBOARDING, or STUCK."""
        valid = VALID_TRANSITIONS[WorkerState.ACTIVE]
        assert WorkerState.WORKING in valid
        assert WorkerState.OFFBOARDING in valid
        assert WorkerState.STUCK in valid
        assert len(valid) == 3

    def test_working_transitions(self) -> None:
        """WORKING can go to ACTIVE, STUCK, or OFFBOARDING."""
        valid = VALID_TRANSITIONS[WorkerState.WORKING]
        assert WorkerState.ACTIVE in valid
        assert WorkerState.STUCK in valid
        assert WorkerState.OFFBOARDING in valid
        assert len(valid) == 3

    def test_stuck_transitions(self) -> None:
        """STUCK can go to ACTIVE or OFFBOARDING."""
        valid = VALID_TRANSITIONS[WorkerState.STUCK]
        assert WorkerState.ACTIVE in valid
        assert WorkerState.OFFBOARDING in valid
        assert len(valid) == 2

    def test_offboarding_transitions(self) -> None:
        """OFFBOARDING can only go to TERMINATED."""
        valid = VALID_TRANSITIONS[WorkerState.OFFBOARDING]
        assert WorkerState.TERMINATED in valid
        assert len(valid) == 1

    def test_terminated_no_transitions(self) -> None:
        """TERMINATED is final - no transitions allowed."""
        valid = VALID_TRANSITIONS[WorkerState.TERMINATED]
        assert len(valid) == 0


class TestCanTransition:
    """Tests for the can_transition() function."""

    def test_valid_transition_pending_to_onboarding(self) -> None:
        """can_transition returns True for valid PENDING -> ONBOARDING."""
        assert can_transition(WorkerState.PENDING, WorkerState.ONBOARDING) is True

    def test_valid_transition_pending_to_terminated(self) -> None:
        """can_transition returns True for valid PENDING -> TERMINATED."""
        assert can_transition(WorkerState.PENDING, WorkerState.TERMINATED) is True

    def test_valid_transition_onboarding_to_active(self) -> None:
        """can_transition returns True for valid ONBOARDING -> ACTIVE."""
        assert can_transition(WorkerState.ONBOARDING, WorkerState.ACTIVE) is True

    def test_valid_transition_active_to_working(self) -> None:
        """can_transition returns True for valid ACTIVE -> WORKING."""
        assert can_transition(WorkerState.ACTIVE, WorkerState.WORKING) is True

    def test_valid_transition_working_to_active(self) -> None:
        """can_transition returns True for valid WORKING -> ACTIVE."""
        assert can_transition(WorkerState.WORKING, WorkerState.ACTIVE) is True

    def test_valid_transition_active_to_stuck(self) -> None:
        """can_transition returns True for valid ACTIVE -> STUCK."""
        assert can_transition(WorkerState.ACTIVE, WorkerState.STUCK) is True

    def test_valid_transition_stuck_to_active(self) -> None:
        """can_transition returns True for valid STUCK -> ACTIVE."""
        assert can_transition(WorkerState.STUCK, WorkerState.ACTIVE) is True

    def test_valid_transition_active_to_offboarding(self) -> None:
        """can_transition returns True for valid ACTIVE -> OFFBOARDING."""
        assert can_transition(WorkerState.ACTIVE, WorkerState.OFFBOARDING) is True

    def test_valid_transition_offboarding_to_terminated(self) -> None:
        """can_transition returns True for valid OFFBOARDING -> TERMINATED."""
        assert can_transition(WorkerState.OFFBOARDING, WorkerState.TERMINATED) is True

    def test_invalid_transition_pending_to_active(self) -> None:
        """can_transition returns False for invalid PENDING -> ACTIVE."""
        assert can_transition(WorkerState.PENDING, WorkerState.ACTIVE) is False

    def test_invalid_transition_pending_to_working(self) -> None:
        """can_transition returns False for invalid PENDING -> WORKING."""
        assert can_transition(WorkerState.PENDING, WorkerState.WORKING) is False

    def test_invalid_transition_active_to_onboarding(self) -> None:
        """can_transition returns False for invalid ACTIVE -> ONBOARDING."""
        assert can_transition(WorkerState.ACTIVE, WorkerState.ONBOARDING) is False

    def test_invalid_transition_terminated_to_any(self) -> None:
        """can_transition returns False for any transition from TERMINATED."""
        for state in WorkerState:
            assert can_transition(WorkerState.TERMINATED, state) is False

    def test_invalid_transition_to_pending(self) -> None:
        """can_transition returns False for any transition TO PENDING."""
        for state in WorkerState:
            if state != WorkerState.PENDING:
                assert can_transition(state, WorkerState.PENDING) is False

    def test_invalid_transition_to_onboarding_from_non_pending(self) -> None:
        """can_transition returns False for ONBOARDING from non-PENDING."""
        non_pending_states = [s for s in WorkerState if s != WorkerState.PENDING]
        for state in non_pending_states:
            assert can_transition(state, WorkerState.ONBOARDING) is False


class TestTransitionFunction:
    """Tests for the transition() function."""

    def test_transition_returns_new_state_on_valid(self) -> None:
        """transition() returns the target state when valid."""
        result = transition(WorkerState.PENDING, WorkerState.ONBOARDING)
        assert result == WorkerState.ONBOARDING

    def test_transition_full_lifecycle(self) -> None:
        """Test a complete valid lifecycle through transition()."""
        state = WorkerState.PENDING

        state = transition(state, WorkerState.ONBOARDING)
        assert state == WorkerState.ONBOARDING

        state = transition(state, WorkerState.ACTIVE)
        assert state == WorkerState.ACTIVE

        state = transition(state, WorkerState.WORKING)
        assert state == WorkerState.WORKING

        state = transition(state, WorkerState.ACTIVE)
        assert state == WorkerState.ACTIVE

        state = transition(state, WorkerState.OFFBOARDING)
        assert state == WorkerState.OFFBOARDING

        state = transition(state, WorkerState.TERMINATED)
        assert state == WorkerState.TERMINATED

    def test_transition_raises_invalid_transition(self) -> None:
        """transition() raises InvalidTransition on invalid transition."""
        with pytest.raises(InvalidTransition):
            transition(WorkerState.PENDING, WorkerState.ACTIVE)

    def test_transition_raises_with_correct_states(self) -> None:
        """InvalidTransition contains the correct from/to states."""
        with pytest.raises(InvalidTransition) as exc_info:
            transition(WorkerState.PENDING, WorkerState.WORKING)

        assert exc_info.value.from_state == WorkerState.PENDING
        assert exc_info.value.to_state == WorkerState.WORKING

    def test_transition_exception_message(self) -> None:
        """InvalidTransition has a descriptive error message."""
        with pytest.raises(InvalidTransition) as exc_info:
            transition(WorkerState.TERMINATED, WorkerState.ACTIVE)

        message = str(exc_info.value)
        assert "terminated" in message
        assert "active" in message
        assert "Invalid transition" in message


class TestInvalidTransitionException:
    """Tests for the InvalidTransition exception class."""

    def test_exception_attributes(self) -> None:
        """InvalidTransition stores from_state and to_state."""
        exc = InvalidTransition(WorkerState.PENDING, WorkerState.ACTIVE)
        assert exc.from_state == WorkerState.PENDING
        assert exc.to_state == WorkerState.ACTIVE

    def test_exception_message_format(self) -> None:
        """InvalidTransition message includes state values."""
        exc = InvalidTransition(WorkerState.ACTIVE, WorkerState.PENDING)
        message = str(exc)
        assert "active" in message
        assert "pending" in message

    def test_exception_is_exception_subclass(self) -> None:
        """InvalidTransition is a proper Exception subclass."""
        exc = InvalidTransition(WorkerState.PENDING, WorkerState.ACTIVE)
        assert isinstance(exc, Exception)
