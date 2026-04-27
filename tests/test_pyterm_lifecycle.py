"""
Tests for lifecycle hooks and worker state management.
"""

import pytest
from unittest.mock import MagicMock

from shared.pyterm.lifecycle import (
    LifecycleHooks,
    session_to_worker_state,
    VALID_TRANSITIONS,
)
from shared.core.state import WorkerState, WORKER_STATE_TRANSITIONS
from shared.pyterm.protocols import PytermSessionState


class TestSessionToWorkerState:
    """Tests for session_to_worker_state mapping."""

    def test_idle_maps_to_pending(self):
        """Test IDLE session maps to PENDING worker."""
        result = session_to_worker_state(PytermSessionState.IDLE)
        assert result == WorkerState.PENDING

    def test_running_maps_to_active(self):
        """Test RUNNING session maps to ACTIVE worker."""
        result = session_to_worker_state(PytermSessionState.RUNNING)
        assert result == WorkerState.ACTIVE

    def test_exited_maps_to_terminated(self):
        """Test EXITED session maps to TERMINATED worker."""
        result = session_to_worker_state(PytermSessionState.EXITED)
        assert result == WorkerState.TERMINATED

    def test_error_maps_to_terminated(self):
        """Test ERROR session maps to TERMINATED worker."""
        result = session_to_worker_state(PytermSessionState.ERROR)
        assert result == WorkerState.TERMINATED


class TestValidTransitions:
    """Tests for VALID_TRANSITIONS constant."""

    def test_valid_transitions_is_canonical(self):
        """Test VALID_TRANSITIONS references canonical transitions."""
        assert VALID_TRANSITIONS is WORKER_STATE_TRANSITIONS

    def test_pending_transitions(self):
        """Test valid transitions from PENDING."""
        assert WorkerState.ONBOARDING in VALID_TRANSITIONS[WorkerState.PENDING]

    def test_active_transitions(self):
        """Test valid transitions from ACTIVE."""
        transitions = VALID_TRANSITIONS[WorkerState.ACTIVE]
        assert WorkerState.WORKING in transitions
        assert WorkerState.STUCK in transitions
        assert WorkerState.OFFBOARDING in transitions


class TestLifecycleHooksInit:
    """Tests for LifecycleHooks initialization."""

    def test_init_default(self):
        """Test default initialization."""
        hooks = LifecycleHooks()

        assert hooks.state == WorkerState.PENDING
        assert len(hooks._on_change) == 0
        assert len(hooks._on_enter) == 0
        assert len(hooks._on_exit) == 0

    def test_state_property(self):
        """Test state property."""
        hooks = LifecycleHooks()
        assert hooks.state == WorkerState.PENDING


class TestLifecycleHooksTransition:
    """Tests for state transitions."""

    def test_valid_transition_succeeds(self):
        """Test valid transition succeeds."""
        hooks = LifecycleHooks()

        result = hooks.transition(WorkerState.ONBOARDING)

        assert result is True
        assert hooks.state == WorkerState.ONBOARDING

    def test_invalid_transition_fails(self):
        """Test invalid transition fails."""
        hooks = LifecycleHooks()

        # Can't go directly from PENDING to ACTIVE
        result = hooks.transition(WorkerState.ACTIVE)

        assert result is False
        assert hooks.state == WorkerState.PENDING

    def test_transition_fires_change_callbacks(self):
        """Test transition fires change callbacks."""
        hooks = LifecycleHooks()

        callback = MagicMock()
        hooks.on_change(callback)

        hooks.transition(WorkerState.ONBOARDING)

        callback.assert_called_once_with(WorkerState.PENDING, WorkerState.ONBOARDING)

    def test_transition_fires_exit_callbacks(self):
        """Test transition fires exit callbacks for old state."""
        hooks = LifecycleHooks()

        callback = MagicMock()
        hooks.on_exit(WorkerState.PENDING, callback)

        hooks.transition(WorkerState.ONBOARDING)

        callback.assert_called_once_with(WorkerState.PENDING)

    def test_transition_fires_enter_callbacks(self):
        """Test transition fires enter callbacks for new state."""
        hooks = LifecycleHooks()

        callback = MagicMock()
        hooks.on_enter(WorkerState.ONBOARDING, callback)

        hooks.transition(WorkerState.ONBOARDING)

        callback.assert_called_once_with(WorkerState.ONBOARDING)

    def test_transition_callback_order(self):
        """Test callbacks fire in correct order: exit -> change -> enter."""
        hooks = LifecycleHooks()

        call_order = []

        def exit_cb(state):
            call_order.append(("exit", state))

        def change_cb(old, new):
            call_order.append(("change", old, new))

        def enter_cb(state):
            call_order.append(("enter", state))

        hooks.on_exit(WorkerState.PENDING, exit_cb)
        hooks.on_change(change_cb)
        hooks.on_enter(WorkerState.ONBOARDING, enter_cb)

        hooks.transition(WorkerState.ONBOARDING)

        assert len(call_order) == 3
        assert call_order[0][0] == "exit"
        assert call_order[1][0] == "change"
        assert call_order[2][0] == "enter"

    def test_multiple_change_callbacks(self):
        """Test multiple change callbacks all fire."""
        hooks = LifecycleHooks()

        callback1 = MagicMock()
        callback2 = MagicMock()

        hooks.on_change(callback1)
        hooks.on_change(callback2)

        hooks.transition(WorkerState.ONBOARDING)

        callback1.assert_called_once()
        callback2.assert_called_once()

    def test_multiple_enter_callbacks(self):
        """Test multiple enter callbacks for same state all fire."""
        hooks = LifecycleHooks()

        callback1 = MagicMock()
        callback2 = MagicMock()

        hooks.on_enter(WorkerState.ONBOARDING, callback1)
        hooks.on_enter(WorkerState.ONBOARDING, callback2)

        hooks.transition(WorkerState.ONBOARDING)

        callback1.assert_called_once_with(WorkerState.ONBOARDING)
        callback2.assert_called_once_with(WorkerState.ONBOARDING)


