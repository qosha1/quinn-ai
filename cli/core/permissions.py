"""
Permission enforcement for QuinnAI CLI.

Provides permission levels, checking, and the @requires_permission decorator
for enforcing access control on bead and channel operations.
"""

import json
from enum import IntEnum
from functools import wraps
from typing import Callable, Optional, List
from dataclasses import dataclass
from datetime import datetime

from .db import Database
from .queries import (
    generate_id,
    get_worker,
    get_channel,
    get_worker_team_memberships,
    log_permission_audit,
)


class PermissionLevel(IntEnum):
    """Permission levels in ascending order of capability.

    Each level includes all capabilities of lower levels:
    - NONE: No access (cannot even see the resource exists)
    - READ: View details, metadata, comments, history
    - COMMENT: Add comments, subscribe to updates
    - WRITE: Modify content, status, assignees, labels
    - APPROVE: Approve/reject, close, change lifecycle state
    - ADMIN: Delete, change permissions, transfer ownership
    """
    NONE = 0
    READ = 1
    COMMENT = 2
    WRITE = 3
    APPROVE = 4
    ADMIN = 5


class PermissionDenied(Exception):
    """Raised when worker lacks required permission."""

    def __init__(
        self,
        worker_id: str,
        resource_type: str,
        resource_id: str,
        required: PermissionLevel,
        actual: PermissionLevel,
        action: str
    ):
        self.worker_id = worker_id
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.required = required
        self.actual = actual
        self.action = action
        super().__init__(
            f"Permission denied: '{action}' on {resource_type} '{resource_id}' "
            f"requires {required.name} but worker '{worker_id}' has {actual.name}"
        )


def check_channel_permission(
    db: Database,
    worker_id: str,
    channel_id: str,
    required_level: PermissionLevel,
) -> PermissionLevel:
    """Check worker's permission level on a channel.

    Permission sources for channels:
    1. Channel subscription (subscribed workers get COMMENT)
    2. Team channel ownership (team members get WRITE on their team's channels)
    3. Direct permission grant
    4. Team-based permission grant
    5. Worker's role (CEO gets ADMIN everywhere)

    Args:
        db: Database instance
        worker_id: Worker ID to check
        channel_id: Channel ID to check
        required_level: Minimum required permission level

    Returns:
        The effective permission level
    """
    permissions: List[PermissionLevel] = []

    # Get worker info
    worker = get_worker(db, worker_id)
    if not worker:
        return PermissionLevel.NONE

    # Get channel info
    channel = get_channel(db, channel_id)
    if not channel:
        return PermissionLevel.NONE

    # 1. Check if worker is subscribed to channel (gets COMMENT)
    subscription = db.fetchone(
        "SELECT 1 FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?",
        (channel_id, worker_id)
    )
    if subscription:
        permissions.append(PermissionLevel.COMMENT)

    # 2. Check if channel belongs to worker's team (team members get WRITE)
    if channel.team_id:
        # Check if worker is in the team that owns the channel
        team_membership = db.fetchone(
            "SELECT role FROM team_members WHERE team_id = ? AND worker_id = ?",
            (channel.team_id, worker_id)
        )
        if team_membership:
            team_role = team_membership["role"]
            if team_role == "admin":
                permissions.append(PermissionLevel.ADMIN)
            elif team_role == "lead":
                permissions.append(PermissionLevel.APPROVE)
            else:
                permissions.append(PermissionLevel.WRITE)

        # Also check if worker's primary team matches
        if worker.team_id == channel.team_id:
            permissions.append(PermissionLevel.WRITE)

    # 3. Check direct permission grant on channel (using channel_id as bead_id)
    direct_grant = db.fetchone(
        """SELECT level FROM permissions
           WHERE bead_id = ? AND grantee_type = 'worker' AND grantee_id = ?""",
        (channel_id, worker_id)
    )
    if direct_grant:
        permissions.append(PermissionLevel(direct_grant["level"]))

    # 4. Check team-based permission grants
    worker_teams = get_worker_team_memberships(db, worker_id)
    for membership in worker_teams:
        team_grant = db.fetchone(
            """SELECT level FROM permissions
               WHERE bead_id = ? AND grantee_type = 'team' AND grantee_id = ?""",
            (channel_id, membership.team_id)
        )
        if team_grant:
            permissions.append(PermissionLevel(team_grant["level"]))

    # 5. CEO gets ADMIN on everything
    if worker.role == "CEO":
        permissions.append(PermissionLevel.ADMIN)

    # 6. Global permissions (bead_id is NULL)
    global_worker_perm = db.fetchone(
        """SELECT level FROM permissions
           WHERE bead_id IS NULL AND grantee_type = 'worker' AND grantee_id = ?""",
        (worker_id,)
    )
    if global_worker_perm:
        permissions.append(PermissionLevel(global_worker_perm["level"]))

    # Return maximum permission, or NONE if empty
    return max(permissions) if permissions else PermissionLevel.NONE


