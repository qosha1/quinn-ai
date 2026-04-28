"""Unit tests for reachability helpers — pure graph functions."""
from shared.testing.state_machines import (
    can_reach,
    reachable_states,
    states_reaching,
    terminal_states,
)


GRAPH = {
    "a": ["b"],
    "b": ["c", "d"],
    "c": ["e"],
    "d": [],   # terminal
    "e": [],   # terminal
    "ghost": ["b"],  # not reachable from a
}


class TestReachableStates:
    def test_forward_bfs_from_initial(self):
        assert reachable_states(GRAPH, "a") == {"a", "b", "c", "d", "e"}

    def test_isolated_node_returns_only_itself(self):
        assert reachable_states({"x": []}, "x") == {"x"}

    def test_initial_in_unknown_node_raises(self):
        import pytest
        with pytest.raises(ValueError):
            reachable_states(GRAPH, "nonexistent")


class TestStatesReaching:
    def test_backward_bfs_to_target(self):
        # Anyone who can eventually reach 'e'
        assert states_reaching(GRAPH, "e") == {"a", "b", "c", "e", "ghost"}

    def test_terminal_only_reaches_self(self):
        assert states_reaching(GRAPH, "d") == {"a", "b", "d", "ghost"}


class TestCanReach:
    def test_direct_edge(self):
        assert can_reach(GRAPH, "a", "b") is True

    def test_transitive(self):
        assert can_reach(GRAPH, "a", "e") is True

    def test_not_reachable(self):
        assert can_reach(GRAPH, "d", "e") is False  # d is terminal

    def test_from_orphan(self):
        # 'ghost' can reach b/c/d/e
        assert can_reach(GRAPH, "ghost", "e") is True


class TestTerminalStates:
    def test_finds_all_terminals(self):
        assert terminal_states(GRAPH) == {"d", "e"}

    def test_no_terminals_returns_empty(self):
        cycle = {"a": ["b"], "b": ["a"]}
        assert terminal_states(cycle) == set()
