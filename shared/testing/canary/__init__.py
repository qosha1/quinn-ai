"""Live LLM canary framework — post-publish smoke against a real model.

Public API:
    ProviderConfig
    Pricing, TokenEstimator, BudgetGuard, BudgetExceeded
    CanaryResult, run_canary
    ScoringPolicy, ConsistencyVerdict, RunScore, AssertionOutcome  (scoring)
    build_live_session  (low-level; most callers use run_canary)
"""
from .budget import BudgetExceeded, BudgetGuard, Pricing, TokenEstimator
from .driver import build_live_session
from .orchestrator import run_canary
from .provider_config import ProviderConfig
from .result import CanaryResult
from .scoring import (
    AssertionOutcome,
    ConsistencyVerdict,
    RunScore,
    ScoringPolicy,
    evaluate_consistency,
    score_run,
)

__all__ = [
    "AssertionOutcome",
    "BudgetExceeded",
    "BudgetGuard",
    "CanaryResult",
    "ConsistencyVerdict",
    "Pricing",
    "ProviderConfig",
    "RunScore",
    "ScoringPolicy",
    "TokenEstimator",
    "build_live_session",
    "evaluate_consistency",
    "run_canary",
    "score_run",
]
