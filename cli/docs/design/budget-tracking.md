# Budget Tracking System Design

## Overview

The budget tracking system enables cascading budget allocation from Board to CEO to Directors to Managers to Workers, mirroring the OKR cascade pattern established in QuinnAI's principles. Budget flows downward through the organizational hierarchy, with spend tracking at every provider call.

## Budget Unit Decision: Credits

**Decision: Use "credits" as the internal budget unit.**

### Rationale

| Option | Pros | Cons |
|--------|------|------|
| **Tokens** | Direct API mapping | Provider-specific rates differ wildly; Claude tokens != GPT tokens |
| **Dollars** | User-familiar | Requires real-time price lookup; complex tax/currency handling |
| **Credits** | Provider-agnostic; stable internal accounting; configurable exchange rates | Requires translation layer |

Credits provide:
1. **Provider Independence**: 1 credit = 1 credit regardless of provider
2. **Configurable Rates**: Admin sets `credits_per_dollar` and `provider_rates` in config
3. **Budget Stability**: Internal accounting unaffected by provider price changes
4. **Fractional Support**: Integer credits with DECIMAL(15,2) for precision

### Credit Configuration (in org config.yaml)

```yaml
budget:
  # Base exchange rate
  credits_per_dollar: 1000  # 1 dollar = 1000 credits

  # Provider-specific rates (credits per 1K tokens)
  provider_rates:
    anthropic:
      claude-3-haiku: 0.25      # ~$0.00025/1K input
      claude-3-5-sonnet: 3.0    # ~$0.003/1K input
      claude-3-opus: 15.0       # ~$0.015/1K input
    openai:
      gpt-4o-mini: 0.15         # ~$0.00015/1K input
      gpt-4o: 2.5               # ~$0.0025/1K input
      gpt-5: 30.0               # ~$0.03/1K input (estimated)

  # Default allocation for new workers (per billing period)
  default_worker_budget: 10000

  # Billing period
  period: monthly  # monthly | weekly | daily
```

## Schema Design

### Entity Relationship Diagram

```
budget_pools
    └── pool_id (for org-level pool)

budget_allocations
    ├── worker_id → workers.id (who has budget)
    ├── source_worker_id → workers.id (who allocated it)
    └── pool_id → budget_pools.id (org pool for top-level)

budget_transactions
    ├── allocation_id → budget_allocations.id
    └── worker_id → workers.id

budget_balances (materialized view / trigger-maintained)
    └── allocation_id → budget_allocations.id
```

### SQL Schema

