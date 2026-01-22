"""Tests for the work item (bead) state machine.

Tests the WorkState enum, state transitions, and helper functions.
"""

import pytest

from shared.core import (
    WORK_STATE_TRANSITIONS,
    InvalidStateTransition,
    WorkState,
    can_transition_work,
    is_work_active,
    is_work_terminal,
    transition_work,
)


class TestWorkState:
    """Tests for WorkState enum values."""

    def test_all_states_exist(self) -> None:
        """Verify all expected states are defined."""
        expected_states = [
            "DRAFT",
            "OPEN",
            "IN_PROGRESS",
            "REVIEW",
            "BLOCKED",
            "CLOSED",
            "CANCELLED",
        ]
        for state_name in expected_states:
            assert hasattr(WorkState, state_name)

    def test_state_values(self) -> None:
        """Verify state values are lowercase string versions."""
        assert WorkState.DRAFT.value == "draft"
        assert WorkState.OPEN.value == "open"
        assert WorkState.IN_PROGRESS.value == "in_progress"
        assert WorkState.REVIEW.value == "review"
        assert WorkState.BLOCKED.value == "blocked"
        assert WorkState.CLOSED.value == "closed"
        assert WorkState.CANCELLED.value == "cancelled"

    def test_state_count(self) -> None:
        """Verify exactly 7 states are defined."""
        assert len(WorkState) == 7


class TestWorkStateTransitions:
    """Tests for the WORK_STATE_TRANSITIONS mapping."""

    def test_all_states_have_transitions_defined(self) -> None:
        """Every state should have an entry in WORK_STATE_TRANSITIONS."""
        for state in WorkState:
            assert state in WORK_STATE_TRANSITIONS

    def test_draft_transitions(self) -> None:
        """DRAFT can go to OPEN or CANCELLED."""
        valid = WORK_STATE_TRANSITIONS[WorkState.DRAFT]
        assert WorkState.OPEN in valid
        assert WorkState.CANCELLED in valid
        assert len(valid) == 2

    def test_open_transitions(self) -> None:
        """OPEN can go to IN_PROGRESS, BLOCKED, or CANCELLED."""
        valid = WORK_STATE_TRANSITIONS[WorkState.OPEN]
        assert WorkState.IN_PROGRESS in valid
        assert WorkState.BLOCKED in valid
        assert WorkState.CANCELLED in valid
        assert len(valid) == 3

    def test_in_progress_transitions(self) -> None:
        """IN_PROGRESS can go to REVIEW, BLOCKED, OPEN, or CANCELLED."""
        valid = WORK_STATE_TRANSITIONS[WorkState.IN_PROGRESS]
        assert WorkState.REVIEW in valid
        assert WorkState.BLOCKED in valid
        assert WorkState.OPEN in valid
        assert WorkState.CANCELLED in valid
        assert len(valid) == 4

    def test_review_transitions(self) -> None:
        """REVIEW can go to CLOSED, IN_PROGRESS, or CANCELLED."""
        valid = WORK_STATE_TRANSITIONS[WorkState.REVIEW]
        assert WorkState.CLOSED in valid
        assert WorkState.IN_PROGRESS in valid
        assert WorkState.CANCELLED in valid
        assert len(valid) == 3

    def test_blocked_transitions(self) -> None:
        """BLOCKED can go to OPEN, IN_PROGRESS, or CANCELLED."""
        valid = WORK_STATE_TRANSITIONS[WorkState.BLOCKED]
        assert WorkState.OPEN in valid
        assert WorkState.IN_PROGRESS in valid
        assert WorkState.CANCELLED in valid
        assert len(valid) == 3

    def test_closed_no_transitions(self) -> None:
        """CLOSED is final - no transitions allowed."""
        valid = WORK_STATE_TRANSITIONS[WorkState.CLOSED]
        assert len(valid) == 0

    def test_cancelled_no_transitions(self) -> None:
        """CANCELLED is final - no transitions allowed."""
        valid = WORK_STATE_TRANSITIONS[WorkState.CANCELLED]
        assert len(valid) == 0