def check_bead_permission(
    db: Database,
    worker_id: str,
    bead_id: str,
) -> PermissionLevel:
    """Check worker's permission level on a bead.

    Permission sources for beads (from design doc):
    1. Direct grant on the specific bead
    2. Bead creator gets ADMIN
    3. Bead assignee gets WRITE
    4. Same team as bead = WRITE
    5. Parent team visibility = READ
    6. Manager chain visibility = READ
    7. CEO gets ADMIN everywhere
    8. Team-based grants

    Args:
        db: Database instance
        worker_id: Worker ID to check
        bead_id: Bead ID to check

    Returns:
        The effective permission level
    """
    permissions: List[PermissionLevel] = []

    # Get worker info
    worker = get_worker(db, worker_id)
    if not worker:
        return PermissionLevel.NONE

    # Note: beads are stored in a separate beads database, so we check
    # effective_permissions cache table first, then fall back to grants

    # 1. Check precomputed effective permissions cache
    cached = db.fetchone(
        "SELECT level FROM effective_permissions WHERE worker_id = ? AND bead_id = ?",
        (worker_id, bead_id)
    )
    if cached:
        permissions.append(PermissionLevel(cached["level"]))

    # 2. Check direct permission grant
    direct_grant = db.fetchone(
        """SELECT level FROM permissions
           WHERE bead_id = ? AND grantee_type = 'worker' AND grantee_id = ?""",
        (bead_id, worker_id)
    )
    if direct_grant:
        permissions.append(PermissionLevel(direct_grant["level"]))

    # 3. Check team-based grants
    worker_teams = get_worker_team_memberships(db, worker_id)
    for membership in worker_teams:
        team_grant = db.fetchone(
            """SELECT level FROM permissions
               WHERE bead_id = ? AND grantee_type = 'team' AND grantee_id = ?""",
            (bead_id, membership.team_id)
        )
        if team_grant:
            permissions.append(PermissionLevel(team_grant["level"]))

    # 4. CEO gets ADMIN on everything
    if worker.role == "CEO":
        permissions.append(PermissionLevel.ADMIN)

    # 5. Global permissions (bead_id is NULL)
    global_worker_perm = db.fetchone(
        """SELECT level FROM permissions
           WHERE bead_id IS NULL AND grantee_type = 'worker' AND grantee_id = ?""",
        (worker_id,)
    )
    if global_worker_perm:
        permissions.append(PermissionLevel(global_worker_perm["level"]))

    # Return maximum permission, or NONE if empty
    return max(permissions) if permissions else PermissionLevel.NONE


def require_channel_permission(
    db: Database,
    worker_id: str,
    channel_id: str,
    required_level: PermissionLevel,
    action: str,
    audit: bool = True,
) -> None:
    """Require a specific permission level on a channel.

    Args:
        db: Database instance
        worker_id: Worker ID performing the action
        channel_id: Channel ID being accessed
        required_level: Minimum required permission level
        action: Name of the action being performed (for audit/error)
        audit: Whether to log denials to audit table

    Raises:
        PermissionDenied: If worker lacks required permission
    """
    actual = check_channel_permission(db, worker_id, channel_id, required_level)

    if actual < required_level:
        # Audit the denial
        if audit:
            log_permission_audit(
                db=db,
                action="deny",
                bead_id=channel_id,
                worker_id=worker_id,
                level=required_level,
                details=json.dumps({
                    "action": action,
                    "resource_type": "channel",
                    "required": required_level.name,
                    "actual": actual.name,
                }),
            )

        raise PermissionDenied(
            worker_id=worker_id,
            resource_type="channel",
            resource_id=channel_id,
            required=required_level,
            actual=actual,
            action=action,
        )