```sql
-- ===================
-- BUDGET TABLES
-- ===================

-- Organization budget pool (funded by billing/subscription)
CREATE TABLE IF NOT EXISTS budget_pools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    total_credits DECIMAL(15,2) NOT NULL DEFAULT 0,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Budget allocations (who has how much budget)
-- Implements the cascade: Board -> CEO -> Directors -> Managers -> Workers
CREATE TABLE IF NOT EXISTS budget_allocations (
    id TEXT PRIMARY KEY,

    -- Who owns this allocation
    worker_id TEXT NOT NULL,

    -- Where budget came from (NULL = from org pool, otherwise from manager)
    source_worker_id TEXT,
    pool_id TEXT,

    -- Budget amounts
    allocated_credits DECIMAL(15,2) NOT NULL,
    spent_credits DECIMAL(15,2) NOT NULL DEFAULT 0,
    reserved_credits DECIMAL(15,2) NOT NULL DEFAULT 0,  -- In-flight requests

    -- Period tracking
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,

    -- Allocation rules
    can_delegate BOOLEAN NOT NULL DEFAULT FALSE,  -- Can allocate to subordinates?
    delegation_limit DECIMAL(15,2),               -- Max delegatable per subordinate

    -- Timestamps
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (source_worker_id) REFERENCES workers(id) ON DELETE SET NULL,
    FOREIGN KEY (pool_id) REFERENCES budget_pools(id) ON DELETE CASCADE,

    -- Either from pool or from source_worker, not both
    CHECK (
        (source_worker_id IS NULL AND pool_id IS NOT NULL) OR
        (source_worker_id IS NOT NULL AND pool_id IS NULL)
    ),

    -- Can't spend more than allocated
    CHECK (spent_credits + reserved_credits <= allocated_credits)
);

CREATE INDEX idx_budget_allocations_worker ON budget_allocations(worker_id);
CREATE INDEX idx_budget_allocations_source ON budget_allocations(source_worker_id);
CREATE INDEX idx_budget_allocations_period ON budget_allocations(period_start, period_end);

-- Budget transactions (immutable ledger of all budget movements)
CREATE TABLE IF NOT EXISTS budget_transactions (
    id TEXT PRIMARY KEY,
    allocation_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,

    -- Transaction type
    type TEXT NOT NULL CHECK(type IN (
        'allocation',      -- Budget allocated to worker
        'spend',           -- Credits consumed by provider call
        'reserve',         -- Credits reserved for in-flight request
        'release',         -- Reserved credits released (request completed/failed)
        'transfer_out',    -- Delegated to subordinate
        'transfer_in',     -- Received from manager
        'adjustment',      -- Admin adjustment
        'refund'           -- Credits returned (provider error, etc.)
    )),

    -- Amount (positive for credits in, negative for credits out)
    amount DECIMAL(15,2) NOT NULL,

    -- Provider details (for spend transactions)
    provider TEXT,
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,

    -- Reference to what caused this transaction
    reference_type TEXT,  -- 'task', 'message', 'api_call'
    reference_id TEXT,

    -- Audit trail
    description TEXT,
    metadata TEXT,  -- JSON for extensibility

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (allocation_id) REFERENCES budget_allocations(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX idx_budget_transactions_allocation ON budget_transactions(allocation_id);
CREATE INDEX idx_budget_transactions_worker ON budget_transactions(worker_id);
CREATE INDEX idx_budget_transactions_type ON budget_transactions(type);
CREATE INDEX idx_budget_transactions_created ON budget_transactions(created_at);
CREATE INDEX idx_budget_transactions_provider ON budget_transactions(provider, model);

-- Materialized balance view (updated via triggers for performance)
CREATE TABLE IF NOT EXISTS budget_balances (
    allocation_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,

    -- Current balances (derived from transactions)
    allocated DECIMAL(15,2) NOT NULL,
    spent DECIMAL(15,2) NOT NULL,
    reserved DECIMAL(15,2) NOT NULL,
    available DECIMAL(15,2) NOT NULL,  -- allocated - spent - reserved
    delegated DECIMAL(15,2) NOT NULL,  -- transferred to subordinates

    -- Period info
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,

    -- Last update
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (allocation_id) REFERENCES budget_allocations(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);

CREATE INDEX idx_budget_balances_worker ON budget_balances(worker_id);
CREATE INDEX idx_budget_balances_available ON budget_balances(available);

-- ===================
-- TRIGGERS
-- ===================

-- Update budget_balances on transaction insert
CREATE TRIGGER IF NOT EXISTS update_budget_balance_on_transaction
AFTER INSERT ON budget_transactions
BEGIN
    UPDATE budget_balances
    SET
        spent = spent + CASE
            WHEN NEW.type = 'spend' THEN ABS(NEW.amount)
            WHEN NEW.type = 'refund' THEN -ABS(NEW.amount)
            ELSE 0
        END,
        reserved = reserved + CASE
            WHEN NEW.type = 'reserve' THEN ABS(NEW.amount)
            WHEN NEW.type = 'release' THEN -ABS(NEW.amount)
            ELSE 0
        END,
        delegated = delegated + CASE
            WHEN NEW.type = 'transfer_out' THEN ABS(NEW.amount)
            ELSE 0
        END,
        allocated = allocated + CASE
            WHEN NEW.type = 'allocation' THEN NEW.amount
            WHEN NEW.type = 'transfer_in' THEN NEW.amount
            WHEN NEW.type = 'adjustment' THEN NEW.amount
            ELSE 0
        END,
        available = allocated - spent - reserved - delegated,
        updated_at = CURRENT_TIMESTAMP
    WHERE allocation_id = NEW.allocation_id;
END;
```

