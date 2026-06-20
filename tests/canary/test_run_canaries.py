"""Run every canary spec — gated by QUINNAI_RUN_CANARY=1."""
from pathlib import Path

import pytest

from shared.testing.canary import ProviderConfig, run_canary
from shared.testing.scenarios import ScenarioSpec


# Live canaries spawn real LLM sessions and routinely take 10-60 minutes;
# the 30s default in pytest.ini will kill the run mid-flight without this.
# Override matches the wall-clock cap in QUINNAI_CANARY_BUDGET_SECONDS so the
# BudgetGuard remains the primary kill-switch.
@pytest.mark.canary
@pytest.mark.timeout(3600)
def test_canary(canary_spec_path: Path):
    spec = ScenarioSpec.from_yaml(canary_spec_path)
    config = ProviderConfig.from_env()

    result = run_canary(spec, config)

    if not result.ok:
        if any("budget" in v.lower() for v in result.violations):
            pytest.skip(
                f"canary {spec.name} aborted by budget guard "
                f"(spend=${result.spend_usd:.4f}, elapsed={result.elapsed_seconds:.0f}s)"
            )
        verdict_line = (
            f"\nscoring: {result.verdict.summary()}"
            if result.verdict is not None
            else ""
        )
        pytest.fail(
            f"canary {spec.name} failed the correctness bar "
            f"(pass_rate={result.pass_rate:.2f}, mean_score={result.mean_score:.2f}, "
            f"samples={result.samples}):{verdict_line}\n"
            + "\n".join(f"  - {v}" for v in result.violations)
            + f"\n\nTranscript:\n{result.transcript[:5000]}"
        )
