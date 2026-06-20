"""Deterministic correctness-scoring engine ($0 — no LLM, no harness).

This is the heart of the canary correctness gate: live runs are
non-deterministic, but the scoring/threshold math that turns a set of
assertion outcomes into a pass/fail verdict MUST be fully deterministic and
provable without spending a cent. These tests feed synthetic assertion
outcomes and assert the exact verdict.
"""
import pytest

from shared.testing.canary.scoring import (
    DEFAULT_CONSISTENCY_THRESHOLD,
    DEFAULT_PASS_THRESHOLD,
    DEFAULT_SAMPLES,
    AssertionOutcome,
    ConsistencyVerdict,
    RunScore,
    ScoringPolicy,
    evaluate_consistency,
    score_run,
)


def _o(kind, passed, weight=1.0, critical=False):
    return AssertionOutcome(kind=kind, passed=passed, weight=weight, critical=critical)


# --------------------------------------------------------------------------
# score_run — weighted per-run correctness
# --------------------------------------------------------------------------

def test_empty_outcomes_is_vacuously_correct():
    """No assertions => score 1.0 and passed (matches legacy 'no assertions = ok')."""
    rs = score_run([], pass_threshold=0.9)
    assert rs.score == 1.0
    assert rs.passed is True
    assert rs.total_weight == 0.0


def test_all_pass_scores_one():
    rs = score_run([_o("a", True), _o("b", True)], pass_threshold=0.9)
    assert rs.score == 1.0
    assert rs.passed is True


def test_all_fail_scores_zero():
    rs = score_run([_o("a", False), _o("b", False)], pass_threshold=0.9)
    assert rs.score == 0.0
    assert rs.passed is False


def test_weighted_partial_credit():
    """Weights drive the score: a heavy passing assertion outweighs a light fail."""
    # weights 9 (pass) + 1 (fail) => 9/10 = 0.9
    rs = score_run([_o("big", True, weight=9), _o("small", False, weight=1)],
                   pass_threshold=0.9)
    assert rs.score == pytest.approx(0.9)
    assert rs.passed is True  # exactly at the bar passes (>=)
    assert rs.passed_weight == pytest.approx(9.0)
    assert rs.total_weight == pytest.approx(10.0)


def test_below_threshold_fails():
    rs = score_run([_o("big", False, weight=9), _o("small", True, weight=1)],
                   pass_threshold=0.9)
    assert rs.score == pytest.approx(0.1)
    assert rs.passed is False


def test_threshold_boundary_is_inclusive():
    rs = score_run([_o("a", True), _o("b", False)], pass_threshold=0.5)
    assert rs.score == pytest.approx(0.5)
    assert rs.passed is True


def test_critical_failure_forces_fail_even_above_threshold():
    """A failed critical assertion zeroes the verdict regardless of weighted score."""
    rs = score_run(
        [_o("deliverable", False, weight=1, critical=True),
         _o("a", True, weight=9), _o("b", True, weight=9)],
        pass_threshold=0.5,
    )
    # weighted score is high (18/19) but the critical fail vetoes it
    assert rs.score == pytest.approx(18 / 19)
    assert rs.critical_failed is True
    assert rs.passed is False


def test_critical_pass_does_not_veto():
    rs = score_run(
        [_o("deliverable", True, weight=1, critical=True), _o("a", True)],
        pass_threshold=0.9,
    )
    assert rs.critical_failed is False
    assert rs.passed is True


# --------------------------------------------------------------------------
# evaluate_consistency — across-sample pass rate
# --------------------------------------------------------------------------

def _passing(score=1.0):
    return RunScore(score=score, passed=True, passed_weight=score, total_weight=1.0,
                    critical_failed=False, pass_threshold=0.9)


def _failing(score=0.0):
    return RunScore(score=score, passed=False, passed_weight=score, total_weight=1.0,
                    critical_failed=False, pass_threshold=0.9)


def test_consistency_all_pass():
    v = evaluate_consistency([_passing(), _passing(), _passing()],
                             consistency_threshold=0.9)
    assert v.ok is True
    assert v.samples == 3
    assert v.runs_passed == 3
    assert v.pass_rate == pytest.approx(1.0)


def test_consistency_two_of_three_below_90_fails():
    v = evaluate_consistency([_passing(1.0), _passing(1.0), _failing(0.0)],
                             consistency_threshold=0.9)
    assert v.runs_passed == 2
    assert v.pass_rate == pytest.approx(2 / 3)
    assert v.ok is False  # 0.66 < 0.90


def test_consistency_two_of_three_passes_lower_bar():
    v = evaluate_consistency([_passing(1.0), _passing(1.0), _failing(0.0)],
                             consistency_threshold=0.66)
    assert v.ok is True  # 0.666 >= 0.66


def test_consistency_mean_score_reported():
    v = evaluate_consistency([_passing(1.0), _failing(0.4)],
                             consistency_threshold=0.5)
    assert v.mean_score == pytest.approx(0.7)


def test_consistency_no_runs_is_not_ok():
    v = evaluate_consistency([], consistency_threshold=0.9)
    assert v.ok is False
    assert v.samples == 0
    assert v.pass_rate == 0.0


# --------------------------------------------------------------------------
# ScoringPolicy — spec parsing + backward compat + validation
# --------------------------------------------------------------------------

def test_policy_absent_block_is_strict_legacy():
    """No scoring block => strict all-pass, single shot (unchanged behaviour)."""
    p = ScoringPolicy.from_spec(None)
    assert p.samples == 1
    assert p.pass_threshold == 1.0
    assert p.consistency_threshold == 1.0


def test_policy_present_empty_block_uses_graded_defaults():
    """Opting in with `scoring: {}` activates the 90% graded defaults."""
    p = ScoringPolicy.from_spec({})
    assert p.samples == DEFAULT_SAMPLES
    assert p.pass_threshold == DEFAULT_PASS_THRESHOLD
    assert p.consistency_threshold == DEFAULT_CONSISTENCY_THRESHOLD


def test_policy_partial_block_fills_defaults():
    p = ScoringPolicy.from_spec({"samples": 3})
    assert p.samples == 3
    assert p.pass_threshold == DEFAULT_PASS_THRESHOLD
    assert p.consistency_threshold == DEFAULT_CONSISTENCY_THRESHOLD


def test_policy_full_block():
    p = ScoringPolicy.from_spec(
        {"samples": 5, "pass_threshold": 0.8, "consistency_threshold": 0.6}
    )
    assert p.samples == 5
    assert p.pass_threshold == 0.8
    assert p.consistency_threshold == 0.6


@pytest.mark.parametrize("bad", [
    {"samples": 0},
    {"samples": -1},
    {"pass_threshold": 0.0},
    {"pass_threshold": 1.5},
    {"consistency_threshold": 0.0},
    {"consistency_threshold": 2.0},
])
def test_policy_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        ScoringPolicy.from_spec(bad)


def test_defaults_are_ninety_percent():
    assert DEFAULT_PASS_THRESHOLD == 0.9
    assert DEFAULT_CONSISTENCY_THRESHOLD == 0.9
    assert DEFAULT_SAMPLES == 1