## Allocation Cascade

### How Budget Flows Through the Hierarchy

```
Board (Human)
    │
    │ Subscription payment → budget_pools (org level)
    │
    ▼
CEO (worker_id: ceo-001)
    │
    │ Allocation from pool → budget_allocations (can_delegate: true)
    │
    ├──► Director of Engineering (dir-eng-001)
    │        │ Allocation from CEO → budget_allocations (can_delegate: true)
    │        │
    │        ├──► Engineering Manager (mgr-001)
    │        │        │ Allocation from Director
    │        │        │
    │        │        ├──► Senior Engineer (eng-001) - spends on API calls
    │        │        └──► Junior Engineer (eng-002) - spends on API calls
    │        │
    │        └──► Engineering Manager (mgr-002)
    │                 └──► ... more workers
    │
    └──► Director of Product (dir-prod-001)
             └──► ... product team hierarchy
```

### Allocation Rules

1. **Only managers can delegate**: Workers with `can_delegate=true` can allocate budget to subordinates
2. **Delegation limits**: `delegation_limit` caps how much can be given to any single subordinate
3. **Can't exceed available**: Total delegations cannot exceed allocator's available balance
4. **Hierarchical constraint**: Can only allocate to direct reports (manager_id relationship)

### Python Pseudocode for Allocation

