"""run_canary honours the scoring policy — multi-sample + weighted threshold
gating — proven WITHOUT a live LLM.

These specs use `setup.init` with ops:[] so the only work each sample does is a
deterministic `qn org init` (no start_org => no session spawn => $0). That lets
us exercise the full sample-loop + scoring + verdict pipeline for real.
"""
import pytest

from shared.testing.canary import ProviderConfig, run_canary
from shared.testing.scenarios import ScenarioSpec


def _config():
    return ProviderConfig(
        provider="claude_code",
        model="claude-sonnet-4-5",
        api_key_env="ANTHROPIC_API_KEY",
        budget_usd=0.50,
        budget_seconds=300,
    )


def _spec(tmp_path, body):
    p = tmp_path / "spec.yml"
    p.write_text(body)
    return ScenarioSpec.from_yaml(p)


def test_multi_sample_all_pass(tmp_path):
    spec = _spec(tmp_path, """
name: scored_pass
setup: {init: {ceo_name: Alice}}
ops: []
scoring: {samples: 2, pass_threshold: 0.9, consistency_threshold: 0.9}
assertions:
  - { kind: org_status, value: initialized }
  - { kind: worker_count, value: 1 }
""")
    result = run_canary(spec, _config())
    assert result.ok is True
    assert result.samples == 2
    assert result.pass_rate == pytest.approx(1.0)
    assert result.mean_score == pytest.approx(1.0)
    assert result.verdict is not None
    assert result.verdict.runs_passed == 2


def test_below_correctness_bar_fails_with_scoring_violation(tmp_path):
    """A wrong assertion every run => pass_rate 0 => canary fails, and the
    violation message is about correctness, not a budget kill."""
    spec = _spec(tmp_path, """
name: scored_fail
setup: {init: {ceo_name: Alice}}
ops: []
scoring: {samples: 2, pass_threshold: 0.9, consistency_threshold: 0.9}
assertions:
  - { kind: org_status, value: initialized }
  - { kind: worker_count, value: 9 }
""")
    result = run_canary(spec, _config())
    assert result.ok is False
    assert result.pass_rate == pytest.approx(0.0)
    assert any("correctness" in v.lower() or "pass_rate" in v.lower()
               for v in result.violations)
    assert not any("budget" in v.lower() for v in result.violations)


def test_weighted_partial_credit_passes(tmp_path):
    """A heavy passing assertion + a light failing one clears a 0.85 bar."""
    spec = _spec(tmp_path, """
name: scored_partial
setup: {init: {ceo_name: Alice}}
ops: []
scoring: {samples: 1, pass_threshold: 0.85, consistency_threshold: 1.0}
assertions:
  - { kind: org_status, value: initialized, weight: 9 }
  - { kind: worker_count, value: 9, weight: 1 }
""")
    result = run_canary(spec, _config())
    assert result.ok is True
    assert result.mean_score == pytest.approx(0.9)


def test_critical_assertion_failure_fails_run(tmp_path):
    """Even with a high weighted score, a failed critical assertion fails the run."""
    spec = _spec(tmp_path, """
name: scored_critical
setup: {init: {ceo_name: Alice}}
ops: []
scoring: {samples: 1, pass_threshold: 0.5, consistency_threshold: 1.0}
assertions:
  - { kind: org_status, value: initialized, weight: 9 }
  - { kind: worker_count, value: 9, weight: 1, critical: true }
""")
    result = run_canary(spec, _config())
    assert result.ok is False


def test_samples_env_override(tmp_path, monkeypatch):
    """QUINNAI_CANARY_SAMPLES overrides the spec's sample count (cost lever)."""
    monkeypatch.setenv("QUINNAI_CANARY_SAMPLES", "3")
    spec = _spec(tmp_path, """
name: scored_env
setup: {init: {ceo_name: Alice}}
ops: []
scoring: {samples: 1, pass_threshold: 0.9, consistency_threshold: 0.9}
assertions:
  - { kind: org_status, value: initialized }
""")
    result = run_canary(spec, _config())
    assert result.samples == 3


def test_wait_until_timeout_scores_run_not_aborts_canary(tmp_path):
    """A wait_until timeout is a soft failure: the run is still scored (the unmet
    predicate fails its assertion => partial/zero credit), NOT a canary abort.

    This is what makes weighted partial credit work for the live multi-agent
    canary — a worker that never ships scores low instead of crashing the run.
    """
    spec = _spec(tmp_path, """
name: timeout_soft
setup: {init: {ceo_name: Alice}}
ops:
  - { op: wait_until, predicate: { kind: worker_count, value: 5 }, timeout_seconds: 1, poll_interval_seconds: 1 }
scoring: {samples: 2, pass_threshold: 0.9, consistency_threshold: 0.9}
assertions:
  - { kind: org_status, value: initialized, weight: 1 }
  - { kind: worker_count, value: 5, weight: 1 }
""")
    result = run_canary(spec, _config())
    # The canary failed the correctness bar — but gracefully, with a verdict.
    assert result.ok is False
    assert result.verdict is not None              # NOT a crashed abort
    assert result.samples == 2
    # org_status passed, worker_count failed => 0.5 per run, below 0.9 bar.
    assert result.mean_score == pytest.approx(0.5)
    assert not any("scenario error" in v.lower() for v in result.violations)
    assert any("correctness" in v.lower() for v in result.violations)


def test_no_scoring_block_is_strict_single_shot(tmp_path):
    """Legacy spec (no scoring) => one run, every assertion must pass."""
    spec = _spec(tmp_path, """
name: legacy
setup: {init: {ceo_name: Alice}}
ops: []
assertions:
  - { kind: org_status, value: initialized }
  - { kind: worker_count, value: 1 }
""")
    result = run_canary(spec, _config())
    assert result.ok is True
    assert result.samples == 1
