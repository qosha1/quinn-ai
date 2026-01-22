"""
Budget enforcement for QuinnAI CLI.

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

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import uuid

from .db import Database
from .queries import (
    get_worker_balance,
    get_current_allocation,
    create_budget_transaction,
    get_budget_pool,
    get_worker,
    get_worker_allocations,
    create_budget_allocation,
    create_budget_balance,
    BudgetAllocation,
    BudgetBalance,
    BudgetTransaction,
)


class BudgetExhaustedError(Exception):
    """Raised when worker budget is exhausted."""

    def __init__(
        self,
        worker_id: str,
        required: float,
        available: float,
        message: Optional[str] = None,
    ):
        self.worker_id = worker_id
        self.required = required
        self.available = available
        if message is None:
            message = (
                f"Budget exhausted for worker '{worker_id}'. "
                f"Required: ${required:.4f}, Available: ${available:.4f}"
            )
        super().__init__(message)


class NoBudgetAllocationError(Exception):
    """Raised when worker has no budget allocation."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        super().__init__(
            f"No budget allocation found for worker '{worker_id}'. "
            "Contact your manager to request budget allocation."
        )


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


# Import cost estimates from constants
from .constants import (
    COST_PER_1K_TOKENS_BUDGET,
    COST_PER_1K_TOKENS_STANDARD,
    COST_PER_1K_TOKENS_ADVANCED,
    COST_PER_1K_TOKENS_PREMIUM,
)

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
) -> float:
    """Estimate cost for a provider operation.

    Args:
        model_tier: Model tier ('budget', 'standard', 'advanced', 'premium')
        input_tokens: Estimated input token count
        output_tokens: Estimated output token count

    Returns:
        Estimated cost in dollars
    """
    tier = model_tier.lower()
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

    return BudgetCheckResult(
        allowed=allowed,
        worker_id=worker_id,
        allocation_id=allocation_id,
        available=available,
        required=required_amount,
        remaining_after=remaining,
        message=message,
    )


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

    Args:
        db: Database instance
        worker_id: Worker ID
        allocation_id: Allocation ID (from BudgetCheckResult)
        amount: Actual cost in dollars
        provider: Provider name
        model: Model name
        input_tokens: Actual input token count
        output_tokens: Actual output token count
        reference_type: Optional reference type ('task', 'message', 'session')
        reference_id: Optional reference ID
        description: Optional description

    Returns:
        Created BudgetTransaction
    """
    return create_budget_transaction(
        db=db,
        allocation_id=allocation_id,
        worker_id=worker_id,
        transaction_type="spend",
        amount=-abs(amount),  # Negative for spend
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )


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
            import warnings
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


class BudgetAllocationError(Exception):
    """Raised when budget allocation fails."""

    pass


def _generate_budget_id(prefix: str = "budget") -> str:
    """Generate a unique budget-related ID."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class BudgetService:
    """Service for managing budget allocations.

    Implements the cascade pattern where budget flows from:
    - Organization pool → CEO
    - CEO → Directors
    - Directors → Managers
    - Managers → Workers

    Each level can optionally delegate to subordinates if can_delegate=True.
    """

    def __init__(self, db: Database):
        """Initialize budget service.

        Args:
            db: Database instance
        """
        self.db = db

    def allocate_from_pool(
        self,
        pool_id: str,
        worker_id: str,
        amount: float,
        period_start: datetime,
        period_end: datetime,
        can_delegate: bool = False,
        delegation_limit: Optional[float] = None,
    ) -> str:
        """Allocate budget from org pool to top-level worker (CEO).

        Args:
            pool_id: Budget pool ID
            worker_id: Target worker (typically CEO)
            amount: Credits to allocate
            period_start: Allocation period start
            period_end: Allocation period end
            can_delegate: Whether worker can sub-allocate
            delegation_limit: Max per-subordinate if delegating

        Returns:
            Allocation ID

        Raises:
            BudgetAllocationError: If pool insufficient or doesn't exist
        """
        # Verify pool exists and has sufficient funds
        pool = get_budget_pool(self.db, pool_id)
        if not pool:
            raise BudgetAllocationError(f"Budget pool {pool_id} not found")

        allocated_total = self._get_pool_allocated_total(pool_id)
        available_in_pool = float(pool.total_credits) - allocated_total

        if available_in_pool < amount:
            raise BudgetAllocationError(
                f"Insufficient pool funds: {available_in_pool:.2f} available, "
                f"{amount:.2f} requested"
            )

        # Create allocation
        allocation_id = _generate_budget_id("alloc")
        create_budget_allocation(
            self.db,
            worker_id=worker_id,
            allocated_credits=amount,
            period_start=period_start,
            period_end=period_end,
            pool_id=pool_id,
            source_worker_id=None,
            can_delegate=can_delegate,
            delegation_limit=delegation_limit,
        )

        # Initialize balance record
        create_budget_balance(
            self.db,
            allocation_id=allocation_id,
            worker_id=worker_id,
            allocated=amount,
            spent=0.0,
            reserved=0.0,
            available=amount,
            delegated=0.0,
            period_start=period_start,
            period_end=period_end,
        )

        # Record initial allocation transaction
        create_budget_transaction(
            self.db,
            allocation_id=allocation_id,
            worker_id=worker_id,
            transaction_type="allocation",
            amount=amount,
            description=f"Initial allocation from pool {pool_id}",
        )

        return allocation_id

    def delegate_budget(
        self,
        source_worker_id: str,
        target_worker_id: str,
        amount: float,
    ) -> str:
        """Delegate budget from manager to subordinate.

        Implements the cascade: manager → direct report.

        Args:
            source_worker_id: Manager delegating budget
            target_worker_id: Subordinate receiving budget
            amount: Credits to delegate

        Returns:
            New allocation ID for target

        Raises:
            BudgetAllocationError: If delegation not allowed or insufficient
        """
        # Verify hierarchy: target must report to source
        target = get_worker(self.db, target_worker_id)
        if not target:
            raise BudgetAllocationError(f"Worker {target_worker_id} not found")

        if target.manager_id != source_worker_id:
            raise BudgetAllocationError(
                f"Worker {target_worker_id} does not report to {source_worker_id}"
            )

        # Get source allocation
        source_alloc = self._get_current_allocation(source_worker_id)
        if not source_alloc:
            raise BudgetAllocationError(
                f"Worker {source_worker_id} has no budget allocation"
            )

        if not source_alloc.can_delegate:
            raise BudgetAllocationError(
                f"Worker {source_worker_id} cannot delegate budget"
            )

        # Check delegation limit
        if source_alloc.delegation_limit and amount > source_alloc.delegation_limit:
            raise BudgetAllocationError(
                f"Amount {amount:.2f} exceeds delegation limit "
                f"{source_alloc.delegation_limit:.2f}"
            )

        # Check available balance
        source_balance = get_worker_balance(self.db, source_worker_id)
        if not source_balance:
            raise BudgetAllocationError(
                f"No balance found for worker {source_worker_id}"
            )

        if source_balance.available < amount:
            raise BudgetAllocationError(
                f"Insufficient available budget: {source_balance.available:.2f} < {amount:.2f}"
            )

        # Determine if target can also delegate (managers only)
        target_can_delegate = self._is_manager(target_worker_id)

        # Create target allocation
        allocation_id = _generate_budget_id("alloc")
        create_budget_allocation(
            self.db,
            worker_id=target_worker_id,
            allocated_credits=amount,
            period_start=source_alloc.period_start,
            period_end=source_alloc.period_end,
            source_worker_id=source_worker_id,
            pool_id=None,
            can_delegate=target_can_delegate,
            delegation_limit=source_alloc.delegation_limit,
        )

        # Initialize target balance
        create_budget_balance(
            self.db,
            allocation_id=allocation_id,
            worker_id=target_worker_id,
            allocated=amount,
            spent=0.0,
            reserved=0.0,
            available=amount,
            delegated=0.0,
            period_start=source_alloc.period_start,
            period_end=source_alloc.period_end,
        )

        # Record transfer out from source
        create_budget_transaction(
            self.db,
            allocation_id=source_alloc.id,
            worker_id=source_worker_id,
            transaction_type="transfer_out",
            amount=-amount,
            description=f"Delegated to {target_worker_id}",
        )

        # Record transfer in to target
        create_budget_transaction(
            self.db,
            allocation_id=allocation_id,
            worker_id=target_worker_id,
            transaction_type="transfer_in",
            amount=amount,
            description=f"Received from {source_worker_id}",
        )

        return allocation_id

    def get_balance(self, worker_id: str) -> Optional[BudgetBalance]:
        """Get current budget balance for a worker.

        Args:
            worker_id: Worker ID

        Returns:
            BudgetBalance or None if no allocation
        """
        return get_worker_balance(self.db, worker_id)

    def get_allocation(self, worker_id: str) -> Optional[BudgetAllocation]:
        """Get current budget allocation for a worker.

        Args:
            worker_id: Worker ID

        Returns:
            BudgetAllocation or None if no allocation
        """
        return self._get_current_allocation(worker_id)

    def has_sufficient_budget(self, worker_id: str, amount: float) -> bool:
        """Check if worker has sufficient available budget.

        Args:
            worker_id: Worker ID
            amount: Amount needed

        Returns:
            True if worker has sufficient budget
        """
        balance = self.get_balance(worker_id)
        if not balance:
            return False
        return balance.available >= amount

    def revoke_unused(self, worker_id: str) -> float:
        """Revoke unused budget from terminated/offboarding worker.

        Returns unused credits to source (manager or pool).

        Args:
            worker_id: Worker being offboarded

        Returns:
            Amount revoked
        """
        alloc = self._get_current_allocation(worker_id)
        if not alloc:
            return 0.0

        balance = get_worker_balance(self.db, worker_id)
        if not balance or balance.available <= 0:
            return 0.0

        revoked_amount = balance.available

        # Record adjustment removing the balance
        create_budget_transaction(
            self.db,
            allocation_id=alloc.id,
            worker_id=worker_id,
            transaction_type="adjustment",
            amount=-revoked_amount,
            description="Budget revoked on worker termination",
        )

        # If delegated from manager, return to manager
        if alloc.source_worker_id:
            source_alloc = self._get_current_allocation(alloc.source_worker_id)
            if source_alloc:
                create_budget_transaction(
                    self.db,
                    allocation_id=source_alloc.id,
                    worker_id=alloc.source_worker_id,
                    transaction_type="refund",
                    amount=revoked_amount,
                    description=f"Recovered from terminated worker {worker_id}",
                )

        return revoked_amount

    def _get_current_allocation(self, worker_id: str) -> Optional[BudgetAllocation]:
        """Get the current (most recent) allocation for a worker."""
        allocations = get_worker_allocations(self.db, worker_id)
        if not allocations:
            return None

        # Get most recent by period_start
        now = datetime.now()
        current = None
        for alloc in allocations:
            if alloc.period_start <= now <= alloc.period_end:
                if current is None or alloc.period_start > current.period_start:
                    current = alloc

        return current or (allocations[0] if allocations else None)

    def _get_pool_allocated_total(self, pool_id: str) -> float:
        """Get total credits allocated from a pool."""
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(allocated_credits), 0) as total
               FROM budget_allocations WHERE pool_id = ?""",
            (pool_id,),
        )
        return float(row["total"]) if row else 0.0

    def _is_manager(self, worker_id: str) -> bool:
        """Check if worker has direct reports."""
        row = self.db.fetchone(
            "SELECT 1 FROM workers WHERE manager_id = ? LIMIT 1",
            (worker_id,),
        )
        return row is not None