```python
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Optional

@dataclass
class AllocationRequest:
    """Request to allocate budget to a worker."""
    target_worker_id: str
    amount: Decimal
    period_start: datetime
    period_end: datetime


class BudgetAllocationError(Exception):
    """Raised when allocation fails."""
    pass


class BudgetService:
    """Service for managing budget allocations."""

    def __init__(self, db: Database):
        self.db = db

    def allocate_from_pool(
        self,
        pool_id: str,
        worker_id: str,
        amount: Decimal,
        can_delegate: bool = False,
        delegation_limit: Optional[Decimal] = None,
    ) -> str:
        """Allocate budget from org pool to top-level worker (CEO).

        Args:
            pool_id: Budget pool ID
            worker_id: Target worker (typically CEO)
            amount: Credits to allocate
            can_delegate: Whether worker can sub-allocate
            delegation_limit: Max per-subordinate if delegating

        Returns:
            Allocation ID

        Raises:
            BudgetAllocationError: If pool insufficient
        """
        with self.db.transaction() as tx:
            # Verify pool has sufficient funds
            pool = self._get_pool(pool_id)
            allocated_total = self._get_pool_allocated(pool_id)

            if pool.total_credits - allocated_total < amount:
                raise BudgetAllocationError(
                    f"Insufficient pool funds: {pool.total_credits - allocated_total} < {amount}"
                )

            # Create allocation
            allocation_id = generate_id("alloc")
            tx.execute("""
                INSERT INTO budget_allocations
                (id, worker_id, pool_id, allocated_credits, period_start, period_end,
                 can_delegate, delegation_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (allocation_id, worker_id, pool_id, amount,
                  pool.period_start, pool.period_end, can_delegate, delegation_limit))

            # Initialize balance record
            tx.execute("""
                INSERT INTO budget_balances
                (allocation_id, worker_id, allocated, spent, reserved, available,
                 delegated, period_start, period_end)
                VALUES (?, ?, ?, 0, 0, ?, 0, ?, ?)
            """, (allocation_id, worker_id, amount, amount,
                  pool.period_start, pool.period_end))

            # Record transaction
            self._record_transaction(
                tx, allocation_id, worker_id, 'allocation', amount,
                description=f"Initial allocation from pool {pool_id}"
            )

            return allocation_id

    def delegate_budget(
        self,
        source_worker_id: str,
        target_worker_id: str,
        amount: Decimal,
    ) -> str:
        """Delegate budget from manager to subordinate.

        Implements the cascade: manager -> direct report.

        Args:
            source_worker_id: Manager delegating budget
            target_worker_id: Subordinate receiving budget
            amount: Credits to delegate

        Returns:
            New allocation ID for target

        Raises:
            BudgetAllocationError: If delegation not allowed or insufficient
        """
        with self.db.transaction() as tx:
            # Verify hierarchy: target must report to source
            target = self._get_worker(target_worker_id)
            if target.manager_id != source_worker_id:
                raise BudgetAllocationError(
                    f"Worker {target_worker_id} does not report to {source_worker_id}"
                )

            # Get source allocation
            source_alloc = self._get_current_allocation(source_worker_id)
            if not source_alloc.can_delegate:
                raise BudgetAllocationError(
                    f"Worker {source_worker_id} cannot delegate budget"
                )

            # Check delegation limit
            if source_alloc.delegation_limit and amount > source_alloc.delegation_limit:
                raise BudgetAllocationError(
                    f"Amount {amount} exceeds delegation limit {source_alloc.delegation_limit}"
                )

            # Check available balance
            source_balance = self._get_balance(source_alloc.id)
            if source_balance.available < amount:
                raise BudgetAllocationError(
                    f"Insufficient available budget: {source_balance.available} < {amount}"
                )

            # Determine if target can also delegate (managers only)
            target_can_delegate = self._is_manager(target_worker_id)

            # Create target allocation
            allocation_id = generate_id("alloc")
            tx.execute("""
                INSERT INTO budget_allocations
                (id, worker_id, source_worker_id, allocated_credits,
                 period_start, period_end, can_delegate, delegation_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (allocation_id, target_worker_id, source_worker_id, amount,
                  source_alloc.period_start, source_alloc.period_end,
                  target_can_delegate, source_alloc.delegation_limit))

            # Initialize target balance
            tx.execute("""
                INSERT INTO budget_balances
                (allocation_id, worker_id, allocated, spent, reserved, available,
                 delegated, period_start, period_end)
                VALUES (?, ?, ?, 0, 0, ?, 0, ?, ?)
            """, (allocation_id, target_worker_id, amount, amount,
                  source_alloc.period_start, source_alloc.period_end))

            # Record transfer out from source
            self._record_transaction(
                tx, source_alloc.id, source_worker_id, 'transfer_out', -amount,
                description=f"Delegated to {target_worker_id}"
            )

            # Record transfer in to target
            self._record_transaction(
                tx, allocation_id, target_worker_id, 'transfer_in', amount,
                description=f"Received from {source_worker_id}"
            )

            return allocation_id

    def _is_manager(self, worker_id: str) -> bool:
        """Check if worker has direct reports."""
        row = self.db.fetchone(
            "SELECT 1 FROM workers WHERE manager_id = ? LIMIT 1",
            (worker_id,)
        )
        return row is not None
```

## Spend Tracking

### When Provider Calls Record Spend

Every LLM API call follows this flow:

```
Worker makes request
       │
       ▼
┌─────────────────────────────────────────┐
│ 1. RESERVE: Estimate cost, reserve credits │
│    - Estimate tokens based on input length │
│    - Reserve credits for worst-case output │
│    - FAIL if insufficient available         │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 2. EXECUTE: Make provider API call        │
│    - Call Anthropic/OpenAI/etc.           │
│    - Record actual token counts           │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 3. SETTLE: Release reservation, record spend │
│    - Calculate actual cost from tokens     │
│    - Release reserved credits              │
│    - Record actual spend                   │
│    - Return excess to available            │
└─────────────────────────────────────────┘
```

### Python Pseudocode for Spend Tracking

