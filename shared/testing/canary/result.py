"""CanaryResult — structured output of a canary run."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CanaryResult:
    ok: bool
    transcript: str
    spend_usd: float
    elapsed_seconds: float
    violations: list[str] = field(default_factory=list)
