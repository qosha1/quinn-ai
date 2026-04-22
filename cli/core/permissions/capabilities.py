"""Named capability permissions for QuinnAI CLI.

Provides role-based capability checking and the @requires_named_permission
decorator for enforcing named permissions like "can_hire", "can_fire", etc.
"""

import logging
import sqlite3
from functools import wraps
from typing import Callable, List, Optional

from ..db import Database
from ..queries import get_worker, get_worker_team_memberships
from shared.enums import WorkerRole

_logger = logging.getLogger(__name__)


class NamedPermissionDenied(Exception):
    """Raised when worker lacks required named permission(s)."""

    def __init__(
        self,
        worker_id: str,
        required_permissions: List[str],
        missing_permissions: List[str],
        require_all: bool,
        action: str,
    ):
        self.worker_id = worker_id
        self.required_permissions = required_permissions
        self.missing_permissions = missing_permissions
        self.require_all = require_all
        self.action = action

        logic = "all of" if require_all else "any of"
        super().__init__(
            f"Permission denied: '{action}' requires {logic} {required_permissions} "
            f"but worker '{worker_id}' is missing {missing_permissions}"
        )


def _get_role_permissions(role: str) -> set:
    """Get permissions derived from a worker's role.

    These are implicit permissions that come with certain roles.
    Roles form a hierarchy where higher roles include lower role permissions.

    Args:
        role: Worker role string

    Returns:
        Set of permission names this role grants
    """
    base_permissions = {
        "can_view_own_beads",
        "can_comment",
    }

    # Role-specific permissions — canonical keys use WorkerRole.value so enum
    # renames are caught at definition time rather than silently at runtime.
    # All WorkerRole values (WORKER, SENIOR, MANAGER, DIRECTOR, CEO) are covered.
    # "lead" is kept as a backwards-compatible alias for WorkerRole.SENIOR.
    _senior_permissions = {
        "can_create_beads",
        "can_edit_own_beads",
        "can_assign_beads",
        "can_approve",
        "is_lead",
    }
    role_permissions = {
        WorkerRole.WORKER.value: {
            "can_create_beads",
            "can_edit_own_beads",
        },
        WorkerRole.SENIOR.value: _senior_permissions,
        "lead": _senior_permissions,  # alias: workers stored with role="lead" before SENIOR existed
        WorkerRole.MANAGER.value: {
            "can_create_beads",
            "can_edit_own_beads",
            "can_assign_beads",
            "can_approve",
            "can_hire",
            "is_lead",
            "is_manager",
        },
        WorkerRole.DIRECTOR.value: {
            "can_create_beads",
            "can_edit_own_beads",
            "can_assign_beads",
            "can_approve",
            "can_hire",
            "can_fire",
            "is_lead",
            "is_manager",
            "is_director",
        },
        WorkerRole.CEO.value: {
            "can_create_beads",
            "can_edit_own_beads",
            "can_assign_beads",
            "can_approve",
            "can_hire",
            "can_fire",
            "can_admin",
            "is_lead",
            "is_manager",
            "is_director",
            "is_ceo",
        },
    }
    assert {r.value for r in WorkerRole}.issubset(role_permissions.keys()), (
        f"role_permissions is missing WorkerRole values: "
        f"{set(r.value for r in WorkerRole) - set(role_permissions.keys())}"
    )

    role_key = role.lower()
    return base_permissions | role_permissions.get(role_key, set())


def check_worker_named_permission(
    db: Database,
    worker_id: str,
    permission_name: str,
) -> bool:
    """Check if a worker has a specific named permission.

    Named permissions are capability-based permissions that are either:
    1. Derived from worker role (e.g., CEO has "can_hire", "can_fire")
    2. Stored in the worker_permissions table (if available)
    3. Inherited from team membership (if team_permissions table exists)

    Args:
        db: Database instance
        worker_id: Worker ID to check
        permission_name: Name of the permission to check (e.g., "can_create_beads")

    Returns:
        True if worker has the permission, False otherwise
    """
    worker = get_worker(db, worker_id)
    if not worker:
        return False

    # 1. Check role-based permissions (derived from worker role)
    role_permissions = _get_role_permissions(worker.role)
    if permission_name in role_permissions:
        return True

    # 2. Check direct permission grant in worker_permissions table (if it exists)
    try:
        direct_perm = db.fetchone(
            """SELECT 1 FROM worker_permissions
               WHERE worker_id = ? AND permission_name = ? AND granted = 1""",
            (worker_id, permission_name)
        )
        if direct_perm:
            return True
    except sqlite3.Error as e:
        # Table doesn't exist yet - that's OK, skip this check
        _logger.debug(f"worker_permissions table not accessible: {e}")

    # 3. Check team-based permission grants (if team_permissions table exists)
    try:
        worker_teams = get_worker_team_memberships(db, worker_id)
        for membership in worker_teams:
            team_perm = db.fetchone(
                """SELECT 1 FROM team_permissions
                   WHERE team_id = ? AND permission_name = ? AND granted = 1""",
                (membership.team_id, permission_name)
            )
            if team_perm:
                return True
    except sqlite3.Error as e:
        # Table doesn't exist yet - that's OK, skip this check
        _logger.debug(f"team_permissions table not accessible: {e}")

    return False