def require_bead_permission(
    db: Database,
    worker_id: str,
    bead_id: str,
    required_level: PermissionLevel,
    action: str,
    audit: bool = True,
) -> None:
    """Require a specific permission level on a bead.

    Args:
        db: Database instance
        worker_id: Worker ID performing the action
        bead_id: Bead ID being accessed
        required_level: Minimum required permission level
        action: Name of the action being performed (for audit/error)
        audit: Whether to log denials to audit table

    Raises:
        PermissionDenied: If worker lacks required permission
    """
    actual = check_bead_permission(db, worker_id, bead_id)

    if actual < required_level:
        # Audit the denial
        if audit:
            log_permission_audit(
                db=db,
                action="deny",
                bead_id=bead_id,
                worker_id=worker_id,
                level=required_level,
                details=json.dumps({
                    "action": action,
                    "resource_type": "bead",
                    "required": required_level.name,
                    "actual": actual.name,
                }),
            )

        raise PermissionDenied(
            worker_id=worker_id,
            resource_type="bead",
            resource_id=bead_id,
            required=required_level,
            actual=actual,
            action=action,
        )


def can_worker_access_channel(
    db: Database,
    worker_id: str,
    channel_id: str,
    level: PermissionLevel = PermissionLevel.READ,
) -> bool:
    """Check if worker can access a channel at the given level.

    Convenience function for boolean checks.

    Args:
        db: Database instance
        worker_id: Worker ID to check
        channel_id: Channel ID to check
        level: Required permission level (default: READ)

    Returns:
        True if worker has at least the required permission level
    """
    actual = check_channel_permission(db, worker_id, channel_id, level)
    return actual >= level


def can_worker_access_bead(
    db: Database,
    worker_id: str,
    bead_id: str,
    level: PermissionLevel = PermissionLevel.READ,
) -> bool:
    """Check if worker can access a bead at the given level.

    Convenience function for boolean checks.

    Args:
        db: Database instance
        worker_id: Worker ID to check
        bead_id: Bead ID to check
        level: Required permission level (default: READ)

    Returns:
        True if worker has at least the required permission level
    """
    actual = check_bead_permission(db, worker_id, bead_id)
    return actual >= level


# =========================================================================
# Permission Decorators
# =========================================================================


