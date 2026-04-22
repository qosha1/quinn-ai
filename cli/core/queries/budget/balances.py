"""Budget balance queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...db import Database


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


def _row_to_balance(row: dict) -> BudgetBalance:
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
    return _row_to_balance(row)


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
    return _row_to_balance(row)


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
    return [_row_to_balance(row) for row in rows]


def delete_budget_balance(db: Database, allocation_id: str) -> None:
    """Delete a budget balance.

    Args:
        db: Database instance
        allocation_id: Allocation ID
    """
    db.execute("DELETE FROM budget_balances WHERE allocation_id = ?", (allocation_id,))
    db.connection.commit()


__all__ = [
    "BudgetBalance",
    "create_budget_balance",
    "get_budget_balance",
    "get_worker_balance",
    "get_all_worker_balances",
    "delete_budget_balance",
]
