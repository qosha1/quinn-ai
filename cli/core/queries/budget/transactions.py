"""Budget transaction queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...db import Database
from ..common import generate_id


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


def _row_to_transaction(row: dict) -> BudgetTransaction:
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
    return _row_to_transaction(row)


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
    return [_row_to_transaction(row) for row in rows]


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
    return [_row_to_transaction(row) for row in rows]


__all__ = [
    "BudgetTransaction",
    "create_budget_transaction",
    "get_budget_transaction",
    "get_transactions_by_allocation",
    "get_transactions_by_worker",
]