def requires_permission(
    resource_type: str,
    level: PermissionLevel,
    resource_id_param: str = "bead_id",
    worker_id_param: str = "worker_id",
    db_param: str = "db",
    action: Optional[str] = None,
):
    """Decorator to enforce permission checks on functions.

    Extracts resource_id, worker_id, and db from function parameters and
    checks if the worker has the required permission level before executing.

    Args:
        resource_type: Type of resource ("bead" or "channel")
        level: Required permission level
        resource_id_param: Name of parameter containing resource ID
        worker_id_param: Name of parameter containing worker ID
        db_param: Name of parameter containing Database instance
        action: Action name for audit (defaults to function name)

    Returns:
        Decorator function

    Example:
        @requires_permission("bead", PermissionLevel.WRITE)
        def update_bead(db: Database, worker_id: str, bead_id: str, **data):
            # Only runs if worker has WRITE permission on bead
            pass

        @requires_permission("channel", PermissionLevel.COMMENT, resource_id_param="channel_id")
        def post_message(db: Database, worker_id: str, channel_id: str, content: str):
            # Only runs if worker has COMMENT permission on channel
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            import inspect

            # Get function signature to map args to kwargs
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            all_params = bound.arguments

            # Extract required parameters
            db = all_params.get(db_param)
            worker_id = all_params.get(worker_id_param)
            resource_id = all_params.get(resource_id_param)

            if db is None:
                raise ValueError(f"Missing required parameter: {db_param}")
            if worker_id is None:
                raise ValueError(f"Missing required parameter: {worker_id_param}")
            if resource_id is None:
                raise ValueError(f"Missing required parameter: {resource_id_param}")

            # Determine action name
            action_name = action or func.__name__

            # Check permission based on resource type
            if resource_type == "bead":
                require_bead_permission(
                    db=db,
                    worker_id=worker_id,
                    bead_id=resource_id,
                    required_level=level,
                    action=action_name,
                )
            elif resource_type == "channel":
                require_channel_permission(
                    db=db,
                    worker_id=worker_id,
                    channel_id=resource_id,
                    required_level=level,
                    action=action_name,
                )
            else:
                raise ValueError(f"Unknown resource type: {resource_type}")

            # Permission check passed - execute the function
            return func(*args, **kwargs)

        return wrapper
    return decorator


def requires_bead_permission(
    level: PermissionLevel,
    bead_id_param: str = "bead_id",
    worker_id_param: str = "worker_id",
    db_param: str = "db",
    action: Optional[str] = None,
):
    """Convenience decorator for bead permission checks.

    Equivalent to @requires_permission("bead", level, ...).

    Example:
        @requires_bead_permission(PermissionLevel.APPROVE)
        def close_bead(db: Database, worker_id: str, bead_id: str):
            pass
    """
    return requires_permission(
        resource_type="bead",
        level=level,
        resource_id_param=bead_id_param,
        worker_id_param=worker_id_param,
        db_param=db_param,
        action=action,
    )


def requires_channel_permission(
    level: PermissionLevel,
    channel_id_param: str = "channel_id",
    worker_id_param: str = "worker_id",
    db_param: str = "db",
    action: Optional[str] = None,
):
    """Convenience decorator for channel permission checks.

    Equivalent to @requires_permission("channel", level, ...).

    Example:
        @requires_channel_permission(PermissionLevel.WRITE)
        def delete_message(db: Database, worker_id: str, channel_id: str, message_id: str):
            pass
    """
    return requires_permission(
        resource_type="channel",
        level=level,
        resource_id_param=channel_id_param,
        worker_id_param=worker_id_param,
        db_param=db_param,
        action=action,
    )


# =========================================================================
# Named Permission Decorator (capability-based)
# =========================================================================


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
    except Exception:
        # Table doesn't exist yet - that's OK, skip this check
        pass

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
    except Exception:
        # Table doesn't exist yet - that's OK, skip this check
        pass

    return False


def _get_role_permissions(role: str) -> set:
    """Get permissions derived from a worker's role.

    These are implicit permissions that come with certain roles.
    Roles form a hierarchy where higher roles include lower role permissions.

    Args:
        role: Worker role string

    Returns:
        Set of permission names this role grants
    """
    # Base permissions everyone has
    base_permissions = {
        "can_view_own_beads",
        "can_comment",
    }

    # Role-specific permissions
    role_permissions = {
        "worker": {
            "can_create_beads",
            "can_edit_own_beads",
        },
        "lead": {
            "can_create_beads",
            "can_edit_own_beads",
            "can_assign_beads",
            "can_approve",
            "is_lead",
        },
        "manager": {
            "can_create_beads",
            "can_edit_own_beads",
            "can_assign_beads",
            "can_approve",
            "can_hire",
            "is_lead",
            "is_manager",
        },
        "director": {
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
        "CEO": {
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

    # Normalize role to lowercase for lookup (except CEO)
    role_key = role if role == "CEO" else role.lower()
    return base_permissions | role_permissions.get(role_key, set())


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
        # All permissions required - fail if any missing
        return (len(missing) == 0, missing)
    else:
        # Any permission sufficient - succeed if any granted
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
    # Normalize to list
    perm_list = [permissions] if isinstance(permissions, str) else list(permissions)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            import inspect

            # Get function signature to map args to kwargs
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            all_params = bound.arguments

            # Extract required parameters
            db = all_params.get(db_param)
            worker_id = all_params.get(worker_id_param)

            if db is None:
                raise ValueError(f"Missing required parameter: {db_param}")
            if worker_id is None:
                raise ValueError(f"Missing required parameter: {worker_id_param}")

            # Determine action name
            action_name = action or func.__name__

            # Check permissions
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

            # Permission check passed - execute the function
            return func(*args, **kwargs)

        return wrapper
    return decorator
