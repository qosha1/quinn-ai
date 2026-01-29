"""Delegation grant and audit queries."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..db import Database
from .common import generate_id

@dataclass
class DelegationGrant:
    """Delegation grant record.

    Represents a single delegation of hiring authority from one worker
    (delegator) to another (delegate).
    """
    id: str
    delegator_id: str
    delegate_id: str
    scope: str  # JSON-serialized HiringScope
    budget_amount: int
    granted_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    revoked_by: Optional[str]
    revoke_reason: Optional[str]
    granted_by_cli_user: Optional[str]
    metadata: Optional[str]  # JSON

    @property
    def is_active(self) -> bool:
        """Check if this delegation is currently active."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at < datetime.now():
            return False
        return True


@dataclass
class DelegationAuditRecord:
    """Delegation audit trail record.

    Immutable log of all delegation operations for compliance and debugging.
    """
    id: str
    event_type: str  # granted, revoked, expired, cascade_revoked, modified, terminated_revoked
    delegator_id: str
    delegate_id: str
    delegation_grant_id: Optional[str]
    scope_before: Optional[str]
    scope_after: Optional[str]
    budget_before: Optional[int]
    budget_after: Optional[int]
    performed_by: str
    performed_by_cli_user: Optional[str]
    reason: Optional[str]
    timestamp: datetime


@dataclass
class RevokeResult:
    """Result of delegation revocation operation."""
    revoked_grant_ids: list[str]
    cascade_count: int
    affected_workers: list[str]