def check_worker_named_permissions(
    db: Database,
    worker_id: str,
    permission_names: List[str],
    require_all: bool = True,
) -> tuple[bool, List[str]]:
    """Check if a worker has the specified named permissions.

    Args:
        db: Database instance
        worker_id: Worker ID to check
        permission_names: List of permission names to check
        require_all: If True, worker must have ALL permissions (AND logic).
                    If False, worker needs at least ONE permission (OR logic).

    Returns:
        Tuple of (has_permission: bool, missing_permissions: list).
        For require_all=True, missing_permissions contains all missing.
        For require_all=False, missing_permissions is empty if any granted.
    """
    missing = []
    granted = []

    for perm in permission_names:
        if check_worker_named_permission(db, worker_id, perm):
            granted.append(perm)
        else:
            missing.append(perm)

    if require_all:
        return (len(missing) == 0, missing)
    else:
        return (len(granted) > 0, missing if len(granted) == 0 else [])


def requires_named_permission(
    permissions: str | List[str],
    require_all: bool = True,
    worker_id_param: str = "worker_id",
    db_param: str = "db",
    action: Optional[str] = None,
):
    """Decorator to enforce named permission checks on functions.

    Checks if the worker has the required named permission(s) before
    executing the decorated function. Supports both single permissions
    and multiple permissions with AND/OR logic.

    Args:
        permissions: Permission name or list of permission names to check.
                    Examples: "can_create_beads", ["can_edit", "is_manager"]
        require_all: If True (default), worker must have ALL listed permissions.
                    If False, worker needs at least ONE of the permissions.
        worker_id_param: Name of parameter containing worker ID
        db_param: Name of parameter containing Database instance
        action: Action name for error messages (defaults to function name)

    Returns:
        Decorator function

    Raises:
        NamedPermissionDenied: If worker lacks required permission(s)

    Examples:
        # Single permission
        @requires_named_permission("can_create_beads")
        def create_bead(db: Database, worker_id: str, ...):
            ...

        # Multiple permissions with AND logic (must have all)
        @requires_named_permission(["can_edit", "is_manager"])
        def edit_system_config(db: Database, worker_id: str, ...):
            ...

        # Multiple permissions with OR logic (need at least one)
        @requires_named_permission(["can_edit", "is_manager"], require_all=False)
        def edit_config(db: Database, worker_id: str, ...):
            ...

        # Custom parameter names
        @requires_named_permission("can_approve", worker_id_param="approver_id")
        def approve_request(db: Database, approver_id: str, request_id: str):
            ...
    """
    perm_list = [permissions] if isinstance(permissions, str) else list(permissions)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            import inspect

            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            all_params = bound.arguments

            db = all_params.get(db_param)
            worker_id = all_params.get(worker_id_param)

            if db is None:
                raise ValueError(f"Missing required parameter: {db_param}")
            if worker_id is None:
                raise ValueError(f"Missing required parameter: {worker_id_param}")

            action_name = action or func.__name__

            has_perm, missing = check_worker_named_permissions(
                db=db,
                worker_id=worker_id,
                permission_names=perm_list,
                require_all=require_all,
            )

            if not has_perm:
                raise NamedPermissionDenied(
                    worker_id=worker_id,
                    required_permissions=perm_list,
                    missing_permissions=missing,
                    require_all=require_all,
                    action=action_name,
                )

            return func(*args, **kwargs)

        return wrapper
    return decorator
