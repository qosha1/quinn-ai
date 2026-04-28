"""Unit tests for SequenceRunner — runs ordered (machine, target) steps across drivers."""
import pytest

from shared.testing.state_machines import (
    Step,
    StepResult,
    TransitionDriver,
    run_sequence,
)


TRAFFIC = {"red": ["green"], "green": ["yellow"], "yellow": ["red"]}
ENGINE = {"off": ["on"], "on": ["off"]}


def _drivers():
    return {
        "light": TransitionDriver(TRAFFIC, initial="red"),
        "engine": TransitionDriver(ENGINE, initial="off"),
    }


class TestRunSequence:
    def test_empty_sequence_returns_empty_results(self):
        assert run_sequence(_drivers(), []) == []

    def test_single_valid_step(self):
        drivers = _drivers()
        results = run_sequence(drivers, [Step("light", "green")])
        assert len(results) == 1
        r = results[0]
        assert r.ok is True
        assert r.from_state == "red"
        assert r.to_state == "green"
        assert r.error is None
        assert drivers["light"].state == "green"

    def test_multistep_sequence_threads_state(self):
        drivers = _drivers()
        steps = [
            Step("light", "green"),
            Step("light", "yellow"),
            Step("engine", "on"),
        ]
        results = run_sequence(drivers, steps)
        assert all(r.ok for r in results)
        assert drivers["light"].state == "yellow"
        assert drivers["engine"].state == "on"

    def test_invalid_step_halts_by_default(self):
        drivers = _drivers()
        steps = [
            Step("light", "green"),
            Step("light", "red"),  # green -> red not allowed; halts here
            Step("engine", "on"),  # should NOT execute
        ]
        results = run_sequence(drivers, steps)
        assert len(results) == 2
        assert results[0].ok is True
        assert results[1].ok is False
        assert drivers["engine"].state == "off"  # not advanced

    def test_invalid_step_continues_when_halt_false(self):
        drivers = _drivers()
        steps = [
            Step("light", "red"),  # invalid from red->red
            Step("engine", "on"),  # still runs
        ]
        results = run_sequence(drivers, steps, halt=False)
        assert len(results) == 2
        assert results[0].ok is False
        assert results[1].ok is True
        assert drivers["engine"].state == "on"

    def test_unknown_machine_is_a_failure_not_a_crash(self):
        drivers = _drivers()
        results = run_sequence(drivers, [Step("ghost", "anywhere")])
        assert len(results) == 1
        assert results[0].ok is False
        assert "ghost" in results[0].error

    def test_step_result_is_immutable(self):
        drivers = _drivers()
        result = run_sequence(drivers, [Step("light", "green")])[0]
        with pytest.raises((AttributeError, TypeError)):
            result.ok = False

    def test_step_is_immutable(self):
        s = Step("light", "green")
        with pytest.raises((AttributeError, TypeError)):
            s.machine = "engine"
