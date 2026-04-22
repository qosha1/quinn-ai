"""Hierarchical access control for QuinnAI CLI.

Provides PermissionLevel enum, channel/bead permission checking, and
the @requires_permission decorators for enforcing CRUD access control.
"""

import json
import logging
from enum import IntEnum
from functools import wraps
from typing import Callable, List, Optional

from ..db import Database
from ..queries import (
    get_channel,
    get_worker,
    get_worker_team_memberships,
    log_permission_audit,
)
from shared.enums import TeamRole, WorkerRole

_logger = logging.getLogger(__name__)


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

    Aggregates permissions from multiple sources and returns the highest level.

    Permission sources for channels:
    1. Channel subscription (subscribed workers get COMMENT)
    2. Team channel ownership (team members get permissions based on role)
    3. Primary team membership (worker's team matches channel's team)
    4. Direct permission grant
    5. Team-based permission grant
    6. Worker's role (CEO gets ADMIN everywhere)
    7. Global worker permissions

    Args:
        db: Database instance
        worker_id: Worker ID to check
        channel_id: Channel ID to check
        required_level: Minimum required permission level

    Returns:
        The effective permission level
    """
    worker = get_worker(db, worker_id)
    if not worker:
        return PermissionLevel.NONE

    channel = get_channel(db, channel_id)
    if not channel:
        return PermissionLevel.NONE

    permissions: List[PermissionLevel] = []

    permissions.append(_check_subscription_permission(db, worker_id, channel))
    permissions.append(_check_team_membership_permission(db, worker_id, channel))
    permissions.append(_check_primary_team_permission(worker, channel))
    permissions.append(_check_direct_grant_permission(db, worker_id, channel))
    permissions.append(_check_team_grant_permission(db, worker_id, channel))
    permissions.append(_check_ceo_permission(worker))
    permissions.append(_check_global_permission(db, worker_id))

    return max(permissions) if permissions else PermissionLevel.NONE


def _check_subscription_permission(
    db: Database,
    worker_id: str,
    channel: "Channel",
) -> PermissionLevel:
    """Check permission from channel subscription.

    Subscribed workers get COMMENT level access to the channel.

    Args:
        db: Database instance
        worker_id: Worker ID to check
        channel: Channel being accessed

    Returns:
        COMMENT if subscribed, NONE otherwise
    """
    subscription = db.fetchone(
        "SELECT 1 FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?",
        (channel.id, worker_id)
    )
    if subscription:
        return PermissionLevel.COMMENT
    return PermissionLevel.NONE


def _check_team_membership_permission(
    db: Database,
    worker_id: str,
    channel: "Channel",
) -> PermissionLevel:
    """Check permission from team membership on channel's owning team.

    Team members get permissions based on their TeamRole:
    - ADMIN: ADMIN permission
    - LEAD: APPROVE permission
    - MEMBER: WRITE permission

    Args:
        db: Database instance
        worker_id: Worker ID to check
        channel: Channel being accessed

    Returns:
        Permission level based on team role, or NONE if not a member
    """
    if not channel.team_id:
        return PermissionLevel.NONE

    team_membership = db.fetchone(
        "SELECT role FROM team_members WHERE team_id = ? AND worker_id = ?",
        (channel.team_id, worker_id)
    )
    if not team_membership:
        return PermissionLevel.NONE

    team_role = team_membership["role"]
    if team_role == TeamRole.ADMIN.value:
        return PermissionLevel.ADMIN
    elif team_role == TeamRole.LEAD.value:
        return PermissionLevel.APPROVE
    else:
        return PermissionLevel.WRITE


def _check_primary_team_permission(
    worker: "Worker",
    channel: "Channel",
) -> PermissionLevel:
    """Check permission from worker's primary team matching channel's team.

    Workers get WRITE access to channels owned by their primary team.

    Args:
        worker: Worker being checked
        channel: Channel being accessed

    Returns:
        WRITE if primary team matches, NONE otherwise
    """
    if channel.team_id and worker.team_id == channel.team_id:
        return PermissionLevel.WRITE
    return PermissionLevel.NONE


def _check_direct_grant_permission(
    db: Database,
    worker_id: str,
    channel: "Channel",
) -> PermissionLevel:
    """Check permission from direct channel grant.

    Direct grants give workers explicit permission levels on specific channels.

    Args:
        db: Database instance
        worker_id: Worker ID to check
        channel: Channel being accessed

    Returns:
        Granted permission level, or NONE if no grant exists
    """
    direct_grant = db.fetchone(
        """SELECT level FROM permissions
           WHERE bead_id = ? AND grantee_type = 'worker' AND grantee_id = ?""",
        (channel.id, worker_id)
    )
    if direct_grant:
        return PermissionLevel(direct_grant["level"])
    return PermissionLevel.NONE


def _check_team_grant_permission(
    db: Database,
    worker_id: str,
    channel: "Channel",
) -> PermissionLevel:
    """Check permission from team channel grant.

    Workers inherit permissions granted to any of their teams.

    Args:
        db: Database instance
        worker_id: Worker ID to check
        channel: Channel being accessed

    Returns:
        Highest granted permission level from team grants, or NONE
    """
    worker_teams = get_worker_team_memberships(db, worker_id)
    highest = PermissionLevel.NONE

    for membership in worker_teams:
        team_grant = db.fetchone(
            """SELECT level FROM permissions
               WHERE bead_id = ? AND grantee_type = 'team' AND grantee_id = ?""",
            (channel.id, membership.team_id)
        )
        if team_grant:
            level = PermissionLevel(team_grant["level"])
            if level > highest:
                highest = level

    return highest


def _check_ceo_permission(
    worker: "Worker",
) -> PermissionLevel:
    """Check CEO override permission.

    CEO workers get ADMIN permission on all resources.

    Args:
        worker: Worker being checked

    Returns:
        ADMIN if worker is CEO, NONE otherwise
    """
    if worker.role == WorkerRole.CEO.value:
        return PermissionLevel.ADMIN
    return PermissionLevel.NONE


def _check_global_permission(
    db: Database,
    worker_id: str,
) -> PermissionLevel:
    """Check global worker permission.

    Global permissions (bead_id is NULL) apply to all resources.

    Args:
        db: Database instance
        worker_id: Worker ID to check

    Returns:
        Global permission level, or NONE if no global grant exists
    """
    global_worker_perm = db.fetchone(
        """SELECT level FROM permissions
           WHERE bead_id IS NULL AND grantee_type = 'worker' AND grantee_id = ?""",
        (worker_id,)
    )
    if global_worker_perm:
        return PermissionLevel(global_worker_perm["level"])
    return PermissionLevel.NONE


def check_bead_permission(
    db: Database,
    worker_id: str,
    bead_id: str,
) -> PermissionLevel:
    """Check worker's permission level on a bead.

    Permission sources for beads:
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

    worker = get_worker(db, worker_id)
    if not worker:
        return PermissionLevel.NONE

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
    if worker.role == WorkerRole.CEO.value:
        permissions.append(PermissionLevel.ADMIN)

    # 5. Global permissions (bead_id is NULL)
    global_worker_perm = db.fetchone(
        """SELECT level FROM permissions
           WHERE bead_id IS NULL AND grantee_type = 'worker' AND grantee_id = ?""",
        (worker_id,)
    )
    if global_worker_perm:
        permissions.append(PermissionLevel(global_worker_perm["level"]))

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
            pass

        @requires_permission("channel", PermissionLevel.COMMENT, resource_id_param="channel_id")
        def post_message(db: Database, worker_id: str, channel_id: str, content: str):
            pass
    """
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
            resource_id = all_params.get(resource_id_param)

            if db is None:
                raise ValueError(f"Missing required parameter: {db_param}")
            if worker_id is None:
                raise ValueError(f"Missing required parameter: {worker_id_param}")
            if resource_id is None:
                raise ValueError(f"Missing required parameter: {resource_id_param}")

            action_name = action or func.__name__

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
