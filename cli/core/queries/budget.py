"""Budget pool, allocation, transaction, and balance queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..db import Database
from .common import generate_id

@dataclass
class BudgetPool:
    """Organization budget pool."""
    id: str
    name: str
    total_credits: float
    period_start: datetime
    period_end: datetime
    created_at: datetime
    updated_at: datetime


@dataclass
class BudgetAllocation:
    """Budget allocation for a worker."""
    id: str
    worker_id: str
    source_worker_id: Optional[str]
    pool_id: Optional[str]
    allocated_credits: float
    spent_credits: float
    reserved_credits: float
    period_start: datetime
    period_end: datetime
    can_delegate: bool
    delegation_limit: Optional[float]
    created_at: datetime
    updated_at: datetime


@dataclass
class BudgetTransaction:
    """Budget transaction record."""
    id: str
    allocation_id: str
    worker_id: str
    type: str
    amount: float
    provider: Optional[str]
    model: Optional[str]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    reference_type: Optional[str]
    reference_id: Optional[str]
    description: Optional[str]
    metadata: Optional[str]
    created_at: datetime


@dataclass
class BudgetBalance:
    """Materialized budget balance."""
    allocation_id: str
    worker_id: str
    allocated: float
    spent: float
    reserved: float
    available: float
    delegated: float
    period_start: datetime
    period_end: datetime
    updated_at: datetime



def create_budget_pool(
    db: Database,
    name: str,
    total_credits: float,
    period_start: datetime,
    period_end: datetime,
    pool_id: Optional[str] = None,
) -> BudgetPool:
    """Create a new budget pool.

    Args:
        db: Database instance
        name: Pool name
        total_credits: Total credits in pool (must be positive)
        period_start: Period start datetime
        period_end: Period end datetime
        pool_id: Optional custom ID

    Returns:
        Created BudgetPool

    Raises:
        ValueError: If total_credits is not positive
    """
    if total_credits <= 0:
        raise ValueError(f"Total credits must be positive, got {total_credits:.2f}")

    if pool_id is None:
        pool_id = generate_id("pool")

    now = datetime.now()
    db.execute(
        """INSERT INTO budget_pools
           (id, name, total_credits, period_start, period_end, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (pool_id, name, total_credits, period_start, period_end, now, now)
    )
    db.connection.commit()

    return BudgetPool(
        id=pool_id,
        name=name,
        total_credits=total_credits,
        period_start=period_start,
        period_end=period_end,
        created_at=now,
        updated_at=now,
    )


