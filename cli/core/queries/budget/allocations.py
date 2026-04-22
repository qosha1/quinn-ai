"""Budget allocation queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...db import Database
from ..common import generate_id


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


def _row_to_allocation(row: dict) -> BudgetAllocation:
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
    return _row_to_allocation(row)


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
    return [_row_to_allocation(row) for row in rows]


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
    return _row_to_allocation(row)


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
    return [_row_to_allocation(row) for row in rows]


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


__all__ = [
    "BudgetAllocation",
    "create_budget_allocation",
    "get_budget_allocation",
    "get_worker_allocations",
    "get_current_allocation",
    "get_allocations_by_pool",
    "update_allocation_spend",
    "delete_budget_allocation",
]
