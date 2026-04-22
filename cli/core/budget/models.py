"""Budget domain models and exceptions."""

from dataclasses import dataclass
from typing import Optional

from shared.exceptions import (
    BudgetExhaustedError,
    NoBudgetAllocationError,
    BudgetAllocationError,
)

__all__ = [
    "BudgetExhaustedError",
    "NoBudgetAllocationError",
    "BudgetAllocationError",
]


@dataclass
class CostEstimate:
    """Estimated cost for a provider operation."""
    provider: str
    model: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost: float
    confidence: str  # 'exact', 'estimated', 'worst_case'


@dataclass
class BudgetCheckResult:
    """Result of a budget check."""
    allowed: bool
    worker_id: str
    allocation_id: str
    available: float
    required: float
    remaining_after: float
    message: str
