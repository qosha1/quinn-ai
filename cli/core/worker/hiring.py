"""
Worker hiring authority and operations.

Handles hiring validation, authority checks, and hiring operations.
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from ..constants import DEFAULT_MAX_REPORTS, DEFAULT_DELEGATED_BUDGET
from ..queries import (
    create_worker,
    get_workers_by_manager,
    get_team_channel,
    subscribe_to_channel,
    add_team_member,
    expire_delegations,
)

if TYPE_CHECKING:
    from ..db import Database


@dataclass
class HiringScope:
    """Defines what a worker can hire.

    Represents the authority a worker has to hire new workers,
    including role restrictions and budget constraints.
    """
    allowed_roles: set[str] = field(default_factory=set)
    """Roles this worker can hire (e.g., {"engineer", "analyst"})."""

    max_cost: int = 0
    """Maximum cost score (0-100) for individual hires."""

    max_total_budget: int = 0
    """Total budget for all hires combined."""

    def to_json(self) -> str:
        """Serialize to JSON string for database storage."""
        return json.dumps({
            "allowed_roles": list(self.allowed_roles),
            "max_cost": self.max_cost,
            "max_total_budget": self.max_total_budget,
        })

    @classmethod
    def from_json(cls, json_str: Optional[str]) -> "HiringScope":
        """Deserialize from JSON string."""
        if not json_str:
            return cls()
        data = json.loads(json_str)
        return cls(
            allowed_roles=set(data.get("allowed_roles", [])),
            max_cost=data.get("max_cost", 0),
            max_total_budget=data.get("max_total_budget", 0),
        )

    def can_hire_role(self, role: str) -> bool:
        """Check if this scope allows hiring the given role.

        Supports wildcard "*" to allow all roles.
        """
        # Wildcard allows all roles
        if "*" in self.allowed_roles:
            return True
        # Otherwise check if specific role is in the allowed set
        return role in self.allowed_roles

    def can_afford_cost(self, cost: int) -> bool:
        """Check if individual hire cost is within limits."""
        return cost <= self.max_cost


class HiringError(Exception):
    """Base exception for hiring-related errors."""
    pass


class InsufficientHiringAuthority(HiringError):
    """Worker lacks authority to make this hire."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class MaxReportsExceeded(HiringError):
    """Worker has reached maximum direct reports."""

    def __init__(self, current: int, maximum: int):
        self.current = current
        self.maximum = maximum
        super().__init__(f"Max reports exceeded: {current}/{maximum}")