```python
from contextlib import contextmanager
from decimal import Decimal

class InsufficientBudgetError(Exception):
    """Raised when worker lacks budget for request."""
    pass


class BudgetEnforcer:
    """Enforces budget limits on provider calls."""

    def __init__(self, db: Database, config: BudgetConfig):
        self.db = db
        self.config = config

    def estimate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        max_output_tokens: int,
    ) -> Decimal:
        """Estimate credits needed for a request.

        Args:
            provider: Provider name (anthropic, openai)
            model: Model ID
            input_tokens: Estimated input tokens
            max_output_tokens: Maximum output tokens

        Returns:
            Estimated credits (includes safety margin)
        """
        rate = self.config.get_rate(provider, model)

        # Input cost
        input_cost = (input_tokens / 1000) * rate

        # Output cost (typically 3-5x input rate)
        output_multiplier = self.config.get_output_multiplier(provider, model)
        output_cost = (max_output_tokens / 1000) * rate * output_multiplier

        # Add 10% safety margin
        total = (input_cost + output_cost) * Decimal("1.1")

        return total.quantize(Decimal("0.01"))

    def calculate_actual_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """Calculate actual credits consumed.

        Args:
            provider: Provider name
            model: Model ID
            input_tokens: Actual input tokens
            output_tokens: Actual output tokens

        Returns:
            Actual credits consumed
        """
        rate = self.config.get_rate(provider, model)
        output_multiplier = self.config.get_output_multiplier(provider, model)

        input_cost = (input_tokens / 1000) * rate
        output_cost = (output_tokens / 1000) * rate * output_multiplier

        return (input_cost + output_cost).quantize(Decimal("0.01"))

    @contextmanager
    def budget_context(
        self,
        worker_id: str,
        provider: str,
        model: str,
        estimated_input_tokens: int,
        max_output_tokens: int,
        reference_type: str = None,
        reference_id: str = None,
    ):
        """Context manager for budget-controlled provider calls.

        Usage:
            with enforcer.budget_context(worker_id, "anthropic", "claude-3-5-sonnet",
                                         1000, 4096) as budget_ctx:
                result = provider.complete(messages)
                budget_ctx.set_actual_tokens(
                    result.usage["input_tokens"],
                    result.usage["output_tokens"]
                )

        Args:
            worker_id: Worker making the call
            provider: Provider name
            model: Model ID
            estimated_input_tokens: Estimated input size
            max_output_tokens: Max output tokens
            reference_type: Optional reference type (task, message)
            reference_id: Optional reference ID

        Yields:
            BudgetContext for recording actual usage

        Raises:
            InsufficientBudgetError: If worker lacks budget
        """
        # Get allocation
        allocation = self._get_current_allocation(worker_id)
        if not allocation:
            raise InsufficientBudgetError(f"No budget allocation for worker {worker_id}")

        # Estimate and reserve
        estimated_cost = self.estimate_cost(
            provider, model, estimated_input_tokens, max_output_tokens
        )

        balance = self._get_balance(allocation.id)
        if balance.available < estimated_cost:
            raise InsufficientBudgetError(
                f"Insufficient budget: need {estimated_cost}, have {balance.available}"
            )

        # Reserve credits
        reserve_tx_id = self._record_transaction(
            allocation.id, worker_id, 'reserve', estimated_cost,
            provider=provider, model=model,
            description=f"Reserved for {provider}/{model} call"
        )

        # Create context for tracking actual usage
        ctx = BudgetContext(
            allocation_id=allocation.id,
            worker_id=worker_id,
            reserve_tx_id=reserve_tx_id,
            reserved_amount=estimated_cost,
            provider=provider,
            model=model,
            reference_type=reference_type,
            reference_id=reference_id,
        )

        try:
            yield ctx

            # Settle: release reservation, record actual spend
            actual_cost = self.calculate_actual_cost(
                provider, model,
                ctx.actual_input_tokens,
                ctx.actual_output_tokens
            )

            # Release reservation
            self._record_transaction(
                allocation.id, worker_id, 'release', estimated_cost,
                description="Released reservation"
            )

            # Record actual spend
            self._record_transaction(
                allocation.id, worker_id, 'spend', -actual_cost,
                provider=provider, model=model,
                input_tokens=ctx.actual_input_tokens,
                output_tokens=ctx.actual_output_tokens,
                reference_type=reference_type,
                reference_id=reference_id,
                description=f"API call to {provider}/{model}"
            )

        except Exception as e:
            # On error, release reservation without spending
            self._record_transaction(
                allocation.id, worker_id, 'release', estimated_cost,
                description=f"Released due to error: {str(e)}"
            )
            raise


@dataclass
class BudgetContext:
    """Context for tracking actual API usage."""
    allocation_id: str
    worker_id: str
    reserve_tx_id: str
    reserved_amount: Decimal
    provider: str
    model: str
    reference_type: Optional[str]
    reference_id: Optional[str]
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0

    def set_actual_tokens(self, input_tokens: int, output_tokens: int):
        """Record actual token usage from API response."""
        self.actual_input_tokens = input_tokens
        self.actual_output_tokens = output_tokens
```

