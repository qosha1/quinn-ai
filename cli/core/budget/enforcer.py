"""Budget enforcement: pure functions and BudgetEnforcer context manager."""

import warnings
from typing import Optional

from ..db import Database
from ..logging import get_logger, log_budget_check, log_budget_spend
from ..queries import (
    get_worker_balance,
    get_current_allocation,
    create_budget_transaction,
    BudgetTransaction,
)
from ..constants import (
    COST_PER_1K_TOKENS_BUDGET,
    COST_PER_1K_TOKENS_STANDARD,
    COST_PER_1K_TOKENS_ADVANCED,
    COST_PER_1K_TOKENS_PREMIUM,
)

# Import TYPE_CHECKING for forward reference to avoid circular imports
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import BudgetConfig

from .models import (
    BudgetCheckResult,
    BudgetExhaustedError,
    NoBudgetAllocationError,
)

_logger = get_logger(__name__)

# Default cost estimates per 1000 tokens by model tier
DEFAULT_COST_PER_1K_TOKENS = {
    "budget": COST_PER_1K_TOKENS_BUDGET,
    "standard": COST_PER_1K_TOKENS_STANDARD,
    "advanced": COST_PER_1K_TOKENS_ADVANCED,
    "premium": COST_PER_1K_TOKENS_PREMIUM,
}


def estimate_cost(
    model_tier: str,
    input_tokens: int,
    output_tokens: int,
    budget_config: Optional["BudgetConfig"] = None,
) -> float:
    """Estimate cost for a provider operation.

    Args:
        model_tier: Model tier ('budget', 'standard', 'advanced', 'premium')
        input_tokens: Estimated input token count
        output_tokens: Estimated output token count
        budget_config: Optional BudgetConfig for tier costs (falls back to constants)

    Returns:
        Estimated cost in dollars
    """
    tier = model_tier.lower()

    # Use config if provided, otherwise fall back to module-level defaults
    if budget_config is not None:
        rates = budget_config.get_tier_costs(tier)
    else:
        if tier not in DEFAULT_COST_PER_1K_TOKENS:
            tier = "standard"  # Default to standard pricing
        rates = DEFAULT_COST_PER_1K_TOKENS[tier]

    input_cost = (input_tokens / 1000) * rates["input"]
    output_cost = (output_tokens / 1000) * rates["output"]

    return input_cost + output_cost


def check_budget(
    db: Database,
    worker_id: str,
    required_amount: float,
) -> BudgetCheckResult:
    """Check if worker has sufficient budget.

    Args:
        db: Database instance
        worker_id: Worker ID
        required_amount: Required budget amount

    Returns:
        BudgetCheckResult with allowed status

    Raises:
        NoBudgetAllocationError: If worker has no allocation
    """
    # Get current balance
    balance = get_worker_balance(db, worker_id)
    if balance is None:
        # Check if there's an allocation (might be zero balance)
        allocation = get_current_allocation(db, worker_id)
        if allocation is None:
            raise NoBudgetAllocationError(worker_id)
        # Has allocation but no balance record yet
        available = allocation.allocated_credits - allocation.spent_credits - allocation.reserved_credits
        allocation_id = allocation.id
    else:
        available = balance.available
        allocation_id = balance.allocation_id

    allowed = available >= required_amount
    remaining = available - required_amount if allowed else 0.0

    if allowed:
        message = f"Budget approved: ${required_amount:.4f} of ${available:.4f} available"
    else:
        message = (
            f"Insufficient budget: need ${required_amount:.4f}, "
            f"only ${available:.4f} available"
        )

    result = BudgetCheckResult(
        allowed=allowed,
        worker_id=worker_id,
        allocation_id=allocation_id,
        available=available,
        required=required_amount,
        remaining_after=remaining,
        message=message,
    )

    # Log budget check
    log_budget_check(_logger, worker_id, required_amount, available, allowed)

    return result


def enforce_budget(
    db: Database,
    worker_id: str,
    required_amount: float,
) -> BudgetCheckResult:
    """Check budget and raise if insufficient.

    This is the main entry point for budget enforcement.
    Call this before any provider invocation.

    Args:
        db: Database instance
        worker_id: Worker ID
        required_amount: Required budget amount

    Returns:
        BudgetCheckResult if budget is sufficient

    Raises:
        BudgetExhaustedError: If budget is insufficient
        NoBudgetAllocationError: If no allocation exists
    """
    result = check_budget(db, worker_id, required_amount)

    if not result.allowed:
        raise BudgetExhaustedError(
            worker_id=worker_id,
            required=required_amount,
            available=result.available,
        )

    return result


