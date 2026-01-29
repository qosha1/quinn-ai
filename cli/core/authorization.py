"""
Authorization system for QuinnAI.

Provides centralized authorization checks for all operations that require
permission validation. All authorization logic should go through this module.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .db import Database


@dataclass
class AuthorizationResult:
    """Result of an authorization check."""
    allowed: bool
    reason: str

    @classmethod
    def allow(cls, reason: str = "Authorized") -> "AuthorizationResult":
        return cls(allowed=True, reason=reason)

    @classmethod
    def deny(cls, reason: str) -> "AuthorizationResult":
        return cls(allowed=False, reason=reason)


class AuthorizationManager:
    """
    Centralized authorization for all operations.

    All permission checks should go through this class to ensure
    consistent authorization logic across the codebase.
    """

    def __init__(self, db: "Database", org_path: Optional[Path] = None):
        self._db = db
        self._org_path = org_path

    def can(
        self,
        worker_id: str,
        permission: str,
        target_id: Optional[str] = None,
    ) -> AuthorizationResult:
        """
        Check if a worker has permission to perform an action.

        Args:
            worker_id: The worker requesting permission
            permission: The permission being requested (from Permission enum)
            target_id: Optional target resource ID

        Returns:
            AuthorizationResult with allowed status and reason
        """
        from .queries import get_worker

        worker = get_worker(self._db, worker_id)
        if not worker:
            return AuthorizationResult.deny(f"Worker {worker_id} not found")

        # Dispatch to specific permission handlers
        handlers = {
            "hire": self._can_hire,
            "fire": self._can_fire,
            "delegate_budget": self._can_delegate_budget,
            "escalate": self._can_escalate,
            "approve": self._can_approve,
            "assign": self._can_assign,
        }

        handler = handlers.get(permission)
        if handler:
            return handler(worker, target_id)

        # Unknown permission - deny by default
        return AuthorizationResult.deny(f"Unknown permission: {permission}")

    def _parse_hiring_scope(self, worker) -> dict:
        """Parse hiring authority scope from worker data.

        Args:
            worker: Worker dataclass from queries.get_worker

        Returns:
            Dict with allowed_roles, max_cost, max_total_budget
        """
        scope_json = worker.hiring_authority_scope
        if not scope_json:
            return {"allowed_roles": set(), "max_cost": 0, "max_total_budget": 0}
        try:
            data = json.loads(scope_json)
            return {
                "allowed_roles": set(data.get("allowed_roles", [])),
                "max_cost": data.get("max_cost", 0),
                "max_total_budget": data.get("max_total_budget", 0),
            }
        except (json.JSONDecodeError, TypeError):
            return {"allowed_roles": set(), "max_cost": 0, "max_total_budget": 0}

    def _has_hiring_authority(self, worker) -> bool:
        """Check if worker has any hiring authority."""
        scope = self._parse_hiring_scope(worker)
        return len(scope["allowed_roles"]) > 0

    def _has_critical_work(self, worker_id: str) -> tuple[bool, Optional[str]]:
        """Check if worker has critical work in progress.

        Args:
            worker_id: Worker ID to check

        Returns:
            Tuple of (has_critical_work, details_message)
        """
        from .bd_wrapper import run_bd

        # Check if org_path is available
        if not self._org_path:
            # No org_path available, can't check beads
            return False, None

        try:

            # Query for in_progress beads assigned to this worker
            result = run_bd(
                args=["list", "--assignee", worker_id, "--status", "in_progress", "--json"],
                org_path=self._org_path,
                worker_id=None,  # Admin check, skip permission
                capture_output=True,
                skip_permission_check=True,
                skip_lifecycle_check=True,
                skip_okr_check=True,
            )

            if result.returncode != 0:
                # Failed to query beads, allow firing (fail open)
                return False, None

            # Parse JSON output
            import json
            beads_data = json.loads(result.stdout) if result.stdout.strip() else []

            if not beads_data:
                return False, None

            # Worker has active work - list the beads
            bead_ids = [bead.get("id", "unknown") for bead in beads_data]
            return True, f"Worker has {len(bead_ids)} active work item(s): {', '.join(bead_ids[:3])}"

        except Exception as e:
            # On any error, log and allow firing (fail open for safety)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to check critical work for {worker_id}: {e}")
            return False, None

    def _can_hire(self, worker, target_id: Optional[str]) -> AuthorizationResult:
        """Check if worker can hire new workers."""
        # Check authority via hiring_authority_scope
        if not self._has_hiring_authority(worker):
            return AuthorizationResult.deny(
                f"{worker.name} does not have hiring authority"
            )

        # Check budget for new worker
        from .queries import get_worker_balance
        balance = get_worker_balance(self._db, worker.id)
        if not balance or balance.available <= 0:
            return AuthorizationResult.deny(
                f"{worker.name} has no available budget for hiring"
            )

        return AuthorizationResult.allow(
            f"{worker.name} authorized to hire (has hiring scope, budget available)"
        )

    def _can_fire(self, worker, target_id: Optional[str]) -> AuthorizationResult:
        """Check if worker can fire another worker."""
        # Check authority via role - directors and above can fire
        # CEO always can fire, directors can fire within their org
        role = worker.role.lower() if worker.role else ""
        can_fire = role in ("ceo", "director")

        if not can_fire:
            return AuthorizationResult.deny(
                f"{worker.name} does not have firing authority"
            )

        if not target_id:
            return AuthorizationResult.deny("Target worker ID required for fire")

        # Check target is in reports chain
        from .queries import get_worker
        target = get_worker(self._db, target_id)
        if not target:
            return AuthorizationResult.deny(f"Target worker {target_id} not found")

        if target.manager_id != worker.id:
            return AuthorizationResult.deny(
                f"{target.name} is not a direct report of {worker.name}"
            )

        # Check for critical work in progress
        has_work, work_details = self._has_critical_work(target_id)
        if has_work:
            return AuthorizationResult.deny(
                f"Cannot fire {target.name}: {work_details}. "
                "Worker must complete or hand off active work before termination."
            )

        return AuthorizationResult.allow(
            f"{worker.name} authorized to fire {target.name}"
        )

    def _can_delegate_budget(self, worker, target_id: Optional[str]) -> AuthorizationResult:
        """Check if worker can delegate budget to another worker."""
        # Check if worker has delegation authority via budget allocation
        from .queries import get_worker_balance, get_worker_delegation_authority

        # Check budget allocation for can_delegate flag
        can_delegate = get_worker_delegation_authority(self._db, worker.id)

        if not can_delegate:
            return AuthorizationResult.deny(
                f"{worker.name} does not have budget delegation authority"
            )

        if not target_id:
            return AuthorizationResult.deny("Target worker ID required for budget delegation")

        # Check target is in reports chain
        from .queries import get_worker
        target = get_worker(self._db, target_id)
        if not target:
            return AuthorizationResult.deny(f"Target worker {target_id} not found")

        if target.manager_id != worker.id:
            return AuthorizationResult.deny(
                f"{target.name} is not a direct report of {worker.name}"
            )

        # Check sufficient available budget
        balance = get_worker_balance(self._db, worker.id)
        if not balance or balance.available <= 0:
            return AuthorizationResult.deny(
                f"{worker.name} has no available budget to delegate"
            )

        return AuthorizationResult.allow(
            f"{worker.name} authorized to delegate budget to {target.name}"
        )

    def _can_escalate(self, worker, target_id: Optional[str]) -> AuthorizationResult:
        """Check if worker can escalate work."""
        # All workers can escalate to their manager
        if not worker.manager_id:
            return AuthorizationResult.deny(
                f"{worker.name} has no manager to escalate to"
            )

        return AuthorizationResult.allow(
            f"{worker.name} can escalate to manager"
        )

    def _can_approve(self, worker, target_id: Optional[str]) -> AuthorizationResult:
        """Check if worker can approve work from reports."""
        from .queries import get_worker

        if not target_id:
            return AuthorizationResult.deny("Target worker ID required for approval")

        target = get_worker(self._db, target_id)
        if not target:
            return AuthorizationResult.deny(f"Target worker {target_id} not found")

        # Can approve if target is a direct report
        if target.manager_id == worker.id:
            return AuthorizationResult.allow(
                f"{worker.name} can approve work from direct report {target.name}"
            )

        # CEO can approve anyone
        if worker.role and worker.role.lower() == "ceo":
            return AuthorizationResult.allow(
                f"CEO {worker.name} can approve any work"
            )

        return AuthorizationResult.deny(
            f"{worker.name} cannot approve work from {target.name}"
        )

    def _can_assign(self, worker, target_id: Optional[str]) -> AuthorizationResult:
        """Check if worker can assign work to another worker."""
        from .queries import get_worker

        if not target_id:
            return AuthorizationResult.deny("Target worker ID required for assignment")

        target = get_worker(self._db, target_id)
        if not target:
            return AuthorizationResult.deny(f"Target worker {target_id} not found")

        # Can assign to direct reports
        if target.manager_id == worker.id:
            return AuthorizationResult.allow(
                f"{worker.name} can assign work to direct report {target.name}"
            )

        # Can assign to self
        if target.id == worker.id:
            return AuthorizationResult.allow(
                f"{worker.name} can self-assign work"
            )

        return AuthorizationResult.deny(
            f"{worker.name} cannot assign work to {target.name}"
        )