## Enforcement Points

### Where Budget Checks Happen

```
┌──────────────────────────────────────────────────────────────────┐
│ Enforcement Point 1: BEFORE PROVIDER SELECTION                    │
│                                                                   │
│ When: Worker requests model via ProviderRegistry.select_for_worker│
│ What: Check worker has ANY budget allocation                      │
│ Why:  Fail fast before expensive operations                       │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ Enforcement Point 2: BEFORE API CALL (Primary)                    │
│                                                                   │
│ When: BudgetEnforcer.budget_context() entry                       │
│ What: Estimate cost, verify available >= estimated, reserve       │
│ Why:  Prevent calls that would exceed budget                      │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ Enforcement Point 3: AFTER API CALL                               │
│                                                                   │
│ When: BudgetEnforcer.budget_context() exit                        │
│ What: Calculate actual cost, release excess reservation, record   │
│ Why:  Accurate spend tracking, return unused credits              │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ Enforcement Point 4: DELEGATION ATTEMPTS                          │
│                                                                   │
│ When: BudgetService.delegate_budget()                             │
│ What: Verify can_delegate, hierarchy, limits, available           │
│ Why:  Prevent unauthorized or excess delegations                  │
└──────────────────────────────────────────────────────────────────┘
```

### Integration with Provider Interface

```python
# In cli/core/provider.py - extend ProviderRegistry

class ProviderRegistry:
    def __init__(self, budget_enforcer: Optional[BudgetEnforcer] = None):
        self._providers: dict[str, Provider] = {}
        self._default_provider: Optional[str] = None
        self._budget_enforcer = budget_enforcer

    def complete_with_budget(
        self,
        worker_id: str,
        messages: list[Message],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        reference_type: str = None,
        reference_id: str = None,
    ) -> CompletionResult:
        """Make provider call with budget enforcement.

        This is the primary method workers should use for API calls.

        Args:
            worker_id: Worker making the call
            messages: Conversation messages
            provider: Optional preferred provider
            model: Optional specific model
            max_tokens: Maximum output tokens
            reference_type: What triggered this call (task, message)
            reference_id: ID of triggering entity

        Returns:
            CompletionResult from provider

        Raises:
            InsufficientBudgetError: If worker lacks budget
            ValueError: If no suitable provider/model
        """
        # Select provider and model if not specified
        if not provider or not model:
            worker = self._get_worker(worker_id)
            selected_provider, model_info = self.select_for_worker(
                worker.cost, worker.skills, provider
            )
            provider = selected_provider.name
            model = model_info.id
        else:
            selected_provider = self.get(provider)

        # Estimate input tokens (rough heuristic)
        estimated_input = sum(len(m.content) // 4 for m in messages)

        # Budget-controlled call
        if self._budget_enforcer:
            with self._budget_enforcer.budget_context(
                worker_id, provider, model,
                estimated_input, max_tokens,
                reference_type, reference_id
            ) as ctx:
                result = selected_provider.complete(
                    messages, model=model, max_tokens=max_tokens
                )
                ctx.set_actual_tokens(
                    result.usage.get("input_tokens", 0),
                    result.usage.get("output_tokens", 0)
                )
                return result
        else:
            # No budget enforcement (development mode)
            return selected_provider.complete(
                messages, model=model, max_tokens=max_tokens
            )
```

