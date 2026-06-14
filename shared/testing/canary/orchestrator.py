"""run_canary — execute a scenario against a live LLM with budget guardrails."""
from __future__ import annotations

import io
import time
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


def run_canary(spec: ScenarioSpec, config: ProviderConfig) -> CanaryResult:
    """Run a scenario spec against a live LLM provider.

    Returns a CanaryResult with structured failure mode info so callers can
    distinguish budget-kill from real assertion failure.
    """
    pricing = _load_default_pricing()
    guard = BudgetGuard(config=config, pricing=pricing)
    transcript_buf = io.StringIO()

    violations: list[str] = []
    ok = True

    try:
        with redirect_stdout(transcript_buf):
            # use_fake_spawner=False so 'qn org start' inside the scenario hits
            # the real claude_code provider instead of the FakeSpawner used in
            # Tier 2 scenarios.
            with ScenarioHarness(spec, use_fake_spawner=False) as run:
                for op in spec.ops:
                    guard.check_time()
                    run.run_op(op)
                    # Conservative spend account: model can't see this directly,
                    # but hooks downstream may call guard.account().
                for assertion in spec.assertions:
                    msg = run.check(assertion)
                    if msg is not None:
                        violations.append(msg)
        ok = not violations
    except BudgetExceeded as e:
        ok = False
        violations.append(f"budget exceeded ({e.reason}): {e.detail}")
    except Exception as e:
        ok = False
        violations.append(f"scenario error: {type(e).__name__}: {e}")

    return CanaryResult(
        ok=ok,
        transcript=transcript_buf.getvalue(),
        spend_usd=config.budget_usd - guard.remaining_usd,
        elapsed_seconds=guard.elapsed_seconds,
        violations=violations,
    )
