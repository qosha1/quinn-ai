"""Budget pool queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...db import Database
from ..common import generate_id


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


__all__ = [
    "BudgetPool",
    "create_budget_pool",
    "get_budget_pool",
    "get_all_budget_pools",
    "update_budget_pool",
    "delete_budget_pool",
]
