"""Unit tests for InvariantChecker and built-in invariants."""
import pytest

from shared.testing.state_machines import (
    TransitionDriver,
    all_states_reachable_from,
    check,
    cross_machine_invariant,
    no_orphan_terminal_paths,
)


CLEAN = {
    "pending": ["onboarding", "terminated"],
    "onboarding": ["active", "terminated"],
    "active": ["terminated"],
    "terminated": [],
}

ORPHAN = {
    "pending": ["active"],
    "active": [],  # ok, terminal
    "ghost": [],  # unreachable from initial
}

NO_TERMINAL = {
    # every state has out-edges; no terminal state exists
    "a": ["b"],
    "b": ["a"],
}


class TestAllStatesReachable:
    def test_clean_graph_passes(self):
        d = TransitionDriver(CLEAN, initial="pending")
        violations = check({"worker": d}, [all_states_reachable_from("pending")])
        assert violations == []

    def test_orphan_state_detected(self):
        d = TransitionDriver(ORPHAN, initial="pending")
        violations = check({"worker": d}, [all_states_reachable_from("pending")])
        assert len(violations) == 1
        assert "ghost" in violations[0]


class TestNoOrphanTerminalPaths:
    def test_clean_graph_passes(self):
        d = TransitionDriver(CLEAN, initial="pending")
        violations = check({"worker": d}, [no_orphan_terminal_paths()])
        assert violations == []

    def test_no_terminal_state_flagged(self):
        d = TransitionDriver(NO_TERMINAL, initial="a")
        violations = check({"worker": d}, [no_orphan_terminal_paths()])
        assert len(violations) >= 1


class TestCrossMachineInvariant:
    def test_passes_when_predicate_true(self):
        light = TransitionDriver({"red": ["green"], "green": ["red"]}, initial="red")
        engine = TransitionDriver({"off": ["on"], "on": ["off"]}, initial="off")

        # Rule: engine can only be on if light is green.
        rule = cross_machine_invariant(
            name="engine_runs_only_on_green",
            predicate=lambda d: not (d["engine"].state == "on" and d["light"].state != "green"),
            message="engine on while light not green",
        )

        violations = check({"light": light, "engine": engine}, [rule])
        assert violations == []

    def test_fails_when_predicate_false(self):
        light = TransitionDriver({"red": ["green"], "green": ["red"]}, initial="red")
        engine = TransitionDriver({"off": ["on"], "on": ["off"]}, initial="off")
        engine.apply("on")  # red light + engine on = violation

        rule = cross_machine_invariant(
            name="engine_runs_only_on_green",
            predicate=lambda d: not (d["engine"].state == "on" and d["light"].state != "green"),
            message="engine on while light not green",
        )

        violations = check({"light": light, "engine": engine}, [rule])
        assert len(violations) == 1
        assert "engine" in violations[0].lower()


class TestCheckCollects:
    def test_returns_all_violations_not_just_first(self):
        d = TransitionDriver(ORPHAN, initial="pending")
        violations = check(
            {"worker": d},
            [
                all_states_reachable_from("pending"),
                # invent a deliberately-failing one
                cross_machine_invariant(
                    "always_fails", predicate=lambda d: False, message="forced failure"
                ),
            ],
        )
        assert len(violations) == 2

    def test_zero_invariants_returns_empty(self):
        d = TransitionDriver(CLEAN, initial="pending")
        assert check({"worker": d}, []) == []