class TestCanTransitionWork:
    """Tests for the can_transition_work() function."""

    def test_valid_transition_draft_to_open(self) -> None:
        """can_transition_work returns True for valid DRAFT -> OPEN."""
        assert can_transition_work(WorkState.DRAFT, WorkState.OPEN) is True

    def test_valid_transition_draft_to_cancelled(self) -> None:
        """can_transition_work returns True for valid DRAFT -> CANCELLED."""
        assert can_transition_work(WorkState.DRAFT, WorkState.CANCELLED) is True

    def test_valid_transition_open_to_in_progress(self) -> None:
        """can_transition_work returns True for valid OPEN -> IN_PROGRESS."""
        assert can_transition_work(WorkState.OPEN, WorkState.IN_PROGRESS) is True

    def test_valid_transition_in_progress_to_review(self) -> None:
        """can_transition_work returns True for valid IN_PROGRESS -> REVIEW."""
        assert can_transition_work(WorkState.IN_PROGRESS, WorkState.REVIEW) is True

    def test_valid_transition_review_to_closed(self) -> None:
        """can_transition_work returns True for valid REVIEW -> CLOSED."""
        assert can_transition_work(WorkState.REVIEW, WorkState.CLOSED) is True

    def test_valid_transition_in_progress_to_blocked(self) -> None:
        """can_transition_work returns True for valid IN_PROGRESS -> BLOCKED."""
        assert can_transition_work(WorkState.IN_PROGRESS, WorkState.BLOCKED) is True

    def test_valid_transition_blocked_to_in_progress(self) -> None:
        """can_transition_work returns True for valid BLOCKED -> IN_PROGRESS."""
        assert can_transition_work(WorkState.BLOCKED, WorkState.IN_PROGRESS) is True

    def test_valid_transition_review_to_in_progress(self) -> None:
        """can_transition_work returns True for valid REVIEW -> IN_PROGRESS (needs more work)."""
        assert can_transition_work(WorkState.REVIEW, WorkState.IN_PROGRESS) is True

    def test_valid_transition_in_progress_to_open(self) -> None:
        """can_transition_work returns True for valid IN_PROGRESS -> OPEN (return to queue)."""
        assert can_transition_work(WorkState.IN_PROGRESS, WorkState.OPEN) is True

    def test_invalid_transition_draft_to_in_progress(self) -> None:
        """can_transition_work returns False for invalid DRAFT -> IN_PROGRESS."""
        assert can_transition_work(WorkState.DRAFT, WorkState.IN_PROGRESS) is False

    def test_invalid_transition_draft_to_review(self) -> None:
        """can_transition_work returns False for invalid DRAFT -> REVIEW."""
        assert can_transition_work(WorkState.DRAFT, WorkState.REVIEW) is False

    def test_invalid_transition_draft_to_closed(self) -> None:
        """can_transition_work returns False for invalid DRAFT -> CLOSED."""
        assert can_transition_work(WorkState.DRAFT, WorkState.CLOSED) is False

    def test_invalid_transition_open_to_review(self) -> None:
        """can_transition_work returns False for invalid OPEN -> REVIEW."""
        assert can_transition_work(WorkState.OPEN, WorkState.REVIEW) is False

    def test_invalid_transition_closed_to_any(self) -> None:
        """can_transition_work returns False for any transition from CLOSED."""
        for state in WorkState:
            assert can_transition_work(WorkState.CLOSED, state) is False

    def test_invalid_transition_cancelled_to_any(self) -> None:
        """can_transition_work returns False for any transition from CANCELLED."""
        for state in WorkState:
            assert can_transition_work(WorkState.CANCELLED, state) is False

    def test_invalid_transition_to_draft(self) -> None:
        """can_transition_work returns False for any transition TO DRAFT."""
        for state in WorkState:
            if state != WorkState.DRAFT:
                assert can_transition_work(state, WorkState.DRAFT) is False


