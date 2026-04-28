"""BudgetGuard — wall-clock + spend caps for canary runs."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, Mapping

from .provider_config import ProviderConfig


# Pricing entry shape: {"input_per_1k": <usd>, "output_per_1k": <usd>}
ModelPricing = Mapping[str, float]


class Pricing:
    """Wraps a (provider, model) -> ModelPricing table.

    Loaded from pricing.yaml; can also be constructed inline for tests.
    """

    def __init__(self, table: dict[tuple[str, str], ModelPricing]):
        self._table = dict(table)

    def get(self, provider: str, model: str) -> ModelPricing:
        if (provider, model) in self._table:
            return self._table[(provider, model)]
        # Fallback: zero-cost so the run completes; budget guard then triggers
        # only on wall-clock. Operator should add the new entry to pricing.yaml.
        return {"input_per_1k": 0.0, "output_per_1k": 0.0}


class TokenEstimator:
    """Token + cost estimation. Heuristic-based; tighten with real tokenizers later."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # Anthropic + OpenAI both average ~4 chars/token for English prose.
        return max(1, len(text) // 4)

    @staticmethod
    def cost(usage: Mapping[str, int], pricing: ModelPricing) -> float:
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        return (in_tok / 1000.0) * pricing.get("input_per_1k", 0.0) + (
            out_tok / 1000.0
        ) * pricing.get("output_per_1k", 0.0)


class BudgetExceeded(Exception):
    """Raised when wall-clock or spend cap is hit."""

    def __init__(self, reason: Literal["wall_clock", "spend"], detail: dict):
        self.reason = reason
        self.detail = detail
        super().__init__(f"BudgetExceeded({reason}): {detail}")


class BudgetGuard:
    """Tracks elapsed time + cumulative spend; raises BudgetExceeded when limits hit.

    Usage:
        guard = BudgetGuard(config=cfg, pricing=Pricing.load_default())
        # After each LLM call:
        guard.account(usage={"input_tokens": ..., "output_tokens": ...})
        # Periodically:
        guard.check_time()
    """

    def __init__(
        self,
        *,
        config: ProviderConfig,
        pricing: Pricing,
        provider_override: str | None = None,
    ):
        self._config = config
        self._pricing = pricing
        self._provider = provider_override or config.provider
        self._start = time.monotonic()
        self._spent_usd = 0.0

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start

    @property
    def remaining_usd(self) -> float:
        return self._config.budget_usd - self._spent_usd

    def check_time(self) -> None:
        if self.elapsed_seconds > self._config.budget_seconds:
            raise BudgetExceeded(
                reason="wall_clock",
                detail={
                    "elapsed_seconds": self.elapsed_seconds,
                    "budget_seconds": self._config.budget_seconds,
                },
            )

    def account(self, usage: Mapping[str, int]) -> None:
        pricing = self._pricing.get(self._provider, self._config.model)
        cost = TokenEstimator.cost(usage, pricing)
        self._spent_usd += cost
        if self._spent_usd > self._config.budget_usd:
            raise BudgetExceeded(
                reason="spend",
                detail={
                    "spent_usd": self._spent_usd,
                    "budget_usd": self._config.budget_usd,
                    "last_call_usd": cost,
                },
            )
        self.check_time()
