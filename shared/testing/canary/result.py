"""CanaryResult — structured output of a canary run."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scoring import ConsistencyVerdict


@dataclass(frozen=True, slots=True)
class CanaryResult:
    ok: bool
    transcript: str
    spend_usd: float
    elapsed_seconds: float
    violations: list[str] = field(default_factory=list)
    # Correctness-scoring detail (quinn-ai-apg4). Defaults keep the legacy
    # single-shot shape for callers that don't inspect scoring.
    samples: int = 1
    pass_rate: float = 1.0
    mean_score: float = 1.0
    verdict: "ConsistencyVerdict | None" = None
