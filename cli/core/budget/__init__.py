"""Budget enforcement for QuinnAI CLI.

Provides budget checking and transaction recording for provider calls.
All provider invocations must pass through budget enforcement to ensure
workers don't exceed their allocated budgets.

Flow:
1. Worker requests action (via session)
2. Estimate cost of operation
3. Check worker budget balance
4. If sufficient: proceed, record transaction
5. If insufficient: reject with clear message
"""

from .models import (
    BudgetExhaustedError,
    NoBudgetAllocationError,
    BudgetAllocationError,
    CostEstimate,
    BudgetCheckResult,
)
from .enforcer import (
    estimate_cost,
    check_budget,
    enforce_budget,
    record_spend,
    get_remaining_budget,
    BudgetEnforcer,
    DEFAULT_COST_PER_1K_TOKENS,
)
from .service import BudgetService

__all__ = [
    # Exceptions
    "BudgetExhaustedError",
    "NoBudgetAllocationError",
    "BudgetAllocationError",
    # Dataclasses
    "CostEstimate",
    "BudgetCheckResult",
    # Pure functions
    "estimate_cost",
    "check_budget",
    "enforce_budget",
    "record_spend",
    "get_remaining_budget",
    # Constants
    "DEFAULT_COST_PER_1K_TOKENS",
    # Classes
    "BudgetEnforcer",
    "BudgetService",
]
