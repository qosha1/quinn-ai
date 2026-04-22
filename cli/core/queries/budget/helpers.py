"""Shared budget helper queries."""

from typing import Optional

from ...db import Database


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
    "get_pool_allocated_total",
    "is_worker_manager",
    "get_worker_delegation_authority",
    "get_worker_allocated_budget",
]