## CLI Commands

### Budget Visibility Commands

```bash
# Organization-level budget overview
$ qn org budget
Budget Pool: January 2026
  Total Credits: 1,000,000
  Allocated:     850,000 (85.0%)
  Spent:         423,150 (42.3%)
  Available:     576,850

Top Spenders (this period):
  1. eng-senior-001 (Sarah): 45,230 credits
  2. eng-lead-001 (Mike):    38,920 credits
  3. dir-eng-001 (Alice):    31,500 credits

# Worker-specific budget
$ qn org budget --worker eng-senior-001
Worker: eng-senior-001 (Sarah Chen)
Role: Senior Engineer
Manager: eng-lead-001 (Mike)

Current Allocation:
  Allocated: 75,000 credits
  Spent:     45,230 credits (60.3%)
  Reserved:  1,200 credits
  Available: 28,570 credits

Recent Transactions:
  2026-01-21 14:32  spend     -850 cr  anthropic/claude-3-5-sonnet (task-abc123)
  2026-01-21 14:28  spend     -420 cr  anthropic/claude-3-5-sonnet (task-abc123)
  2026-01-21 13:15  spend   -1,200 cr  anthropic/claude-3-5-sonnet (task-xyz789)
  ...

# Hierarchy budget view (for managers)
$ qn org budget --tree
CEO (ceo-001)
  Allocated: 500,000 | Spent: 125,000 | Delegated: 300,000
  │
  ├── Director of Engineering (dir-eng-001)
  │     Allocated: 200,000 | Spent: 31,500 | Delegated: 150,000
  │     │
  │     ├── Engineering Manager (mgr-eng-001)
  │     │     Allocated: 100,000 | Spent: 12,300 | Delegated: 75,000
  │     │     │
  │     │     ├── Senior Engineer (eng-senior-001): 45,230 spent
  │     │     └── Junior Engineer (eng-junior-001): 8,450 spent
  │     │
  │     └── Engineering Manager (mgr-eng-002)
  │           Allocated: 50,000 | Spent: 8,200 | Delegated: 35,000
  │           └── ...
  │
  └── Director of Product (dir-prod-001)
        Allocated: 100,000 | Spent: 28,400 | Delegated: 60,000
        └── ...

# Allocate budget (as manager)
$ qn org budget allocate --to eng-junior-002 --amount 25000
Allocated 25,000 credits to eng-junior-002 (Jane Doe)
Your remaining available: 52,300 credits

# View transaction history
$ qn org budget transactions --worker eng-senior-001 --since 2026-01-20
Date                 Type       Amount    Provider/Model              Reference
2026-01-21 14:32:15  spend      -850 cr   anthropic/claude-3-5-sonnet task-abc123
2026-01-21 14:28:42  spend      -420 cr   anthropic/claude-3-5-sonnet task-abc123
2026-01-21 13:15:08  spend    -1,200 cr   anthropic/claude-3-5-sonnet task-xyz789
2026-01-20 16:45:33  spend      -680 cr   anthropic/claude-3-haiku    task-def456
2026-01-20 09:00:00  allocation +75,000 cr -                          period-start
```

### Worker-Side Budget Command

