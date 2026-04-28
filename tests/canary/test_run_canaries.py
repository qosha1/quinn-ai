"""Run every canary spec — gated by QUINNAI_RUN_CANARY=1."""
from pathlib import Path

import pytest

from shared.testing.canary import ProviderConfig, run_canary
from shared.testing.scenarios import ScenarioSpec


@pytest.mark.canary
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
        pytest.fail(
            f"canary {spec.name} failed:\n"
            + "\n".join(f"  - {v}" for v in result.violations)
            + f"\n\nTranscript:\n{result.transcript[:5000]}"
        )