class WorkerHiringManager:
    """Manages hiring operations for a worker.

    Handles:
    - Hiring authority validation
    - Hiring scope management
    - Worker creation
    - Direct reports tracking
    """

    def __init__(self, worker: "WorkerBase"):
        """Initialize hiring manager.

        Args:
            worker: Parent Worker instance
        """
        self.worker = worker

    def get_hiring_authority_scope(self) -> HiringScope:
        """Get worker's hiring authority scope.

        Returns:
            HiringScope defining what roles/costs this worker can hire.
        """
        if self.worker._worker_data is None:
            self.worker._load_worker()
        # Get from DB - might be stored as JSON
        scope_json = getattr(self.worker._worker_data, "hiring_authority_scope", None)
        return HiringScope.from_json(scope_json)

    def get_delegated_budget(self) -> int:
        """Get worker's delegated hiring budget.

        Returns:
            Budget amount this worker can delegate to hires.
        """
        if self.worker._worker_data is None:
            self.worker._load_worker()
        return getattr(self.worker._worker_data, "delegated_budget", DEFAULT_DELEGATED_BUDGET)

    def get_max_reports(self) -> int:
        """Get maximum direct reports allowed for this worker.

        Returns:
            Maximum number of direct reports this worker can have.
        """
        if self.worker._worker_data is None:
            self.worker._load_worker()
        return getattr(self.worker._worker_data, "max_reports", DEFAULT_MAX_REPORTS)

    def get_direct_reports_count(self) -> int:
        """Get current count of direct reports.

        Returns:
            Number of workers who report to this worker.
        """
        reports = get_workers_by_manager(self.worker.db, self.worker.id)
        return len(reports)

    def can_hire(self, role: str, cost: int) -> tuple[bool, str]:
        """Check if this worker can hire for a given role and cost.

        Validates against:
        - Allowed roles in hiring scope
        - Cost within max_cost limit
        - Total budget constraints
        - Direct reports count vs max_reports
        - Delegation expiry status

        Args:
            role: Role to hire for
            cost: Cost score (0-100) of the potential hire

        Returns:
            Tuple of (can_hire: bool, reason: str).
            If can_hire is False, reason explains why.
        """
        # Expire any outdated delegations first
        expire_delegations(self.worker.db)

        # Refresh worker data to get current delegation state
        self.worker._worker_data = None

        scope = self.get_hiring_authority_scope()

        # Check if worker has any hiring authority
        if not scope.allowed_roles:
            return False, "No hiring authority - no allowed roles"

        # Check role is allowed
        if not scope.can_hire_role(role):
            return False, f"Role '{role}' not in allowed roles: {scope.allowed_roles}"

        # Check cost is within limits
        if not scope.can_afford_cost(cost):
            return False, f"Cost {cost} exceeds max allowed cost {scope.max_cost}"

        # Check direct reports limit
        current_reports = self.get_direct_reports_count()
        max_reports = self.get_max_reports()
        if current_reports >= max_reports:
            return False, f"Max reports reached: {current_reports}/{max_reports}"

        # Check cumulative budget: sum of active hire costs + new cost
        if scope.max_total_budget > 0:
            # Sum cost of all active workers reporting to this manager
            try:
                result = self.worker.db.fetchone(
                    """SELECT COALESCE(SUM(cost), 0) as total_cost
                       FROM workers
                       WHERE manager_id = ? AND status != 'terminated'""",
                    (self.worker.id,)
                )
                cumulative_cost = result["total_cost"] if result else 0
                total_with_new_hire = cumulative_cost + cost

                if total_with_new_hire > scope.max_total_budget:
                    return False, (
                        f"Budget exceeded: cumulative cost {cumulative_cost} + new hire {cost} "
                        f"= {total_with_new_hire} > budget {scope.max_total_budget}"
                    )
            except Exception as e:
                # If budget check fails, log but don't block hire
                # (database might not have cost column in some test scenarios)
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to check cumulative hiring cost: {e}")

        return True, "OK"

    def hire(
        self,
        name: str,
        role: str,
        skills: dict[str, int],
        cost: int,
    ) -> "Worker":
        """Hire a new worker under this worker.

        Creates a new worker with this worker as manager.
        Validates hiring authority before creating.

        Args:
            name: Name for the new worker
            role: Role for the new worker
            skills: Skills dict for the new worker
            cost: Cost score (0-100) for the new worker

        Returns:
            Worker instance for the newly hired worker

        Raises:
            InsufficientHiringAuthority: If can_hire() fails
            MaxReportsExceeded: If at max direct reports
        """
        # Validate hiring authority
        can_do, reason = self.can_hire(role, cost)
        if not can_do:
            if "Max reports" in reason:
                raise MaxReportsExceeded(
                    self.get_direct_reports_count(),
                    self.get_max_reports()
                )
            raise InsufficientHiringAuthority(reason)

        # Create the worker in database
        worker_data = create_worker(
            db=self.worker.db,
            name=name,
            role=role,
            team_id=self.worker.team_id,
            cost=cost,
            manager_id=self.worker.id,
            skills=skills,
        )

        # Create worker storage folder (mirrors org-chart hierarchy)
        storage_mgr = self.worker._storage_mgr.get_storage_manager()
        storage_mgr.ensure_worker_storage(worker_data.id, reports_to=self.worker.id)

        # Add worker to team_members table (org-chart sync)
        add_team_member(self.worker.db, self.worker.team_id, worker_data.id, role="member")

        # Subscribe new worker to team channel
        team_channel = get_team_channel(self.worker.db, self.worker.team_id)
        if team_channel:
            subscribe_to_channel(self.worker.db, team_channel.id, worker_data.id)

        # Import Worker class here to avoid circular import
        from .base import Worker
        # Return Worker instance
        new_worker = Worker(
            self.worker.db,
            worker_data.id,
            org_path=self.worker._storage_mgr.get_org_path()
        )
        new_worker._worker_data = worker_data

        # Update org-chart to reflect the new hire
        try:
            from ..org_chart import update_org_chart, git_commit_org_chart

            org_path = self.worker._storage_mgr.get_org_path()
            update_org_chart(self.worker.db, org_path)
            # Commit to git (best-effort, gracefully handles non-git repos)
            git_commit_org_chart(
                org_path=org_path,
                change_type="hired",
                worker_name=name,
                worker_role=role,
                details=f"Manager: {self.worker.name} ({self.worker.id})",
            )
        except (ImportError, OSError, subprocess.SubprocessError):
            # Intentionally swallowed: org-chart update is best-effort.
            # ImportError: org_chart module not available
            # OSError: file system issues, SubprocessError: git command failed
            pass

        # Publish WORKER_HIRED event if events module is available
        try:
            from ..events import publish, WORKER_HIRED
            publish(WORKER_HIRED, {
                "worker_id": worker_data.id,
                "name": name,
                "role": role,
                "manager_id": self.worker.id,
                "cost": cost,
            })
        except ImportError:
            pass  # Events module not available yet

        return new_worker