```bash
# Workers check their own budget
$ bd budget
Your Budget (eng-senior-001):
  Allocated: 75,000 credits
  Spent:     45,230 credits (60.3%)
  Available: 28,570 credits

Period: 2026-01-01 to 2026-01-31 (10 days remaining)
Daily average spend: 2,153 credits
Projected end-of-period: 66,760 credits (under budget)

# Detailed spend breakdown
$ bd budget --breakdown
Spend by Model:
  claude-3-5-sonnet: 38,450 credits (85.0%)
  claude-3-haiku:     6,780 credits (15.0%)

Spend by Task Type:
  coding:     32,100 credits (71.0%)
  reasoning:  10,200 credits (22.5%)
  research:    2,930 credits  (6.5%)
```

## Configuration

### Budget Config in org config.yaml

```yaml
budget:
  # Base exchange rate
  credits_per_dollar: 1000

  # Provider-specific rates (credits per 1K tokens)
  # These map real provider pricing to internal credits
  provider_rates:
    anthropic:
      claude-3-haiku-20240307:
        input: 0.25
        output: 1.25
      claude-3-5-sonnet-20241022:
        input: 3.0
        output: 15.0
      claude-3-opus-20240229:
        input: 15.0
        output: 75.0
    openai:
      gpt-4o-mini:
        input: 0.15
        output: 0.60
      gpt-4o:
        input: 2.5
        output: 10.0
      gpt-5:
        input: 30.0
        output: 60.0

  # Default allocations by role
  default_allocations:
    ceo: 500000
    director: 200000
    manager: 100000
    lead: 75000
    senior_engineer: 75000
    engineer: 50000
    junior_engineer: 25000
    researcher: 60000
    analyst: 40000

  # Delegation rules
  delegation:
    # Who can delegate
    roles_can_delegate:
      - ceo
      - director
      - manager
      - lead

    # Max percentage of own budget delegatable to single subordinate
    max_delegation_percentage: 50

  # Enforcement settings
  enforcement:
    # Enable/disable enforcement (false for development)
    enabled: true

    # Warning threshold (percentage of allocation)
    warning_threshold: 80

    # Hard stop threshold (percentage)
    hard_stop_threshold: 100

    # Allow grace period overage (emergency work)
    grace_overage_percentage: 10

  # Billing period
  period:
    type: monthly  # monthly | weekly | daily
    rollover: false  # Unused credits roll to next period?
```

## Key Design Decisions

1. **Credits over tokens/dollars**: Provider-agnostic internal accounting with configurable exchange rates

2. **Immutable transaction ledger**: All budget changes recorded as transactions for auditability

3. **Materialized balances**: `budget_balances` table maintained by triggers for fast queries

4. **Reserve-then-spend pattern**: Prevent race conditions and overspend with pre-call reservation

5. **Hierarchical delegation**: Matches org-chart, managers allocate to direct reports only

6. **Config-driven rates**: All pricing in config, no hardcoded values (per "No Magic Values")

7. **Graceful degradation**: Enforcement can be disabled for development

## Implementation Order

1. Add budget tables to `cli/core/db.py` schema
2. Add budget config types to shared config
3. Implement `BudgetService` for allocations
4. Implement `BudgetEnforcer` for spend tracking
5. Integrate with `ProviderRegistry.complete_with_budget()`
6. Add CLI commands (`qn org budget`, `bd budget`)
7. Add triggers for balance maintenance
8. Add tests for allocation cascade and spend tracking

## Relationships to Other Systems

```
billing (Django backend)
    │
    │ Stripe subscription → credits added to budget_pools
    │
    ▼
budget_pools (CLI SQLite)
    │
    │ Pool allocation → CEO budget
    │
    ▼
budget_allocations (CLI SQLite)
    │
    │ Cascade to workers via delegation
    │
    ▼
workers (CLI SQLite)
    │
    │ Worker makes provider call
    │
    ▼
providers (CLI)
    │
    │ BudgetEnforcer validates, reserves, tracks spend
    │
    ▼
budget_transactions (CLI SQLite)
```
