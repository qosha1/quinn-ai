"""
Worker delegation authority management.

Handles delegation grant/revoke and delegation chain validation.
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from ..queries import (
    create_delegation_grant,
    get_delegation_grant,
    revoke_delegation_grant,
    check_delegation_cycle,
    get_delegations_by_delegator,
    get_worker_delegation_version,
    update_worker_delegation,
    DelegationGrant,
    RevokeResult,
)
from shared.exceptions import (
    CircularDelegationError,
    DelegationNotFoundError,
    ConcurrentModificationError,
)
from .hiring import HiringScope, InsufficientHiringAuthority

if TYPE_CHECKING:
    from ..db import Database


class WorkerDelegationManager:
    """Manages delegation operations for a worker.

    Handles:
    - Delegation authority grant
    - Delegation revocation
    - Circular delegation detection
    - Optimistic locking for concurrent modifications
    """

    def __init__(self, worker: "WorkerBase"):
        """Initialize delegation manager.

        Args:
            worker: Parent Worker instance
        """
        self.worker = worker

    def delegate_authority(
        self,
        report: "Worker",
        budget: int,
        scope: HiringScope,
        granted_by_cli_user: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> DelegationGrant:
        """Delegate hiring authority to a direct report.

        Grants a subordinate worker the ability to hire within specified constraints.
        The delegated scope must be a subset of this worker's own authority.

        This method implements P0 security fixes:
        - Self-delegation prevention
        - Lifecycle validation (terminated workers)
        - Circular delegation detection
        - Optimistic locking for concurrent modifications

        Args:
            report: Worker to delegate authority to (must be a direct report)
            budget: Budget amount to delegate for hiring
            scope: HiringScope defining allowed roles/costs
            granted_by_cli_user: Optional CLI user initiating the delegation
            expires_at: Optional expiration timestamp for time-limited delegations

        Returns:
            Created DelegationGrant record

        Raises:
            ValueError: If report is not a direct report, self-delegation, or terminated
            InsufficientHiringAuthority: If trying to delegate more than own authority
            CircularDelegationError: If delegation would create a cycle
            ConcurrentModificationError: If concurrent modification detected
        """
        # P0: Self-delegation check
        if report.id == self.worker.id:
            raise ValueError("Cannot delegate authority to yourself")

        # P0: Lifecycle validation - cannot delegate FROM terminated worker
        if self.worker.lifecycle_status == "terminated":
            raise ValueError("Terminated workers cannot delegate authority")

        # P0: Lifecycle validation - cannot delegate TO terminated worker
        if report.lifecycle_status == "terminated":
            raise ValueError("Cannot delegate authority to terminated worker")

        # Verify report is actually a direct report
        if report.manager_id != self.worker.id:
            raise ValueError(
                f"Worker {report.id} is not a direct report of {self.worker.id}"
            )

        # P0: Check for circular delegation
        if check_delegation_cycle(self.worker.db, self.worker.id, report.id):
            raise CircularDelegationError(self.worker.id, report.id)

        # Verify delegated scope is subset of own scope
        own_scope = self.worker._hiring_mgr.get_hiring_authority_scope()
        for role in scope.allowed_roles:
            # Use can_hire_role to handle wildcard "*" correctly
            if not own_scope.can_hire_role(role):
                raise InsufficientHiringAuthority(
                    f"Cannot delegate role '{role}' - not in own authority"
                )

        if scope.max_cost > own_scope.max_cost:
            raise InsufficientHiringAuthority(
                f"Cannot delegate max_cost {scope.max_cost} exceeding own {own_scope.max_cost}"
            )

        # Verify budget is within own delegated budget
        if budget > self.worker._hiring_mgr.get_delegated_budget():
            raise InsufficientHiringAuthority(
                f"Cannot delegate budget {budget} exceeding own "
                f"{self.worker._hiring_mgr.get_delegated_budget()}"
            )

        # P0: Get current delegation_version for optimistic locking
        expected_version = get_worker_delegation_version(self.worker.db, report.id)

        # Create delegation grant record (triggers auto-audit)
        grant = create_delegation_grant(
            db=self.worker.db,
            delegator_id=self.worker.id,
            delegate_id=report.id,
            scope=scope.to_json(),
            budget=budget,
            granted_by_cli_user=granted_by_cli_user,
            expires_at=expires_at,
        )

        # P0: Update worker with optimistic locking
        success = update_worker_delegation(
            db=self.worker.db,
            worker_id=report.id,
            scope=scope.to_json(),
            budget=budget,
            delegated_by=self.worker.id,
            expires_at=expires_at,
            expected_version=expected_version,
        )

        if not success:
            # Rollback the delegation grant
            self.worker.db.execute(
                "DELETE FROM delegation_grants WHERE id = ?",
                (grant.id,)
            )
            self.worker.db.connection.commit()
            raise ConcurrentModificationError(
                "worker", report.id,
                "Another process modified this worker's delegation state"
            )

        # Invalidate report's cache
        report._worker_data = None

        # Publish delegation event if events module is available
        try:
            from ..events import publish, AUTHORITY_DELEGATED
            publish(AUTHORITY_DELEGATED, {
                "delegator_id": self.worker.id,
                "delegate_id": report.id,
                "budget": budget,
                "scope": scope.to_json(),
            })
        except ImportError:
            pass  # Events module not available yet

        return grant

    def revoke_authority(
        self,
        delegate: "Worker",
        cascade: bool = False,
        reason: Optional[str] = None,
    ) -> RevokeResult:
        """Revoke hiring authority from a delegate.

        Removes the hiring authority that was previously delegated to a worker.
        Optionally cascades to revoke all sub-delegations as well.

        Args:
            delegate: Worker whose authority to revoke
            cascade: If True, also revoke all delegations granted by the delegate
            reason: Optional human-readable reason for revocation

        Returns:
            RevokeResult with revocation details

        Raises:
            ValueError: If no active delegation found
            DelegationNotFoundError: If delegate has no active delegation from this worker
        """
        # Verify delegation exists and was granted by this worker
        grant = get_delegation_grant(self.worker.db, delegate.id)
        if grant is None:
            raise DelegationNotFoundError(delegate.id)

        if grant.delegator_id != self.worker.id:
            raise ValueError(
                f"Delegation for {delegate.id} was granted by {grant.delegator_id}, "
                f"not by {self.worker.id}"
            )

        # Check if cascade is needed but not requested
        sub_delegations = get_delegations_by_delegator(self.worker.db, delegate.id)
        if sub_delegations and not cascade:
            raise ValueError(
                f"Worker {delegate.id} has {len(sub_delegations)} sub-delegations. "
                f"Use cascade=True to revoke all, or revoke them individually first."
            )

        # Perform revocation
        result = revoke_delegation_grant(
            db=self.worker.db,
            delegate_id=delegate.id,
            revoked_by=self.worker.id,
            reason=reason,
            cascade=cascade,
        )

        # Invalidate delegate's cache
        delegate._worker_data = None

        # Publish revocation event if events module is available
        try:
            from ..events import publish, AUTHORITY_REVOKED
            publish(AUTHORITY_REVOKED, {
                "delegator_id": self.worker.id,
                "delegate_id": delegate.id,
                "cascade": cascade,
                "cascade_count": result.cascade_count,
                "reason": reason,
            })
        except ImportError:
            pass  # Events module not available yet

        return result
