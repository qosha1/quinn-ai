"""ScenarioSpec parses + validates the optional `scoring` block and per-assertion
weight/critical keys. Pure YAML parsing — $0, no LLM, no harness.
"""
import pytest

from shared.testing.scenarios import ScenarioSpec
from shared.testing.canary.scoring import ScoringPolicy


def _write(tmp_path, body):
    p = tmp_path / "spec.yml"
    p.write_text(body)
    return p


def test_spec_without_scoring_block_resolves_strict(tmp_path):
    p = _write(tmp_path, """
name: no_scoring
setup: {init: {ceo_name: Alice}}
ops: []
assertions:
  - { kind: org_status, value: initialized }
""")
    spec = ScenarioSpec.from_yaml(p)
    assert spec.scoring is None
    policy = ScoringPolicy.from_spec(spec.scoring)
    assert policy.pass_threshold == 1.0
    assert policy.samples == 1


def test_spec_with_scoring_block_parsed(tmp_path):
    p = _write(tmp_path, """
name: scored
setup: {init: {ceo_name: Alice}}
ops: []
scoring:
  samples: 3
  pass_threshold: 0.9
  consistency_threshold: 0.66
assertions:
  - { kind: org_status, value: initialized, weight: 2, critical: true }
  - { kind: worker_count, value: 1, weight: 1 }
""")
    spec = ScenarioSpec.from_yaml(p)
    assert spec.scoring == {
        "samples": 3,
        "pass_threshold": 0.9,
        "consistency_threshold": 0.66,
    }
    # per-assertion weight/critical survive into the assertion dicts
    assert spec.assertions[0]["weight"] == 2
    assert spec.assertions[0]["critical"] is True
    policy = ScoringPolicy.from_spec(spec.scoring)
    assert policy.samples == 3
    assert policy.consistency_threshold == 0.66


def test_spec_rejects_non_mapping_scoring(tmp_path):
    p = _write(tmp_path, """
name: bad_scoring
setup: {init: {ceo_name: Alice}}
ops: []
scoring: [1, 2, 3]
assertions: []
""")
    with pytest.raises(ValueError, match="scoring"):
        ScenarioSpec.from_yaml(p)


def test_spec_rejects_unknown_scoring_key(tmp_path):
    p = _write(tmp_path, """
name: bad_key
setup: {init: {ceo_name: Alice}}
ops: []
scoring: {sampels: 3}
assertions: []
""")
    with pytest.raises(ValueError, match="scoring"):
        ScenarioSpec.from_yaml(p)


def test_spec_rejects_out_of_range_threshold(tmp_path):
    p = _write(tmp_path, """
name: bad_range
setup: {init: {ceo_name: Alice}}
ops: []
scoring: {pass_threshold: 1.5}
assertions: []
""")
    with pytest.raises(ValueError):
        ScenarioSpec.from_yaml(p)


def test_spec_rejects_bad_assertion_weight(tmp_path):
    p = _write(tmp_path, """
name: bad_weight
setup: {init: {ceo_name: Alice}}
ops: []
assertions:
  - { kind: org_status, value: initialized, weight: -1 }
""")
    with pytest.raises(ValueError, match="weight"):
        ScenarioSpec.from_yaml(p)
