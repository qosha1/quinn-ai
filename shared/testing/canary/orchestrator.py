"""run_canary — execute a scenario against a live LLM with budget guardrails.

A canary is gated by a deterministic correctness bar (quinn-ai-apg4): each
sampled run is scored against a weighted rubric of assertions, a run passes when
it clears ``pass_threshold``, and the canary passes only when the fraction of
passing runs across ``samples`` independent runs clears ``consistency_threshold``.
The LLM supplies the variance; ``scoring.py`` supplies the deterministic verdict.
"""
from __future__ import annotations

import io
import os
from contextlib import redirect_stdout

from shared.testing.scenarios import ScenarioHarness, ScenarioSpec

# Side-effect import: registers canary ops into the shared OPS dict.
from . import canary_ops  # noqa: F401
# Side-effect import: registers host-mode (isolated throwaway repo) ops +
# the branch_on_remote predicate (quinn-ai-a3pg).
from . import host_repo  # noqa: F401
from .budget import BudgetExceeded, BudgetGuard, Pricing
from .driver import build_live_session  # noqa: F401  (placeholder for direct-API flows)
from .provider_config import ProviderConfig
from .result import CanaryResult
from .scoring import (
    AssertionOutcome,
    RunScore,
    ScoringPolicy,
    evaluate_consistency,
    score_run,
)

# Env override: force the sample count regardless of the spec (cost lever — set
# to 1 for cheap CI, higher for a nightly soak that wants tighter confidence).
SAMPLES_ENV_VAR = "QUINNAI_CANARY_SAMPLES"


def _load_default_pricing() -> Pricing:
    """Read pricing.yaml from the canary package."""
    import yaml
    from importlib.resources import files

    data = yaml.safe_load(files(__package__).joinpath("pricing.yaml").read_text())
    table: dict[tuple[str, str], dict[str, float]] = {}
    for provider, models in (data or {}).items():
        for model_id, p in (models or {}).items():
            table[(provider, model_id)] = p
    return Pricing(table)


def _resolve_samples(policy: ScoringPolicy) -> int:
    """Spec sample count, overridable by env for cost control."""
    raw = os.environ.get(SAMPLES_ENV_VAR)
    if raw is None:
        return policy.samples
    try:
        n = int(raw)
    except ValueError:
        return policy.samples
    return max(1, n)


def _evaluate_assertions(run, spec: ScenarioSpec) -> list[AssertionOutcome]:
    """Run every assertion predicate once, building weighted outcomes.

    A predicate returns None on success or a violation message; that maps
    directly to ``passed``. Per-assertion ``weight``/``critical`` come from the
    assertion dict (defaults 1.0 / False).
    """
    outcomes: list[AssertionOutcome] = []
    for assertion in spec.assertions:
        msg = run.check(assertion)
        outcomes.append(
            AssertionOutcome(
                kind=assertion.get("kind", "?"),
                passed=msg is None,
                weight=float(assertion.get("weight", 1.0)),
                critical=bool(assertion.get("critical", False)),
                message=msg,
            )
        )
    return outcomes


def _run_one_sample(
    spec: ScenarioSpec,
    guard: BudgetGuard,
    policy: ScoringPolicy,
    index: int,
) -> tuple[RunScore, str]:
    """Execute one isolated sample run and score it.

    Returns the RunScore and the sample's captured transcript. Only
    BudgetExceeded propagates (the caller aborts the whole canary). Any other
    op failure — most importantly a ``wait_until`` timeout, which simply means
    the awaited outcome never happened — is captured as a soft error: the run's
    assertions are STILL evaluated and scored, so the unmet outcome fails its
    (possibly critical) assertion and the run earns partial/zero credit instead
    of crashing the canary. This is what makes weighted partial credit work for
    the non-deterministic multi-agent canary.
    """
    buf = io.StringIO()
    guard.check_time()
    op_error: Exception | None = None
    with redirect_stdout(buf):
        # use_fake_spawner=False so 'qn org start' hits the real claude_code
        # provider, not the Tier-2 FakeSpawner. Fresh harness per sample =>
        # full isolation (its own tmpdir + throwaway repo + bare remote).
        with ScenarioHarness(spec, use_fake_spawner=False) as run:
            try:
                for op in spec.ops:
                    guard.check_time()
                    run.run_op(op)
            except BudgetExceeded:
                raise  # budget kill must abort the whole canary, never score
            except Exception as e:  # soft: score the run anyway
                op_error = e
            outcomes = _evaluate_assertions(run, spec)
    rs = score_run(outcomes, pass_threshold=policy.pass_threshold)
    note = (
        f" [op aborted: {type(op_error).__name__}: {op_error}]"
        if op_error is not None
        else ""
    )
    header = f"===== sample {index + 1} ({rs.summary()}){note} =====\n"
    return rs, header + buf.getvalue()


def run_canary(spec: ScenarioSpec, config: ProviderConfig) -> CanaryResult:
    """Run a scenario spec against a live LLM provider with a correctness gate.

    Runs the scenario ``samples`` times under one shared BudgetGuard (so total
    wall-clock/spend is bounded across samples), scores each run, and returns a
    CanaryResult whose ``ok`` reflects the deterministic consistency verdict.
    A budget kill aborts the whole canary and is reported as a budget violation
    (callers skip rather than fail).
    """
    pricing = _load_default_pricing()
    guard = BudgetGuard(config=config, pricing=pricing)
    policy = ScoringPolicy.from_spec(spec.scoring)
    samples = _resolve_samples(policy)

    transcripts: list[str] = []
    run_scores: list[RunScore] = []

    try:
        for i in range(samples):
            rs, transcript = _run_one_sample(spec, guard, policy, i)
            run_scores.append(rs)
            transcripts.append(transcript)
    except BudgetExceeded as e:
        # Budget kill is an abort, not a correctness failure. Preserve the
        # legacy skip semantics: ok=False with a budget violation.
        return CanaryResult(
            ok=False,
            transcript="\n".join(transcripts),
            spend_usd=config.budget_usd - guard.remaining_usd,
            elapsed_seconds=guard.elapsed_seconds,
            violations=[f"budget exceeded ({e.reason}): {e.detail}"],
            samples=samples,
            pass_rate=0.0,
            mean_score=0.0,
            verdict=None,
        )
    except Exception as e:  # pragma: no cover - defensive
        return CanaryResult(
            ok=False,
            transcript="\n".join(transcripts),
            spend_usd=config.budget_usd - guard.remaining_usd,
            elapsed_seconds=guard.elapsed_seconds,
            violations=[f"scenario error: {type(e).__name__}: {e}"],
            samples=samples,
            pass_rate=0.0,
            mean_score=0.0,
            verdict=None,
        )

    verdict = evaluate_consistency(
        run_scores, consistency_threshold=policy.consistency_threshold
    )

    violations: list[str] = []
    if not verdict.ok:
        violations.append(f"correctness below bar: {verdict.summary()}")
        for i, rs in enumerate(verdict.run_scores):
            if not rs.passed:
                violations.append(f"  run {i + 1}: {rs.summary()}")

    return CanaryResult(
        ok=verdict.ok,
        transcript="\n".join(transcripts),
        spend_usd=config.budget_usd - guard.remaining_usd,
        elapsed_seconds=guard.elapsed_seconds,
        violations=violations,
        samples=verdict.samples,
        pass_rate=verdict.pass_rate,
        mean_score=verdict.mean_score,
        verdict=verdict,
    )