def create_delegation_grant(
    db: Database,
    delegator_id: str,
    delegate_id: str,
    scope: str,
    budget: int,
    granted_by_cli_user: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    grant_id: Optional[str] = None,
) -> DelegationGrant:
    """Create a new delegation grant.

    Creates a record in delegation_grants table. The database trigger
    will automatically create an audit record.

    Args:
        db: Database instance
        delegator_id: Worker ID granting authority
        delegate_id: Worker ID receiving authority
        scope: JSON-serialized HiringScope
        budget: Budget amount to delegate
        granted_by_cli_user: Optional CLI user who initiated grant
        expires_at: Optional expiration timestamp
        grant_id: Optional custom ID

    Returns:
        Created DelegationGrant

    Raises:
        ValueError: If delegate already has active delegation
        sqlite3.IntegrityError: If workers don't exist or self-delegation
    """
    if grant_id is None:
        grant_id = generate_id("deleg")

    # Check for existing active delegation
    existing = get_delegation_grant(db, delegate_id)
    if existing is not None:
        raise ValueError(
            f"Worker '{delegate_id}' already has an active delegation "
            f"from '{existing.delegator_id}'"
        )

    now = datetime.now()
    db.execute(
        """INSERT INTO delegation_grants
           (id, delegator_id, delegate_id, scope, budget_amount,
            granted_at, expires_at, granted_by_cli_user)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (grant_id, delegator_id, delegate_id, scope, budget,
         now, expires_at, granted_by_cli_user)
    )
    db.connection.commit()

    return DelegationGrant(
        id=grant_id,
        delegator_id=delegator_id,
        delegate_id=delegate_id,
        scope=scope,
        budget_amount=budget,
        granted_at=now,
        expires_at=expires_at,
        revoked_at=None,
        revoked_by=None,
        revoke_reason=None,
        granted_by_cli_user=granted_by_cli_user,
        metadata=None,
    )


def get_delegation_grant(
    db: Database,
    delegate_id: str,
) -> Optional[DelegationGrant]:
    """Get active delegation grant for a delegate.

    Args:
        db: Database instance
        delegate_id: Worker ID to check

    Returns:
        Active DelegationGrant or None if no active delegation
    """
    row = db.fetchone(
        """SELECT * FROM delegation_grants
           WHERE delegate_id = ? AND revoked_at IS NULL""",
        (delegate_id,)
    )
    if not row:
        return None

    grant = DelegationGrant(
        id=row["id"],
        delegator_id=row["delegator_id"],
        delegate_id=row["delegate_id"],
        scope=row["scope"],
        budget_amount=row["budget_amount"],
        granted_at=row["granted_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        revoked_by=row["revoked_by"],
        revoke_reason=row["revoke_reason"],
        granted_by_cli_user=row["granted_by_cli_user"],
        metadata=row["metadata"],
    )

    # Check if expired (but not yet marked as revoked)
    if not grant.is_active:
        return None

    return grant


def get_delegation_grant_by_id(
    db: Database,
    grant_id: str,
) -> Optional[DelegationGrant]:
    """Get a delegation grant by ID (active or revoked).

    Args:
        db: Database instance
        grant_id: Delegation grant ID

    Returns:
        DelegationGrant or None
    """
    row = db.fetchone(
        "SELECT * FROM delegation_grants WHERE id = ?",
        (grant_id,)
    )
    if not row:
        return None

    return DelegationGrant(
        id=row["id"],
        delegator_id=row["delegator_id"],
        delegate_id=row["delegate_id"],
        scope=row["scope"],
        budget_amount=row["budget_amount"],
        granted_at=row["granted_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        revoked_by=row["revoked_by"],
        revoke_reason=row["revoke_reason"],
        granted_by_cli_user=row["granted_by_cli_user"],
        metadata=row["metadata"],
    )


def revoke_delegation_grant(
    db: Database,
    delegate_id: str,
    revoked_by: str,
    reason: Optional[str] = None,
    cascade: bool = False,
) -> RevokeResult:
    """Revoke delegation grant for a delegate.

    Args:
        db: Database instance
        delegate_id: Worker ID whose delegation to revoke
        revoked_by: Worker ID performing revocation
        reason: Optional human-readable reason
        cascade: If True, also revoke delegations granted by this delegate

    Returns:
        RevokeResult with details of revocation

    Raises:
        ValueError: If no active delegation found
    """
    # Find active delegation for this delegate
    grant = get_delegation_grant(db, delegate_id)
    if grant is None:
        raise ValueError(f"No active delegation found for worker '{delegate_id}'")

    now = datetime.now()
    revoked_ids = []
    affected_workers = []
    cascade_count = 0

    # If cascade, first revoke all sub-delegations recursively
    if cascade:
        sub_delegations = get_delegations_by_delegator(db, delegate_id)
        for sub_grant in sub_delegations:
            sub_result = revoke_delegation_grant(
                db=db,
                delegate_id=sub_grant.delegate_id,
                revoked_by=revoked_by,
                reason=f"cascade: parent delegation revoked",
                cascade=True,
            )
            revoked_ids.extend(sub_result.revoked_grant_ids)
            affected_workers.extend(sub_result.affected_workers)
            cascade_count += 1 + sub_result.cascade_count

    # Revoke the main delegation
    db.execute(
        """UPDATE delegation_grants
           SET revoked_at = ?, revoked_by = ?, revoke_reason = ?
           WHERE id = ?""",
        (now, revoked_by, reason, grant.id)
    )

    # Clear worker's delegated authority
    db.execute(
        """UPDATE workers
           SET hiring_authority_scope = NULL,
               delegated_budget = 0,
               delegated_by = NULL,
               delegation_expires_at = NULL,
               delegation_version = delegation_version + 1,
               updated_at = ?
           WHERE id = ?""",
        (now, delegate_id)
    )

    db.connection.commit()

    revoked_ids.append(grant.id)
    affected_workers.append(delegate_id)

    return RevokeResult(
        revoked_grant_ids=revoked_ids,
        cascade_count=cascade_count,
        affected_workers=affected_workers,
    )


def get_delegation_chain(
    db: Database,
    worker_id: str,
) -> list[DelegationGrant]:
    """Get complete delegation chain for a worker.

    Returns the chain from the worker up to the root (CEO),
    following the delegated_by relationships.

    Args:
        db: Database instance
        worker_id: Worker ID to trace

    Returns:
        List of DelegationGrants in chain order (worker -> ... -> root)
    """
    chain = []
    current_id = worker_id
    visited = set()

    while current_id is not None:
        # Prevent infinite loops
        if current_id in visited:
            break
        visited.add(current_id)

        grant = get_delegation_grant(db, current_id)
        if grant is None:
            break

        chain.append(grant)
        current_id = grant.delegator_id

    return chain


def check_delegation_cycle(
    db: Database,
    delegator_id: str,
    delegate_id: str,
) -> bool:
    """Check if delegation would create a circular reference.

    A cycle would occur if the proposed delegate (or any worker in their
    delegation subtree) could delegate back to the delegator.

    Args:
        db: Database instance
        delegator_id: Worker ID granting authority
        delegate_id: Worker ID receiving authority

    Returns:
        True if cycle would be created, False otherwise
    """
    # Check if delegate_id is in delegator's chain (would create A -> B -> ... -> A)
    chain = get_delegation_chain(db, delegator_id)
    chain_ids = {g.delegate_id for g in chain}
    chain_ids.add(delegator_id)

    # If delegate is already in the chain to delegator, this would create a cycle
    if delegate_id in chain_ids:
        return True

    # Also check if delegator appears in delegate's existing subtree
    # (would happen if delegate already has sub-delegations that include delegator)
    subtree = _get_delegation_subtree(db, delegate_id)
    if delegator_id in subtree:
        return True

    return False


def _get_delegation_subtree(db: Database, root_id: str) -> set[str]:
    """Get all worker IDs in the delegation subtree rooted at root_id.

    Args:
        db: Database instance
        root_id: Root worker ID

    Returns:
        Set of all worker IDs in the subtree (including root)
    """
    subtree = {root_id}
    to_visit = [root_id]

    while to_visit:
        current = to_visit.pop()
        delegations = get_delegations_by_delegator(db, current)
        for grant in delegations:
            if grant.delegate_id not in subtree:
                subtree.add(grant.delegate_id)
                to_visit.append(grant.delegate_id)

    return subtree


def get_delegations_by_delegator(
    db: Database,
    delegator_id: str,
    include_revoked: bool = False,
) -> list[DelegationGrant]:
    """Get delegations granted by a delegator.

    Args:
        db: Database instance
        delegator_id: Worker ID who granted delegations
        include_revoked: Include revoked delegations

    Returns:
        List of DelegationGrants
    """
    if include_revoked:
        query = "SELECT * FROM delegation_grants WHERE delegator_id = ? ORDER BY granted_at"
        rows = db.fetchall(query, (delegator_id,))
    else:
        query = """SELECT * FROM delegation_grants
                   WHERE delegator_id = ? AND revoked_at IS NULL
                   ORDER BY granted_at"""
        rows = db.fetchall(query, (delegator_id,))

    return [
        DelegationGrant(
            id=row["id"],
            delegator_id=row["delegator_id"],
            delegate_id=row["delegate_id"],
            scope=row["scope"],
            budget_amount=row["budget_amount"],
            granted_at=row["granted_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            revoked_by=row["revoked_by"],
            revoke_reason=row["revoke_reason"],
            granted_by_cli_user=row["granted_by_cli_user"],
            metadata=row["metadata"],
        )
        for row in rows
    ]


def expire_delegations(db: Database) -> list[str]:
    """Expire delegations past their expires_at timestamp.

    Should be called periodically (e.g., on org start, before delegation operations).

    Args:
        db: Database instance

    Returns:
        List of expired delegation grant IDs
    """
    now = datetime.now()

    # Find expired but not yet revoked delegations
    rows = db.fetchall(
        """SELECT id, delegate_id FROM delegation_grants
           WHERE expires_at IS NOT NULL
             AND expires_at <= ?
             AND revoked_at IS NULL""",
        (now,)
    )

    expired_ids = []
    for row in rows:
        grant_id = row["id"]
        delegate_id = row["delegate_id"]

        # Revoke the delegation
        db.execute(
            """UPDATE delegation_grants
               SET revoked_at = ?, revoked_by = 'system', revoke_reason = 'expired'
               WHERE id = ?""",
            (now, grant_id)
        )

        # Clear worker's delegated authority
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = NULL,
                   delegated_budget = 0,
                   delegated_by = NULL,
                   delegation_expires_at = NULL,
                   delegation_version = delegation_version + 1,
                   updated_at = ?
               WHERE id = ?""",
            (now, delegate_id)
        )

        expired_ids.append(grant_id)

    if expired_ids:
        db.connection.commit()

    return expired_ids



