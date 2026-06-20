"""Deterministic correctness scoring for live canaries.

Live multi-agent canaries are non-deterministic at the token level — the same
prompt yields different worker behaviour each run, so binary "every assertion
must pass" gating is luck-based. We cannot demand identical output, but we MUST
demand a deterministic *correctness bar*:

  1. Each run is scored against a weighted rubric of assertions, producing a
     correctness score in [0.0, 1.0] (passed weight / total weight).
  2. A run "passes" when its score clears ``pass_threshold`` AND no assertion
     flagged ``critical`` failed.
  3. The canary as a whole passes only when the fraction of passing runs across
     ``samples`` independent runs clears ``consistency_threshold``.

Everything in this module is pure and side-effect free, so the scoring/gating
logic is unit-tested at $0 with synthetic assertion outcomes — the LLM supplies
the variance, this module supplies the deterministic verdict. ``< threshold ===
fail`` is enforced here, not in the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

# Graded defaults, applied when a spec opts in with a ``scoring`` block but
# leaves a key unset. The correctness bar is 90%: a run must satisfy >=90% of
# weighted assertions, and >=90% of sampled runs must pass.
DEFAULT_PASS_THRESHOLD = 0.9
DEFAULT_CONSISTENCY_THRESHOLD = 0.9
DEFAULT_SAMPLES = 1
DEFAULT_WEIGHT = 1.0


@dataclass(frozen=True, slots=True)
class AssertionOutcome:
    """One assertion's result within a single run.

    Attributes:
        kind: Predicate kind (e.g. ``branch_on_remote``).
        passed: Whether the predicate was satisfied.
        weight: Relative importance in the weighted score (default 1.0).
        critical: If True, a failure vetoes the whole run regardless of score.
        message: Predicate violation message when failed (None on pass).
    """

    kind: str
    passed: bool
    weight: float = DEFAULT_WEIGHT
    critical: bool = False
    message: str | None = None


@dataclass(frozen=True, slots=True)
class RunScore:
    """Weighted correctness verdict for a single run."""

    score: float
    passed: bool
    passed_weight: float
    total_weight: float
    critical_failed: bool
    pass_threshold: float
    outcomes: tuple[AssertionOutcome, ...] = ()

    def summary(self) -> str:
        bits = [f"score={self.score:.2f} (>= {self.pass_threshold:.2f} to pass)"]
        if self.critical_failed:
            bits.append("CRITICAL assertion failed")
        failed = [o for o in self.outcomes if not o.passed]
        if failed:
            bits.append(
                "failed: "
                + ", ".join(
                    f"{o.kind}(w={o.weight:g}{',crit' if o.critical else ''})"
                    for o in failed
                )
            )
        return "; ".join(bits)


@dataclass(frozen=True, slots=True)
class ConsistencyVerdict:
    """Across-sample verdict: how consistently the org cleared the bar."""

    ok: bool
    samples: int
    runs_passed: int
    pass_rate: float
    mean_score: float
    consistency_threshold: float
    run_scores: tuple[RunScore, ...] = ()

    def summary(self) -> str:
        return (
            f"pass_rate={self.pass_rate:.2f} "
            f"({self.runs_passed}/{self.samples} runs, mean_score={self.mean_score:.2f}); "
            f"bar={self.consistency_threshold:.2f} => {'PASS' if self.ok else 'FAIL'}"
        )


def score_run(
    outcomes: Sequence[AssertionOutcome],
    *,
    pass_threshold: float,
) -> RunScore:
    """Compute the weighted correctness score for one run.

    Args:
        outcomes: Per-assertion results for this run.
        pass_threshold: Minimum weighted score (inclusive) for the run to pass.

    Returns:
        A RunScore. An empty rubric is vacuously correct (score 1.0), matching
        the legacy "no assertions = ok" behaviour. A failed ``critical``
        assertion forces ``passed=False`` regardless of the weighted score.
    """
    outcomes = tuple(outcomes)
    total_weight = sum(o.weight for o in outcomes)
    passed_weight = sum(o.weight for o in outcomes if o.passed)
    score = 1.0 if total_weight == 0 else passed_weight / total_weight
    critical_failed = any(o.critical and not o.passed for o in outcomes)
    passed = (score >= pass_threshold) and not critical_failed
    return RunScore(
        score=score,
        passed=passed,
        passed_weight=passed_weight,
        total_weight=total_weight,
        critical_failed=critical_failed,
        pass_threshold=pass_threshold,
        outcomes=outcomes,
    )


def evaluate_consistency(
    run_scores: Sequence[RunScore],
    *,
    consistency_threshold: float,
) -> ConsistencyVerdict:
    """Aggregate per-run scores into a deterministic pass/fail verdict.

    Args:
        run_scores: One RunScore per sampled run.
        consistency_threshold: Minimum fraction of passing runs (inclusive) for
            the canary to pass overall.

    Returns:
        A ConsistencyVerdict. Zero runs is never OK (nothing was proven).
    """
    run_scores = tuple(run_scores)
    samples = len(run_scores)
    runs_passed = sum(1 for r in run_scores if r.passed)
    pass_rate = (runs_passed / samples) if samples else 0.0
    mean_score = (sum(r.score for r in run_scores) / samples) if samples else 0.0
    ok = samples > 0 and pass_rate >= consistency_threshold
    return ConsistencyVerdict(
        ok=ok,
        samples=samples,
        runs_passed=runs_passed,
        pass_rate=pass_rate,
        mean_score=mean_score,
        consistency_threshold=consistency_threshold,
        run_scores=run_scores,
    )


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    """Resolved scoring configuration for a canary spec.

    Backward compatible: a spec with no ``scoring`` block resolves to the strict
    legacy policy (every assertion must pass, single shot). Opting in — even
    with an empty ``scoring: {}`` block — activates the 90% graded defaults.
    """

    samples: int = DEFAULT_SAMPLES
    pass_threshold: float = DEFAULT_PASS_THRESHOLD
    consistency_threshold: float = DEFAULT_CONSISTENCY_THRESHOLD

    def __post_init__(self) -> None:
        if self.samples < 1:
            raise ValueError(f"samples must be >= 1, got {self.samples}")
        for name, val in (
            ("pass_threshold", self.pass_threshold),
            ("consistency_threshold", self.consistency_threshold),
        ):
            if not (0.0 < val <= 1.0):
                raise ValueError(f"{name} must be in (0.0, 1.0], got {val}")

    @classmethod
    def strict(cls) -> "ScoringPolicy":
        """Legacy gate: every assertion must pass, exactly one run."""
        return cls(samples=1, pass_threshold=1.0, consistency_threshold=1.0)

    @classmethod
    def from_spec(cls, scoring: dict | None) -> "ScoringPolicy":
        """Resolve a policy from a spec's ``scoring`` mapping.

        ``None`` (block absent) => strict legacy policy. A present mapping
        (including empty ``{}``) => graded defaults filled in for unset keys.
        """
        if scoring is None:
            return cls.strict()
        return cls(
            samples=int(scoring.get("samples", DEFAULT_SAMPLES)),
            pass_threshold=float(scoring.get("pass_threshold", DEFAULT_PASS_THRESHOLD)),
            consistency_threshold=float(
                scoring.get("consistency_threshold", DEFAULT_CONSISTENCY_THRESHOLD)
            ),
        )