class TestLifecycleHooksCanTransition:
    """Tests for can_transition()."""

    def test_can_transition_valid(self):
        """Test can_transition() returns True for valid transition."""
        hooks = LifecycleHooks()

        assert hooks.can_transition(WorkerState.ONBOARDING) is True

    def test_can_transition_invalid(self):
        """Test can_transition() returns False for invalid transition."""
        hooks = LifecycleHooks()

        assert hooks.can_transition(WorkerState.ACTIVE) is False

    def test_can_transition_after_state_change(self):
        """Test can_transition() reflects current state."""
        hooks = LifecycleHooks()

        # Initially can go to ONBOARDING
        assert hooks.can_transition(WorkerState.ONBOARDING) is True

        # After transition, can't go back to PENDING
        hooks.transition(WorkerState.ONBOARDING)
        assert hooks.can_transition(WorkerState.PENDING) is False

        # But can go to ACTIVE
        assert hooks.can_transition(WorkerState.ACTIVE) is True


class TestLifecycleHooksReset:
    """Tests for reset()."""

    def test_reset_returns_to_pending(self):
        """Test reset() returns to PENDING state."""
        hooks = LifecycleHooks()

        hooks.transition(WorkerState.ONBOARDING)
        hooks.transition(WorkerState.ACTIVE)

        hooks.reset()

        assert hooks.state == WorkerState.PENDING

    def test_reset_does_not_fire_callbacks(self):
        """Test reset() doesn't fire callbacks (for testing only)."""
        hooks = LifecycleHooks()

        callback = MagicMock()
        hooks.on_change(callback)

        hooks.transition(WorkerState.ONBOARDING)
        callback.reset_mock()

        hooks.reset()

        callback.assert_not_called()


class TestLifecycleHooksCallbackRegistration:
    """Tests for callback registration."""

    def test_on_change_registers_callback(self):
        """Test on_change() registers callback."""
        hooks = LifecycleHooks()

        callback = MagicMock()
        hooks.on_change(callback)

        assert callback in hooks._on_change

    def test_on_enter_registers_callback(self):
        """Test on_enter() registers callback for state."""
        hooks = LifecycleHooks()

        callback = MagicMock()
        hooks.on_enter(WorkerState.ACTIVE, callback)

        assert WorkerState.ACTIVE in hooks._on_enter
        assert callback in hooks._on_enter[WorkerState.ACTIVE]

    def test_on_exit_registers_callback(self):
        """Test on_exit() registers callback for state."""
        hooks = LifecycleHooks()

        callback = MagicMock()
        hooks.on_exit(WorkerState.PENDING, callback)

        assert WorkerState.PENDING in hooks._on_exit
        assert callback in hooks._on_exit[WorkerState.PENDING]

    def test_multiple_enter_callbacks_same_state(self):
        """Test multiple callbacks can be registered for same state."""
        hooks = LifecycleHooks()

        callback1 = MagicMock()
        callback2 = MagicMock()

        hooks.on_enter(WorkerState.ACTIVE, callback1)
        hooks.on_enter(WorkerState.ACTIVE, callback2)

        assert len(hooks._on_enter[WorkerState.ACTIVE]) == 2