def record_spend(
    db: Database,
    worker_id: str,
    allocation_id: str,
    amount: float,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    description: Optional[str] = None,
) -> BudgetTransaction:
    """Record a budget spend transaction.

    Call this after a successful provider invocation to record the cost.
    Re-validates budget before recording to prevent race conditions.

    Args:
        db: Database instance
        worker_id: Worker ID
        allocation_id: Allocation ID (from BudgetCheckResult)
        amount: Actual cost in dollars (must be positive)
        provider: Provider name
        model: Model name
        input_tokens: Actual input token count
        output_tokens: Actual output token count
        reference_type: Optional reference type ('task', 'message', 'session')
        reference_id: Optional reference ID
        description: Optional description

    Returns:
        Created BudgetTransaction

    Raises:
        ValueError: If amount is not positive
        BudgetExhaustedError: If budget is now insufficient (race condition)
        NoBudgetAllocationError: If allocation no longer exists
    """
    # Validate amount is positive
    if amount <= 0:
        raise ValueError(f"Spend amount must be positive, got {amount:.4f}")

    # Re-validate budget before recording spend to prevent race conditions
    # between enforce_budget check and actual recording
    balance = get_worker_balance(db, worker_id)
    if balance is None:
        allocation = get_current_allocation(db, worker_id)
        if allocation is None:
            raise NoBudgetAllocationError(worker_id)
        available = allocation.allocated_credits - allocation.spent_credits - allocation.reserved_credits
    else:
        available = balance.available

    spend_amount = abs(amount)
    if available < spend_amount:
        raise BudgetExhaustedError(
            worker_id=worker_id,
            required=spend_amount,
            available=available,
            message=(
                f"Budget insufficient at record time for worker '{worker_id}'. "
                f"Required: ${spend_amount:.4f}, Available: ${available:.4f}. "
                "Budget may have been consumed by concurrent operations."
            ),
        )

    txn = create_budget_transaction(
        db=db,
        allocation_id=allocation_id,
        worker_id=worker_id,
        transaction_type="spend",
        amount=-spend_amount,  # Negative for spend
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )

    # Log budget spend
    log_budget_spend(_logger, worker_id, spend_amount, provider, model)

    return txn


def get_remaining_budget(db: Database, worker_id: str) -> float:
    """Get remaining budget for a worker.

    Convenience function for quick budget checks.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Remaining budget in dollars, or 0.0 if no allocation
    """
    balance = get_worker_balance(db, worker_id)
    if balance is None:
        allocation = get_current_allocation(db, worker_id)
        if allocation is None:
            return 0.0
        return allocation.amount
    return balance.available


class BudgetEnforcer:
    """Context manager for budget enforcement around provider calls.

    Usage:
        with BudgetEnforcer(db, worker_id, estimated_cost) as enforcer:
            # Make provider call
            result = provider.complete(prompt)
            # Record actual cost
            enforcer.record(
                actual_cost=result.cost,
                provider="anthropic",
                model="claude-3-sonnet",
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
    """

    def __init__(
        self,
        db: Database,
        worker_id: str,
        estimated_cost: float,
    ):
        self.db = db
        self.worker_id = worker_id
        self.estimated_cost = estimated_cost
        self._check_result: Optional[BudgetCheckResult] = None
        self._recorded = False

    def __enter__(self) -> "BudgetEnforcer":
        """Check budget on entry."""
        self._check_result = enforce_budget(
            self.db,
            self.worker_id,
            self.estimated_cost,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Log warning if spend wasn't recorded."""
        if not self._recorded and exc_type is None:
            # Operation succeeded but spend wasn't recorded
            # This is a bug in the calling code
            warnings.warn(
                f"BudgetEnforcer for worker '{self.worker_id}' exited without "
                "recording spend. Call enforcer.record() after provider call.",
                UserWarning,
            )

    @property
    def allocation_id(self) -> str:
        """Get allocation ID from check result."""
        if self._check_result is None:
            raise RuntimeError("BudgetEnforcer not entered")
        return self._check_result.allocation_id

    def record(
        self,
        actual_cost: float,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> BudgetTransaction:
        """Record actual spend after provider call.

        Args:
            actual_cost: Actual cost in dollars
            provider: Provider name
            model: Model name
            input_tokens: Actual input token count
            output_tokens: Actual output token count
            reference_type: Optional reference type
            reference_id: Optional reference ID
            description: Optional description

        Returns:
            Created BudgetTransaction
        """
        if self._check_result is None:
            raise RuntimeError("BudgetEnforcer not entered")

        txn = record_spend(
            db=self.db,
            worker_id=self.worker_id,
            allocation_id=self._check_result.allocation_id,
            amount=actual_cost,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )
        self._recorded = True
        return txn