def get_delegation_audit(
    db: Database,
    worker_id: Optional[str] = None,
    limit: int = 100,
) -> list[DelegationAuditRecord]:
    """Get delegation audit records.

    Args:
        db: Database instance
        worker_id: Optional filter by delegator or delegate
        limit: Maximum records to return

    Returns:
        List of audit records, newest first
    """
    if worker_id:
        rows = db.fetchall(
            """SELECT * FROM delegation_audit
               WHERE delegator_id = ? OR delegate_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (worker_id, worker_id, limit)
        )
    else:
        rows = db.fetchall(
            "SELECT * FROM delegation_audit ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )

    return [
        DelegationAuditRecord(
            id=row["id"],
            event_type=row["event_type"],
            delegator_id=row["delegator_id"],
            delegate_id=row["delegate_id"],
            delegation_grant_id=row["delegation_grant_id"],
            scope_before=row["scope_before"],
            scope_after=row["scope_after"],
            budget_before=row["budget_before"],
            budget_after=row["budget_after"],
            performed_by=row["performed_by"],
            performed_by_cli_user=row["performed_by_cli_user"],
            reason=row["reason"],
            timestamp=row["timestamp"],
        )
        for row in rows
    ]


def get_worker_delegation_version(db: Database, worker_id: str) -> int:
    """Get the current delegation_version for a worker.

    Used for optimistic locking in delegation operations.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        Current delegation_version (0 if not set)
    """
    row = db.fetchone(
        "SELECT delegation_version FROM workers WHERE id = ?",
        (worker_id,)
    )
    if row is None:
        return 0
    return row["delegation_version"] or 0


def update_worker_delegation(
    db: Database,
    worker_id: str,
    scope: Optional[str],
    budget: int,
    delegated_by: Optional[str],
    expires_at: Optional[datetime],
    expected_version: int,
) -> bool:
    """Update worker's delegation fields with optimistic locking.

    Args:
        db: Database instance
        worker_id: Worker ID
        scope: JSON-serialized HiringScope (or None to clear)
        budget: Delegated budget
        delegated_by: Worker ID who delegated (or None)
        expires_at: Optional expiration timestamp
        expected_version: Expected delegation_version for optimistic locking

    Returns:
        True if update succeeded, False if version mismatch (concurrent modification)
    """
    now = datetime.now()
    cursor = db.execute(
        """UPDATE workers
           SET hiring_authority_scope = ?,
               delegated_budget = ?,
               delegated_by = ?,
               delegation_expires_at = ?,
               delegation_version = delegation_version + 1,
               updated_at = ?
           WHERE id = ? AND delegation_version = ?""",
        (scope, budget, delegated_by, expires_at, now, worker_id, expected_version)
    )
    db.connection.commit()

    return cursor.rowcount > 0

__all__ = [
    "DelegationAuditRecord",
    "DelegationGrant",
    "RevokeResult",
    "_get_delegation_subtree",
    "check_delegation_cycle",
    "create_delegation_grant",
    "expire_delegations",
    "get_delegation_audit",
    "get_delegation_chain",
    "get_delegation_grant",
    "get_delegation_grant_by_id",
    "get_delegations_by_delegator",
    "get_worker_delegation_version",
    "is_active",
    "revoke_delegation_grant",
    "update_worker_delegation",
]