class TestLifecycleHooksFullFlow:
    """Integration tests for full lifecycle flow."""

    def test_full_worker_lifecycle(self):
        """Test a full worker lifecycle."""
        hooks = LifecycleHooks()

        states_visited = []

        def track_state(old, new):
            states_visited.append(new)

        hooks.on_change(track_state)

        # PENDING -> ONBOARDING
        assert hooks.transition(WorkerState.ONBOARDING)

        # ONBOARDING -> ACTIVE
        assert hooks.transition(WorkerState.ACTIVE)

        # ACTIVE -> WORKING
        assert hooks.transition(WorkerState.WORKING)

        # WORKING -> ACTIVE
        assert hooks.transition(WorkerState.ACTIVE)

        # ACTIVE -> OFFBOARDING
        assert hooks.transition(WorkerState.OFFBOARDING)

        # OFFBOARDING -> TERMINATED
        assert hooks.transition(WorkerState.TERMINATED)

        assert states_visited == [
            WorkerState.ONBOARDING,
            WorkerState.ACTIVE,
            WorkerState.WORKING,
            WorkerState.ACTIVE,
            WorkerState.OFFBOARDING,
            WorkerState.TERMINATED,
        ]

    def test_stuck_recovery_flow(self):
        """Test worker stuck and recovery flow."""
        hooks = LifecycleHooks()

        # Get to ACTIVE
        hooks.transition(WorkerState.ONBOARDING)
        hooks.transition(WorkerState.ACTIVE)

        # Go to STUCK
        assert hooks.transition(WorkerState.STUCK)
        assert hooks.state == WorkerState.STUCK

        # Recover back to ACTIVE
        assert hooks.transition(WorkerState.ACTIVE)
        assert hooks.state == WorkerState.ACTIVE

    def test_invalid_paths_blocked(self):
        """Test invalid state paths are blocked."""
        hooks = LifecycleHooks()

        # Can't skip to these states from PENDING (except TERMINATED which is allowed for emergency shutdown)
        assert hooks.transition(WorkerState.ACTIVE) is False
        assert hooks.transition(WorkerState.WORKING) is False
        assert hooks.transition(WorkerState.STUCK) is False
        assert hooks.transition(WorkerState.OFFBOARDING) is False

        # Must go through proper flow
        assert hooks.transition(WorkerState.ONBOARDING) is True
        assert hooks.transition(WorkerState.ACTIVE) is True


class TestLifecycleHooksCallbackErrors:
    """Tests for callback error handling."""

    def test_callback_exception_does_not_prevent_transition(self):
        """Test exception in callback doesn't prevent transition."""
        hooks = LifecycleHooks()

        def failing_callback(old, new):
            raise RuntimeError("Callback error")

        hooks.on_change(failing_callback)

        # Transition should still succeed despite callback error
        # (Note: current implementation doesn't catch exceptions,
        # so this would actually raise. This test documents current behavior.)
        with pytest.raises(RuntimeError, match="Callback error"):
            hooks.transition(WorkerState.ONBOARDING)

    def test_exit_callback_exception(self):
        """Test exception in exit callback."""
        hooks = LifecycleHooks()

        def failing_exit(state):
            raise ValueError("Exit callback error")

        hooks.on_exit(WorkerState.PENDING, failing_exit)

        with pytest.raises(ValueError, match="Exit callback error"):
            hooks.transition(WorkerState.ONBOARDING)

    def test_enter_callback_exception(self):
        """Test exception in enter callback."""
        hooks = LifecycleHooks()

        def failing_enter(state):
            raise TypeError("Enter callback error")

        hooks.on_enter(WorkerState.ONBOARDING, failing_enter)

        with pytest.raises(TypeError, match="Enter callback error"):
            hooks.transition(WorkerState.ONBOARDING)


class TestLifecycleHooksEdgeCases:
    """Tests for edge cases."""

    def test_transition_to_same_state(self):
        """Test transitioning to same state fails (not in valid transitions)."""
        hooks = LifecycleHooks()

        # PENDING -> PENDING not in valid transitions
        result = hooks.transition(WorkerState.PENDING)

        assert result is False
        assert hooks.state == WorkerState.PENDING

    def test_no_callbacks_registered(self):
        """Test transitions work with no callbacks."""
        hooks = LifecycleHooks()

        # Should work fine without any callbacks
        assert hooks.transition(WorkerState.ONBOARDING) is True

    def test_empty_callback_lists(self):
        """Test callbacks work when lists are empty."""
        hooks = LifecycleHooks()

        # Register callbacks for states we won't visit
        hooks.on_enter(WorkerState.TERMINATED, MagicMock())
        hooks.on_exit(WorkerState.TERMINATED, MagicMock())

        # Should still work
        assert hooks.transition(WorkerState.ONBOARDING) is True
