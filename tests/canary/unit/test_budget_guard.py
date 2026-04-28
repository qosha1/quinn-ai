"""BudgetGuard tests — wall-clock + spend caps."""
import time

import pytest

from shared.testing.canary import (
    BudgetExceeded,
    BudgetGuard,
    Pricing,
    ProviderConfig,
    TokenEstimator,
)


def _cfg(*, usd: float = 1.0, seconds: int = 60) -> ProviderConfig:
    return ProviderConfig(
        provider="claude_code",
        model="claude-sonnet-4-5",
        api_key_env="ANTHROPIC_API_KEY",
        budget_usd=usd,
        budget_seconds=seconds,
    )


def _pricing() -> Pricing:
    return Pricing(
        {
            ("claude_code", "claude-sonnet-4-5"): {"input_per_1k": 0.003, "output_per_1k": 0.015},
        }
    )


class TestTokenEstimator:
    def test_estimate_tokens_short(self):
        # ~1 token per 4 chars heuristic
        assert TokenEstimator.estimate_tokens("hello world") == pytest.approx(3, abs=1)

    def test_cost_uses_pricing(self):
        cost = TokenEstimator.cost(
            usage={"input_tokens": 1000, "output_tokens": 500},
            pricing={"input_per_1k": 0.003, "output_per_1k": 0.015},
        )
        # 1*0.003 + 0.5*0.015 = 0.0105
        assert cost == pytest.approx(0.0105)


class TestBudgetGuardSpend:
    def test_under_budget_passes(self):
        guard = BudgetGuard(config=_cfg(usd=0.10), pricing=_pricing())
        guard.account(usage={"input_tokens": 1000, "output_tokens": 500})
        # 0.0105 < 0.10
        assert guard.remaining_usd > 0

    def test_over_budget_raises_with_spend_reason(self):
        guard = BudgetGuard(config=_cfg(usd=0.001), pricing=_pricing())
        with pytest.raises(BudgetExceeded) as exc:
            guard.account(usage={"input_tokens": 5000, "output_tokens": 5000})
        assert exc.value.reason == "spend"

    def test_remaining_decreases_after_account(self):
        guard = BudgetGuard(config=_cfg(usd=1.0), pricing=_pricing())
        before = guard.remaining_usd
        guard.account(usage={"input_tokens": 1000, "output_tokens": 500})
        after = guard.remaining_usd
        assert after < before


class TestBudgetGuardWallClock:
    def test_within_time_passes(self):
        guard = BudgetGuard(config=_cfg(seconds=60), pricing=_pricing())
        guard.check_time()  # immediately, well within
        assert guard.elapsed_seconds < 60

    def test_over_time_raises_with_wall_clock_reason(self):
        # Use a 1-second budget then sleep past it.
        guard = BudgetGuard(config=_cfg(seconds=1), pricing=_pricing())
        time.sleep(1.05)
        with pytest.raises(BudgetExceeded) as exc:
            guard.check_time()
        assert exc.value.reason == "wall_clock"


class TestBudgetGuardModularity:
    """Brutality check: BudgetGuard.account must work with arbitrary token usage dicts."""

    def test_works_with_unrelated_pricing_table(self):
        # A pricing table for some made-up provider
        pricing = Pricing(
            {("xyz", "model-a"): {"input_per_1k": 0.001, "output_per_1k": 0.002}}
        )
        cfg = ProviderConfig(provider="claude_code", model="model-a", api_key_env="X", budget_usd=0.50)
        # Manually wire to alternate pricing
        guard = BudgetGuard(config=cfg, pricing=pricing, provider_override="xyz")
        guard.account(usage={"input_tokens": 100, "output_tokens": 100})
        assert guard.remaining_usd < 0.50
