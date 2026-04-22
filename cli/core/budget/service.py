"""BudgetService: higher-level allocation management."""

import uuid
from datetime import datetime
from typing import Optional

from ..db import Database
from ..queries import (
    get_worker_balance,
    get_current_allocation,
    create_budget_transaction,
    get_budget_pool,
    get_worker,
    get_worker_allocations,
    create_budget_allocation,
    create_budget_balance,
    get_pool_allocated_total,
    is_worker_manager,
    BudgetAllocation,
    BudgetBalance,
)

# Import TYPE_CHECKING for forward reference to avoid circular imports
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import BudgetConfig

from .models import BudgetAllocationError
from .enforcer import estimate_cost


def _generate_budget_id(prefix: str = "budget") -> str:
    """Generate a unique budget-related ID."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class BudgetService:
    """Service for managing budget allocations.

    Implements the cascade pattern where budget flows from:
    - Organization pool -> CEO
    - CEO -> Directors
    - Directors -> Managers
    - Managers -> Workers

    Each level can optionally delegate to subordinates if can_delegate=True.
    """

    def __init__(
        self,
        db: Database,
        budget_config: Optional["BudgetConfig"] = None,
    ):
        """Initialize budget service.

        Args:
            db: Database instance
            budget_config: Optional budget configuration for cost estimates.
                Falls back to constants if not provided.
        """
        self.db = db
        self._budget_config = budget_config

    @property
    def budget_config(self) -> Optional["BudgetConfig"]:
        """Get the budget configuration."""
        return self._budget_config

    def estimate_cost(
        self,
        model_tier: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost for a provider operation using config.

        Args:
            model_tier: Model tier ('budget', 'standard', 'advanced', 'premium')
            input_tokens: Estimated input token count
            output_tokens: Estimated output token count

        Returns:
            Estimated cost in dollars
        """
        return estimate_cost(
            model_tier=model_tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            budget_config=self._budget_config,
        )

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

        All state changes are wrapped in a transaction for atomicity.

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
        # === VALIDATION PHASE (before any state changes) ===

        # Validate amount is positive
        if amount <= 0:
            raise BudgetAllocationError(
                f"Allocation amount must be positive, got {amount:.2f}"
            )

        # Verify pool exists and has sufficient funds
        pool = get_budget_pool(self.db, pool_id)
        if not pool:
            raise BudgetAllocationError(f"Budget pool {pool_id} not found")

        allocated_total = get_pool_allocated_total(self.db, pool_id)
        available_in_pool = float(pool.total_credits) - allocated_total

        if available_in_pool < amount:
            raise BudgetAllocationError(
                f"Insufficient pool funds: {available_in_pool:.2f} available, "
                f"{amount:.2f} requested"
            )

        # Generate allocation ID before transaction
        allocation_id = _generate_budget_id("alloc")

        # === EXECUTION PHASE (all state changes in transaction) ===
        # Use transaction to ensure atomicity - if any step fails,
        # all changes are rolled back automatically
        with self.db.transaction():
            # Re-validate pool balance inside transaction to prevent race conditions
            allocated_total = get_pool_allocated_total(self.db, pool_id)
            available_in_pool = float(pool.total_credits) - allocated_total

            if available_in_pool < amount:
                raise BudgetAllocationError(
                    f"Insufficient pool funds: {available_in_pool:.2f} available, "
                    f"{amount:.2f} requested"
                )

            # Create allocation with our pre-generated ID
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
                allocation_id=allocation_id,
            )

            # Initialize balance record with zero - the allocation transaction
            # will set the correct values via the database trigger
            create_budget_balance(
                self.db,
                allocation_id=allocation_id,
                worker_id=worker_id,
                allocated=0.0,
                period_start=period_start,
                period_end=period_end,
            )

            # Record initial allocation transaction - trigger updates balance
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

        Implements the cascade: manager -> direct report.
        All state changes are wrapped in a transaction for atomicity.

        Args:
            source_worker_id: Manager delegating budget
            target_worker_id: Subordinate receiving budget
            amount: Credits to delegate

        Returns:
            New allocation ID for target

        Raises:
            BudgetAllocationError: If delegation not allowed or insufficient
        """
        # === VALIDATION PHASE (before any state changes) ===

        # Validate amount is positive
        if amount <= 0:
            raise BudgetAllocationError(
                f"Delegation amount must be positive, got {amount:.2f}"
            )

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
        target_can_delegate = is_worker_manager(self.db, target_worker_id)

        # Generate allocation ID before transaction
        allocation_id = _generate_budget_id("alloc")

        # === EXECUTION PHASE (all state changes in transaction) ===
        # Use transaction to ensure atomicity - if any step fails,
        # all changes are rolled back automatically
        with self.db.transaction():
            # Re-validate balance inside transaction to prevent race conditions
            source_balance = get_worker_balance(self.db, source_worker_id)
            if not source_balance or source_balance.available < amount:
                available = source_balance.available if source_balance else 0.0
                raise BudgetAllocationError(
                    f"Insufficient available budget: {available:.2f} < {amount:.2f}"
                )

            # Create target allocation with our pre-generated ID
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
                allocation_id=allocation_id,
            )

            # Initialize target balance with zero - the transfer_in transaction
            # will set the correct values via the database trigger
            create_budget_balance(
                self.db,
                allocation_id=allocation_id,
                worker_id=target_worker_id,
                allocated=0.0,
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

        def parse_dt(val):
            """Parse datetime from string or return as-is if already datetime."""
            if isinstance(val, str):
                return datetime.fromisoformat(val)
            return val

        # Get most recent by period_start
        now = datetime.now()
        current = None
        for alloc in allocations:
            period_start = parse_dt(alloc.period_start)
            period_end = parse_dt(alloc.period_end)

            if period_start <= now <= period_end:
                if current is None:
                    current = alloc
                else:
                    current_start = parse_dt(current.period_start)
                    if period_start > current_start:
                        current = alloc

        return current or (allocations[0] if allocations else None)
