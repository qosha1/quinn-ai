"""Unit tests for TransitionDriver — pure state-graph walker."""
import pytest

from shared.testing.state_machines import InvalidTransition, TransitionDriver


# A 3-state synthetic graph that does NOT depend on any QuinnAI specifics.
TRAFFIC = {
    "red": ["green"],
    "green": ["yellow"],
    "yellow": ["red"],
}


class TestTransitionDriver:
    def test_initial_state_is_set(self):
        d = TransitionDriver(TRAFFIC, initial="red")
        assert d.state == "red"

    def test_apply_valid_changes_state(self):
        d = TransitionDriver(TRAFFIC, initial="red")
        d.apply("green")
        assert d.state == "green"

    def test_apply_invalid_raises(self):
        d = TransitionDriver(TRAFFIC, initial="red")
        with pytest.raises(InvalidTransition) as exc:
            d.apply("yellow")  # red -> yellow not allowed
        assert "red" in str(exc.value)
        assert "yellow" in str(exc.value)

    def test_apply_unknown_state_raises(self):
        d = TransitionDriver(TRAFFIC, initial="red")
        with pytest.raises(InvalidTransition):
            d.apply("blue")  # not in graph at all

    def test_can_transition_matches_table(self):
        d = TransitionDriver(TRAFFIC, initial="red")
        assert d.can_transition("green") is True
        assert d.can_transition("yellow") is False

    def test_terminal_state_has_no_outgoing(self):
        terminal_graph = {"start": ["end"], "end": []}
        d = TransitionDriver(terminal_graph, initial="end")
        assert d.can_transition("start") is False
        with pytest.raises(InvalidTransition):
            d.apply("start")

    def test_unknown_initial_state_rejected(self):
        with pytest.raises(ValueError):
            TransitionDriver(TRAFFIC, initial="purple")

    def test_state_is_read_only(self):
        d = TransitionDriver(TRAFFIC, initial="red")
        with pytest.raises(AttributeError):
            d.state = "green"  # should be a property without setter

    def test_transitions_view_is_read_only(self):
        d = TransitionDriver(TRAFFIC, initial="red")
        with pytest.raises((AttributeError, TypeError)):
            d.transitions["red"] = ["yellow"]  # should not mutate the original