class TestTransitionWorkFunction:
    """Tests for the transition_work() function."""

    def test_transition_returns_new_state_on_valid(self) -> None:
        """transition_work() returns the target state when valid."""
        result = transition_work(WorkState.DRAFT, WorkState.OPEN)
        assert result == WorkState.OPEN

    def test_transition_full_lifecycle(self) -> None:
        """Test a complete valid lifecycle through transition_work()."""
        state = WorkState.DRAFT

        state = transition_work(state, WorkState.OPEN)
        assert state == WorkState.OPEN

        state = transition_work(state, WorkState.IN_PROGRESS)
        assert state == WorkState.IN_PROGRESS

        state = transition_work(state, WorkState.REVIEW)
        assert state == WorkState.REVIEW

        state = transition_work(state, WorkState.CLOSED)
        assert state == WorkState.CLOSED

    def test_transition_lifecycle_with_block(self) -> None:
        """Test lifecycle with blocking and unblocking."""
        state = WorkState.DRAFT

        state = transition_work(state, WorkState.OPEN)
        state = transition_work(state, WorkState.IN_PROGRESS)
        state = transition_work(state, WorkState.BLOCKED)
        assert state == WorkState.BLOCKED

        # Unblock and continue
        state = transition_work(state, WorkState.IN_PROGRESS)
        state = transition_work(state, WorkState.REVIEW)
        state = transition_work(state, WorkState.CLOSED)
        assert state == WorkState.CLOSED

    def test_transition_lifecycle_with_review_rejection(self) -> None:
        """Test lifecycle where review sends work back for more work."""
        state = WorkState.DRAFT

        state = transition_work(state, WorkState.OPEN)
        state = transition_work(state, WorkState.IN_PROGRESS)
        state = transition_work(state, WorkState.REVIEW)

        # Review rejects, needs more work
        state = transition_work(state, WorkState.IN_PROGRESS)
        assert state == WorkState.IN_PROGRESS

        # Complete again
        state = transition_work(state, WorkState.REVIEW)
        state = transition_work(state, WorkState.CLOSED)
        assert state == WorkState.CLOSED

    def test_transition_raises_invalid_state_transition(self) -> None:
        """transition_work() raises InvalidStateTransition on invalid transition."""
        with pytest.raises(InvalidStateTransition):
            transition_work(WorkState.DRAFT, WorkState.CLOSED)

    def test_transition_raises_with_correct_states(self) -> None:
        """InvalidStateTransition contains the correct from/to states."""
        with pytest.raises(InvalidStateTransition) as exc_info:
            transition_work(WorkState.DRAFT, WorkState.REVIEW)

        assert exc_info.value.from_state == WorkState.DRAFT
        assert exc_info.value.to_state == WorkState.REVIEW

    def test_transition_exception_message(self) -> None:
        """InvalidStateTransition has a descriptive error message."""
        with pytest.raises(InvalidStateTransition) as exc_info:
            transition_work(WorkState.CLOSED, WorkState.OPEN)

        message = str(exc_info.value)
        assert "closed" in message
        assert "open" in message
        assert "Invalid transition" in message


class TestWorkStateHelpers:
    """Tests for work state helper functions."""

    def test_is_work_terminal_closed(self) -> None:
        """is_work_terminal returns True for CLOSED."""
        assert is_work_terminal(WorkState.CLOSED) is True

    def test_is_work_terminal_cancelled(self) -> None:
        """is_work_terminal returns True for CANCELLED."""
        assert is_work_terminal(WorkState.CANCELLED) is True

    def test_is_work_terminal_non_terminal_states(self) -> None:
        """is_work_terminal returns False for non-terminal states."""
        non_terminal = [
            WorkState.DRAFT,
            WorkState.OPEN,
            WorkState.IN_PROGRESS,
            WorkState.REVIEW,
            WorkState.BLOCKED,
        ]
        for state in non_terminal:
            assert is_work_terminal(state) is False

    def test_is_work_active_in_progress(self) -> None:
        """is_work_active returns True for IN_PROGRESS."""
        assert is_work_active(WorkState.IN_PROGRESS) is True

    def test_is_work_active_review(self) -> None:
        """is_work_active returns True for REVIEW."""
        assert is_work_active(WorkState.REVIEW) is True

    def test_is_work_active_non_active_states(self) -> None:
        """is_work_active returns False for non-active states."""
        non_active = [
            WorkState.DRAFT,
            WorkState.OPEN,
            WorkState.BLOCKED,
            WorkState.CLOSED,
            WorkState.CANCELLED,
        ]
        for state in non_active:
            assert is_work_active(state) is False
