"""Op + predicate registries — ensure they're extensible without harness changes."""
import pytest

from shared.testing.scenarios import OPS, PREDICATES, ScenarioHarness, ScenarioSpec


def test_ops_is_a_dict_of_callables():
    assert isinstance(OPS, dict)
    for name, fn in OPS.items():
        assert callable(fn), f"{name} is not callable"


def test_predicates_is_a_dict_of_callables():
    assert isinstance(PREDICATES, dict)
    for name, fn in PREDICATES.items():
        assert callable(fn), f"{name} is not callable"


def test_known_ops_present():
    """The minimum op set required by the v1 scenarios."""
    expected = {"init", "hire", "fire", "transition_lifecycle"}
    missing = expected - set(OPS.keys())
    assert not missing, f"missing ops: {missing}"


def test_known_predicates_present():
    """The minimum assertion set required by the v1 scenarios."""
    expected = {"org_status", "worker_count", "worker_lifecycle_is", "manager_subordinates"}
    missing = expected - set(PREDICATES.keys())
    assert not missing, f"missing predicates: {missing}"


def test_run_op_dispatches(monkeypatch):
    """Adding a new op = registering a function. No harness change needed."""
    called: list[dict] = []

    OPS["__test_marker_op__"] = lambda run, op: called.append(op)
    try:
        spec = ScenarioSpec(
            name="t",
            setup={"init": {}},
            ops=[{"op": "__test_marker_op__", "x": 1}],
            assertions=[],
            _allow_unknown_kinds=True,  # validation bypass for this test
        )
        with ScenarioHarness(spec) as run:
            run.run_op({"op": "__test_marker_op__", "x": 1})
        assert called == [{"op": "__test_marker_op__", "x": 1}]
    finally:
        OPS.pop("__test_marker_op__", None)


def test_unknown_op_at_runtime_raises():
    """Even if validation is bypassed, runtime dispatch must reject unknown ops cleanly."""
    spec = ScenarioSpec(
        name="t",
        setup={"init": {}},
        ops=[],
        assertions=[],
    )
    with ScenarioHarness(spec) as run:
        with pytest.raises(KeyError, match="unknown op"):
            run.run_op({"op": "no_such_op"})
