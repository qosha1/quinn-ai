"""Run every YAML spec in tests/scenarios/specs/ via the harness."""
from pathlib import Path

import pytest

from shared.testing.scenarios import ScenarioHarness, ScenarioSpec


def test_scenario(scenario_path: Path):
    spec = ScenarioSpec.from_yaml(scenario_path)
    with ScenarioHarness(spec) as run:
        for op in spec.ops:
            run.run_op(op)

        violations = []
        for assertion in spec.assertions:
            msg = run.check(assertion)
            if msg is not None:
                violations.append(msg)

        assert not violations, (
            f"Scenario {spec.name!r} produced violations:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