def get_budget_pool(db: Database, pool_id: str) -> Optional[BudgetPool]:
    """Get a budget pool by ID.

    Args:
        db: Database instance
        pool_id: Pool ID

    Returns:
        BudgetPool or None
    """
    row = db.fetchone("SELECT * FROM budget_pools WHERE id = ?", (pool_id,))
    if not row:
        return None

    return BudgetPool(
        id=row["id"],
        name=row["name"],
        total_credits=float(row["total_credits"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_all_budget_pools(db: Database) -> list[BudgetPool]:
    """Get all budget pools.

    Args:
        db: Database instance

    Returns:
        List of all budget pools
    """
    rows = db.fetchall("SELECT * FROM budget_pools ORDER BY created_at DESC")
    return [
        BudgetPool(
            id=row["id"],
            name=row["name"],
            total_credits=float(row["total_credits"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def update_budget_pool(
    db: Database,
    pool_id: str,
    total_credits: Optional[float] = None,
    name: Optional[str] = None,
) -> None:
    """Update a budget pool.

    Args:
        db: Database instance
        pool_id: Pool ID
        total_credits: Optional new total credits
        name: Optional new name
    """
    now = datetime.now()
    updates = ["updated_at = ?"]
    params: list = [now]

    if total_credits is not None:
        updates.append("total_credits = ?")
        params.append(total_credits)
    if name is not None:
        updates.append("name = ?")
        params.append(name)

    params.append(pool_id)
    db.execute(
        f"UPDATE budget_pools SET {', '.join(updates)} WHERE id = ?",
        tuple(params)
    )
    db.connection.commit()


def delete_budget_pool(db: Database, pool_id: str) -> None:
    """Delete a budget pool.

    Args:
        db: Database instance
        pool_id: Pool ID to delete
    """
    db.execute("DELETE FROM budget_pools WHERE id = ?", (pool_id,))
    db.connection.commit()



def create_budget_allocation(
    db: Database,
    worker_id: str,
    allocated_credits: float,
    period_start: datetime,
    period_end: datetime,
    source_worker_id: Optional[str] = None,
    pool_id: Optional[str] = None,
    can_delegate: bool = False,
    delegation_limit: Optional[float] = None,
    allocation_id: Optional[str] = None,
) -> BudgetAllocation:
    """Create a budget allocation.

    Either source_worker_id or pool_id must be provided, but not both.

    Args:
        db: Database instance
        worker_id: Worker receiving the allocation
        allocated_credits: Credits being allocated (must be positive)
        period_start: Period start datetime
        period_end: Period end datetime
        source_worker_id: Manager delegating budget (mutually exclusive with pool_id)
        pool_id: Pool providing budget (mutually exclusive with source_worker_id)
        can_delegate: Whether worker can delegate to subordinates
        delegation_limit: Max credits delegatable to single subordinate (must be positive if set)
        allocation_id: Optional custom ID

    Returns:
        Created BudgetAllocation

    Raises:
        ValueError: If allocated_credits is not positive, or if delegation_limit is set but not positive
    """
    if allocated_credits <= 0:
        raise ValueError(f"Allocated credits must be positive, got {allocated_credits:.2f}")

    if delegation_limit is not None and delegation_limit <= 0:
        raise ValueError(f"Delegation limit must be positive, got {delegation_limit:.2f}")

    if allocation_id is None:
        allocation_id = generate_id("alloc")

    now = datetime.now()
    db.execute(
        """INSERT INTO budget_allocations
           (id, worker_id, source_worker_id, pool_id, allocated_credits,
            spent_credits, reserved_credits, period_start, period_end,
            can_delegate, delegation_limit, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?)""",
        (allocation_id, worker_id, source_worker_id, pool_id, allocated_credits,
         period_start, period_end, can_delegate, delegation_limit, now, now)
    )
    db.connection.commit()

    return BudgetAllocation(
        id=allocation_id,
        worker_id=worker_id,
        source_worker_id=source_worker_id,
        pool_id=pool_id,
        allocated_credits=allocated_credits,
        spent_credits=0.0,
        reserved_credits=0.0,
        period_start=period_start,
        period_end=period_end,
        can_delegate=can_delegate,
        delegation_limit=delegation_limit,
        created_at=now,
        updated_at=now,
    )


def get_budget_allocation(db: Database, allocation_id: str) -> Optional[BudgetAllocation]:
    """Get a budget allocation by ID.

    Args:
        db: Database instance
        allocation_id: Allocation ID

    Returns:
        BudgetAllocation or None
    """
    row = db.fetchone("SELECT * FROM budget_allocations WHERE id = ?", (allocation_id,))
    if not row:
        return None

    return BudgetAllocation(
        id=row["id"],
        worker_id=row["worker_id"],
        source_worker_id=row["source_worker_id"],
        pool_id=row["pool_id"],
        allocated_credits=float(row["allocated_credits"]),
        spent_credits=float(row["spent_credits"]),
        reserved_credits=float(row["reserved_credits"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        can_delegate=bool(row["can_delegate"]),
        delegation_limit=float(row["delegation_limit"]) if row["delegation_limit"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_worker_allocations(db: Database, worker_id: str) -> list[BudgetAllocation]:
    """Get all allocations for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of allocations for the worker
    """
    rows = db.fetchall(
        "SELECT * FROM budget_allocations WHERE worker_id = ? ORDER BY period_start DESC",
        (worker_id,)
    )
    return [
        BudgetAllocation(
            id=row["id"],
            worker_id=row["worker_id"],
            source_worker_id=row["source_worker_id"],
            pool_id=row["pool_id"],
            allocated_credits=float(row["allocated_credits"]),
            spent_credits=float(row["spent_credits"]),
            reserved_credits=float(row["reserved_credits"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            can_delegate=bool(row["can_delegate"]),
            delegation_limit=float(row["delegation_limit"]) if row["delegation_limit"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def get_current_allocation(
    db: Database,
    worker_id: str,
    as_of: Optional[datetime] = None,
) -> Optional[BudgetAllocation]:
    """Get the current allocation for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        as_of: Optional datetime to check (defaults to now)

    Returns:
        Current BudgetAllocation or None
    """
    if as_of is None:
        as_of = datetime.now()

    row = db.fetchone(
        """SELECT * FROM budget_allocations
           WHERE worker_id = ? AND period_start <= ? AND period_end >= ?
           ORDER BY period_start DESC LIMIT 1""",
        (worker_id, as_of, as_of)
    )
    if not row:
        return None

    return BudgetAllocation(
        id=row["id"],
        worker_id=row["worker_id"],
        source_worker_id=row["source_worker_id"],
        pool_id=row["pool_id"],
        allocated_credits=float(row["allocated_credits"]),
        spent_credits=float(row["spent_credits"]),
        reserved_credits=float(row["reserved_credits"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        can_delegate=bool(row["can_delegate"]),
        delegation_limit=float(row["delegation_limit"]) if row["delegation_limit"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_allocations_by_pool(db: Database, pool_id: str) -> list[BudgetAllocation]:
    """Get all allocations from a pool.

    Args:
        db: Database instance
        pool_id: Pool ID

    Returns:
        List of allocations from the pool
    """
    rows = db.fetchall(
        "SELECT * FROM budget_allocations WHERE pool_id = ?",
        (pool_id,)
    )
    return [
        BudgetAllocation(
            id=row["id"],
            worker_id=row["worker_id"],
            source_worker_id=row["source_worker_id"],
            pool_id=row["pool_id"],
            allocated_credits=float(row["allocated_credits"]),
            spent_credits=float(row["spent_credits"]),
            reserved_credits=float(row["reserved_credits"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            can_delegate=bool(row["can_delegate"]),
            delegation_limit=float(row["delegation_limit"]) if row["delegation_limit"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def update_allocation_spend(
    db: Database,
    allocation_id: str,
    spent_credits: float,
    reserved_credits: float,
) -> None:
    """Update spend and reserve amounts on an allocation.

    Args:
        db: Database instance
        allocation_id: Allocation ID
        spent_credits: New spent amount
        reserved_credits: New reserved amount
    """
    now = datetime.now()
    db.execute(
        """UPDATE budget_allocations
           SET spent_credits = ?, reserved_credits = ?, updated_at = ?
           WHERE id = ?""",
        (spent_credits, reserved_credits, now, allocation_id)
    )
    db.connection.commit()


def delete_budget_allocation(db: Database, allocation_id: str) -> None:
    """Delete a budget allocation.

    Args:
        db: Database instance
        allocation_id: Allocation ID to delete
    """
    db.execute("DELETE FROM budget_allocations WHERE id = ?", (allocation_id,))
    db.connection.commit()



def create_budget_transaction(
    db: Database,
    allocation_id: str,
    worker_id: str,
    transaction_type: str,
    amount: float,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[str] = None,
    transaction_id: Optional[str] = None,
) -> BudgetTransaction:
    """Create a budget transaction.

    Args:
        db: Database instance
        allocation_id: Allocation ID
        worker_id: Worker ID
        transaction_type: Type ('allocation', 'spend', 'reserve', etc.)
        amount: Transaction amount (positive in, negative out)
        provider: Optional provider name (for spend)
        model: Optional model name (for spend)
        input_tokens: Optional input token count
        output_tokens: Optional output token count
        reference_type: Optional reference type ('task', 'message')
        reference_id: Optional reference ID
        description: Optional description
        metadata: Optional JSON metadata
        transaction_id: Optional custom ID

    Returns:
        Created BudgetTransaction
    """
    if transaction_id is None:
        transaction_id = generate_id("txn")

    now = datetime.now()
    db.execute(
        """INSERT INTO budget_transactions
           (id, allocation_id, worker_id, type, amount, provider, model,
            input_tokens, output_tokens, reference_type, reference_id,
            description, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (transaction_id, allocation_id, worker_id, transaction_type, amount,
         provider, model, input_tokens, output_tokens, reference_type,
         reference_id, description, metadata, now)
    )
    db.connection.commit()

    return BudgetTransaction(
        id=transaction_id,
        allocation_id=allocation_id,
        worker_id=worker_id,
        type=transaction_type,
        amount=amount,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        metadata=metadata,
        created_at=now,
    )


def get_budget_transaction(db: Database, transaction_id: str) -> Optional[BudgetTransaction]:
    """Get a budget transaction by ID.

    Args:
        db: Database instance
        transaction_id: Transaction ID

    Returns:
        BudgetTransaction or None
    """
    row = db.fetchone("SELECT * FROM budget_transactions WHERE id = ?", (transaction_id,))
    if not row:
        return None

    return BudgetTransaction(
        id=row["id"],
        allocation_id=row["allocation_id"],
        worker_id=row["worker_id"],
        type=row["type"],
        amount=float(row["amount"]),
        provider=row["provider"],
        model=row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        reference_type=row["reference_type"],
        reference_id=row["reference_id"],
        description=row["description"],
        metadata=row["metadata"],
        created_at=row["created_at"],
    )


def get_transactions_by_allocation(
    db: Database,
    allocation_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[BudgetTransaction]:
    """Get transactions for an allocation.

    Args:
        db: Database instance
        allocation_id: Allocation ID
        limit: Max transactions to return
        offset: Offset for pagination

    Returns:
        List of transactions, newest first
    """
    rows = db.fetchall(
        """SELECT * FROM budget_transactions
           WHERE allocation_id = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (allocation_id, limit, offset)
    )
    return [
        BudgetTransaction(
            id=row["id"],
            allocation_id=row["allocation_id"],
            worker_id=row["worker_id"],
            type=row["type"],
            amount=float(row["amount"]),
            provider=row["provider"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reference_type=row["reference_type"],
            reference_id=row["reference_id"],
            description=row["description"],
            metadata=row["metadata"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_transactions_by_worker(
    db: Database,
    worker_id: str,
    transaction_type: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[BudgetTransaction]:
    """Get transactions for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        transaction_type: Optional filter by type
        since: Optional filter by time
        limit: Max transactions to return
        offset: Offset for pagination

    Returns:
        List of transactions, newest first
    """
    query = "SELECT * FROM budget_transactions WHERE worker_id = ?"
    params: list = [worker_id]

    if transaction_type:
        query += " AND type = ?"
        params.append(transaction_type)
    if since:
        query += " AND created_at >= ?"
        params.append(since)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.fetchall(query, tuple(params))
    return [
        BudgetTransaction(
            id=row["id"],
            allocation_id=row["allocation_id"],
            worker_id=row["worker_id"],
            type=row["type"],
            amount=float(row["amount"]),
            provider=row["provider"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            reference_type=row["reference_type"],
            reference_id=row["reference_id"],
            description=row["description"],
            metadata=row["metadata"],
            created_at=row["created_at"],
        )
        for row in rows
    ]



def create_budget_balance(
    db: Database,
    allocation_id: str,
    worker_id: str,
    allocated: float,
    period_start: datetime,
    period_end: datetime,
) -> BudgetBalance:
    """Create a budget balance record.

    Args:
        db: Database instance
        allocation_id: Allocation ID
        worker_id: Worker ID
        allocated: Initial allocated amount
        period_start: Period start
        period_end: Period end

    Returns:
        Created BudgetBalance
    """
    now = datetime.now()
    db.execute(
        """INSERT INTO budget_balances
           (allocation_id, worker_id, allocated, spent, reserved, available,
            delegated, period_start, period_end, updated_at)
           VALUES (?, ?, ?, 0, 0, ?, 0, ?, ?, ?)""",
        (allocation_id, worker_id, allocated, allocated, period_start, period_end, now)
    )
    db.connection.commit()

    return BudgetBalance(
        allocation_id=allocation_id,
        worker_id=worker_id,
        allocated=allocated,
        spent=0.0,
        reserved=0.0,
        available=allocated,
        delegated=0.0,
        period_start=period_start,
        period_end=period_end,
        updated_at=now,
    )


def get_budget_balance(db: Database, allocation_id: str) -> Optional[BudgetBalance]:
    """Get budget balance for an allocation.

    Args:
        db: Database instance
        allocation_id: Allocation ID

    Returns:
        BudgetBalance or None
    """
    row = db.fetchone("SELECT * FROM budget_balances WHERE allocation_id = ?", (allocation_id,))
    if not row:
        return None

    return BudgetBalance(
        allocation_id=row["allocation_id"],
        worker_id=row["worker_id"],
        allocated=float(row["allocated"]),
        spent=float(row["spent"]),
        reserved=float(row["reserved"]),
        available=float(row["available"]),
        delegated=float(row["delegated"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        updated_at=row["updated_at"],
    )


def get_worker_balance(
    db: Database,
    worker_id: str,
    as_of: Optional[datetime] = None,
) -> Optional[BudgetBalance]:
    """Get current budget balance for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        as_of: Optional datetime (defaults to now)

    Returns:
        Current BudgetBalance or None
    """
    if as_of is None:
        as_of = datetime.now()

    row = db.fetchone(
        """SELECT * FROM budget_balances
           WHERE worker_id = ? AND period_start <= ? AND period_end >= ?
           ORDER BY period_start DESC LIMIT 1""",
        (worker_id, as_of, as_of)
    )
    if not row:
        return None

    return BudgetBalance(
        allocation_id=row["allocation_id"],
        worker_id=row["worker_id"],
        allocated=float(row["allocated"]),
        spent=float(row["spent"]),
        reserved=float(row["reserved"]),
        available=float(row["available"]),
        delegated=float(row["delegated"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        updated_at=row["updated_at"],
    )


def get_all_worker_balances(db: Database) -> list[BudgetBalance]:
    """Get all current budget balances.

    Args:
        db: Database instance

    Returns:
        List of all budget balances
    """
    now = datetime.now()
    rows = db.fetchall(
        """SELECT * FROM budget_balances
           WHERE period_start <= ? AND period_end >= ?
           ORDER BY worker_id""",
        (now, now)
    )
    return [
        BudgetBalance(
            allocation_id=row["allocation_id"],
            worker_id=row["worker_id"],
            allocated=float(row["allocated"]),
            spent=float(row["spent"]),
            reserved=float(row["reserved"]),
            available=float(row["available"]),
            delegated=float(row["delegated"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def delete_budget_balance(db: Database, allocation_id: str) -> None:
    """Delete a budget balance.

    Args:
        db: Database instance
        allocation_id: Allocation ID
    """
    db.execute("DELETE FROM budget_balances WHERE allocation_id = ?", (allocation_id,))
    db.connection.commit()


def get_pool_allocated_total(db: Database, pool_id: str) -> float:
    """Get total allocated credits from a pool.

    Args:
        db: Database instance
        pool_id: Pool ID

    Returns:
        Total allocated credits
    """
    row = db.fetchone(
        "SELECT COALESCE(SUM(allocated_credits), 0) as total FROM budget_allocations WHERE pool_id = ?",
        (pool_id,)
    )
    return float(row["total"]) if row else 0.0


def is_worker_manager(db: Database, worker_id: str) -> bool:
    """Check if worker has any direct reports.

    Args:
        db: Database instance
        worker_id: Worker ID to check

    Returns:
        True if worker has direct reports
    """
    row = db.fetchone(
        "SELECT 1 FROM workers WHERE manager_id = ? LIMIT 1",
        (worker_id,)
    )
    return row is not None


def get_worker_delegation_authority(db: Database, worker_id: str) -> Optional[bool]:
    """Get whether worker can delegate budget.

    Args:
        db: Database instance
        worker_id: Worker ID to check

    Returns:
        True if worker can delegate, False if not, None if no allocation
    """
    row = db.fetchone(
        """SELECT can_delegate FROM budget_allocations
           WHERE worker_id = ? AND revoked_at IS NULL
           ORDER BY created_at DESC LIMIT 1""",
        (worker_id,)
    )
    if row:
        return bool(row["can_delegate"])
    return None


def get_worker_allocated_budget(db: Database, worker_id: str) -> float:
    """Get total allocated budget for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Allocated budget amount or 0.0 if no allocation
    """
    row = db.fetchone(
        "SELECT allocated FROM budget_allocations WHERE worker_id = ?",
        (worker_id,)
    )
    return float(row["allocated"]) if row else 0.0


__all__ = [
    "BudgetAllocation",
    "BudgetBalance",
    "BudgetPool",
    "BudgetTransaction",
    "create_budget_allocation",
    "create_budget_balance",
    "create_budget_pool",
    "create_budget_transaction",
    "delete_budget_allocation",
    "delete_budget_balance",
    "delete_budget_pool",
    "get_all_budget_pools",
    "get_all_worker_balances",
    "get_allocations_by_pool",
    "get_budget_allocation",
    "get_budget_balance",
    "get_budget_pool",
    "get_budget_transaction",
    "get_current_allocation",
    "get_pool_allocated_total",
    "get_transactions_by_allocation",
    "get_transactions_by_worker",
    "get_worker_allocations",
    "get_worker_allocated_budget",
    "get_worker_balance",
    "get_worker_delegation_authority",
    "is_worker_manager",
    "update_allocation_spend",
    "update_budget_pool",
]
