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
