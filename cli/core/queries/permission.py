"""Permission and effective permission queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..db import Database
from .common import generate_id

@dataclass
class Permission:
    """Permission grant record."""
    id: str
    bead_id: Optional[str]
    grantee_type: str
    grantee_id: str
    level: int
    granted_by: Optional[str]
    granted_at: datetime


def grant_permission(
    db: Database,
    grantee_type: str,
    grantee_id: str,
    level: int,
    bead_id: Optional[str] = None,
    granted_by: Optional[str] = None,
    permission_id: Optional[str] = None,
) -> Permission:
    """Grant a permission.

    Args:
        db: Database instance
        grantee_type: 'worker' or 'team'
        grantee_id: Worker or team ID
        level: Permission level (0-5)
        bead_id: Optional bead ID (None for global permissions)
        granted_by: Worker ID who granted this
        permission_id: Optional custom ID

    Returns:
        Created Permission
    """
    if permission_id is None:
        permission_id = generate_id("perm")

    now = datetime.now()
    db.execute(
        """INSERT OR REPLACE INTO permissions
           (id, bead_id, grantee_type, grantee_id, level, granted_by, granted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (permission_id, bead_id, grantee_type, grantee_id, level, granted_by, now)
    )
    db.connection.commit()

    return Permission(
        id=permission_id,
        bead_id=bead_id,
        grantee_type=grantee_type,
        grantee_id=grantee_id,
        level=level,
        granted_by=granted_by,
        granted_at=now,
    )


def get_permission(db: Database, permission_id: str) -> Optional[Permission]:
    """Get a permission by ID.

    Args:
        db: Database instance
        permission_id: Permission ID

    Returns:
        Permission or None
    """
    row = db.fetchone("SELECT * FROM permissions WHERE id = ?", (permission_id,))
    if not row:
        return None

    return Permission(
        id=row["id"],
        bead_id=row["bead_id"],
        grantee_type=row["grantee_type"],
        grantee_id=row["grantee_id"],
        level=row["level"],
        granted_by=row["granted_by"],
        granted_at=row["granted_at"],
    )


def get_permission_for_grantee(
    db: Database,
    bead_id: Optional[str],
    grantee_type: str,
    grantee_id: str,
) -> Optional[Permission]:
    """Get a permission for a specific grantee on a bead.

    Args:
        db: Database instance
        bead_id: Bead ID (or None for global)
        grantee_type: 'worker' or 'team'
        grantee_id: Worker or team ID

    Returns:
        Permission or None
    """
    if bead_id is None:
        row = db.fetchone(
            """SELECT * FROM permissions
               WHERE bead_id IS NULL AND grantee_type = ? AND grantee_id = ?""",
            (grantee_type, grantee_id)
        )
    else:
        row = db.fetchone(
            """SELECT * FROM permissions
               WHERE bead_id = ? AND grantee_type = ? AND grantee_id = ?""",
            (bead_id, grantee_type, grantee_id)
        )

    if not row:
        return None

    return Permission(
        id=row["id"],
        bead_id=row["bead_id"],
        grantee_type=row["grantee_type"],
        grantee_id=row["grantee_id"],
        level=row["level"],
        granted_by=row["granted_by"],
        granted_at=row["granted_at"],
    )


def revoke_permission(db: Database, permission_id: str) -> bool:
    """Revoke a permission by ID.

    Args:
        db: Database instance
        permission_id: Permission ID

    Returns:
        True if revoked, False if not found
    """
    cursor = db.execute("DELETE FROM permissions WHERE id = ?", (permission_id,))
    db.connection.commit()
    return cursor.rowcount > 0


def revoke_permission_for_grantee(
    db: Database,
    bead_id: Optional[str],
    grantee_type: str,
    grantee_id: str,
) -> bool:
    """Revoke a permission for a specific grantee on a bead.

    Args:
        db: Database instance
        bead_id: Bead ID (or None for global)
        grantee_type: 'worker' or 'team'
        grantee_id: Worker or team ID

    Returns:
        True if revoked, False if not found
    """
    if bead_id is None:
        cursor = db.execute(
            """DELETE FROM permissions
               WHERE bead_id IS NULL AND grantee_type = ? AND grantee_id = ?""",
            (grantee_type, grantee_id)
        )
    else:
        cursor = db.execute(
            """DELETE FROM permissions
               WHERE bead_id = ? AND grantee_type = ? AND grantee_id = ?""",
            (bead_id, grantee_type, grantee_id)
        )
    db.connection.commit()
    return cursor.rowcount > 0


def get_permissions_for_bead(db: Database, bead_id: str) -> list[Permission]:
    """Get all permissions for a bead.

    Args:
        db: Database instance
        bead_id: Bead ID

    Returns:
        List of Permission records
    """
    rows = db.fetchall("SELECT * FROM permissions WHERE bead_id = ?", (bead_id,))
    return [
        Permission(
            id=row["id"],
            bead_id=row["bead_id"],
            grantee_type=row["grantee_type"],
            grantee_id=row["grantee_id"],
            level=row["level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
        )
        for row in rows
    ]


def get_permissions_for_worker(db: Database, worker_id: str) -> list[Permission]:
    """Get all direct permissions for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of Permission records
    """
    rows = db.fetchall(
        "SELECT * FROM permissions WHERE grantee_type = 'worker' AND grantee_id = ?",
        (worker_id,)
    )
    return [
        Permission(
            id=row["id"],
            bead_id=row["bead_id"],
            grantee_type=row["grantee_type"],
            grantee_id=row["grantee_id"],
            level=row["level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
        )
        for row in rows
    ]


def get_permissions_for_team(db: Database, team_id: str) -> list[Permission]:
    """Get all permissions for a team.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        List of Permission records
    """
    rows = db.fetchall(
        "SELECT * FROM permissions WHERE grantee_type = 'team' AND grantee_id = ?",
        (team_id,)
    )
    return [
        Permission(
            id=row["id"],
            bead_id=row["bead_id"],
            grantee_type=row["grantee_type"],
            grantee_id=row["grantee_id"],
            level=row["level"],
            granted_by=row["granted_by"],
            granted_at=row["granted_at"],
        )
        for row in rows
    ]



@dataclass
class EffectivePermission:
    """Computed effective permission record."""
    worker_id: str
    bead_id: str
    level: int
    computed_at: datetime


def set_effective_permission(
    db: Database,
    worker_id: str,
    bead_id: str,
    level: int,
) -> EffectivePermission:
    """Set or update effective permission for a worker on a bead.

    Args:
        db: Database instance
        worker_id: Worker ID
        bead_id: Bead ID
        level: Computed permission level

    Returns:
        EffectivePermission record
    """
    now = datetime.now()
    db.execute(
        """INSERT OR REPLACE INTO effective_permissions
           (worker_id, bead_id, level, computed_at)
           VALUES (?, ?, ?, ?)""",
        (worker_id, bead_id, level, now)
    )
    db.connection.commit()

    return EffectivePermission(
        worker_id=worker_id,
        bead_id=bead_id,
        level=level,
        computed_at=now,
    )


def get_effective_permission(
    db: Database,
    worker_id: str,
    bead_id: str,
) -> Optional[EffectivePermission]:
    """Get effective permission for a worker on a bead.

    Args:
        db: Database instance
        worker_id: Worker ID
        bead_id: Bead ID

    Returns:
        EffectivePermission or None
    """
    row = db.fetchone(
        "SELECT * FROM effective_permissions WHERE worker_id = ? AND bead_id = ?",
        (worker_id, bead_id)
    )
    if not row:
        return None

    return EffectivePermission(
        worker_id=row["worker_id"],
        bead_id=row["bead_id"],
        level=row["level"],
        computed_at=row["computed_at"],
    )


def delete_effective_permission(db: Database, worker_id: str, bead_id: str) -> bool:
    """Delete effective permission for a worker on a bead.

    Args:
        db: Database instance
        worker_id: Worker ID
        bead_id: Bead ID

    Returns:
        True if deleted, False if not found
    """
    cursor = db.execute(
        "DELETE FROM effective_permissions WHERE worker_id = ? AND bead_id = ?",
        (worker_id, bead_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def delete_effective_permissions_for_bead(db: Database, bead_id: str) -> int:
    """Delete all effective permissions for a bead.

    Args:
        db: Database instance
        bead_id: Bead ID

    Returns:
        Number of records deleted
    """
    cursor = db.execute(
        "DELETE FROM effective_permissions WHERE bead_id = ?",
        (bead_id,)
    )
    db.connection.commit()
    return cursor.rowcount



@dataclass
class PermissionAudit:
    """Permission audit log entry."""
    id: str
    action: str
    bead_id: str
    worker_id: str
    level: Optional[int]
    details: Optional[str]
    created_at: datetime


def log_permission_audit(
    db: Database,
    action: str,
    bead_id: str,
    worker_id: str,
    level: Optional[int] = None,
    details: Optional[str] = None,
    audit_id: Optional[str] = None,
) -> PermissionAudit:
    """Log a permission audit entry.

    Args:
        db: Database instance
        action: 'grant', 'revoke', 'check', or 'deny'
        bead_id: Bead ID
        worker_id: Worker ID
        level: Permission level (optional)
        details: Additional details as JSON string
        audit_id: Optional custom ID

    Returns:
        Created PermissionAudit
    """
    if audit_id is None:
        audit_id = generate_id("audit")

    now = datetime.now()
    db.execute(
        """INSERT INTO permission_audit
           (id, action, bead_id, worker_id, level, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (audit_id, action, bead_id, worker_id, level, details, now)
    )
    db.connection.commit()

    return PermissionAudit(
        id=audit_id,
        action=action,
        bead_id=bead_id,
        worker_id=worker_id,
        level=level,
        details=details,
        created_at=now,
    )


def get_permission_audit_for_bead(
    db: Database,
    bead_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[PermissionAudit]:
    """Get audit log entries for a bead.

    Args:
        db: Database instance
        bead_id: Bead ID
        limit: Max entries to return
        offset: Offset for pagination

    Returns:
        List of PermissionAudit records
    """
    rows = db.fetchall(
        """SELECT * FROM permission_audit
           WHERE bead_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (bead_id, limit, offset)
    )
    return [
        PermissionAudit(
            id=row["id"],
            action=row["action"],
            bead_id=row["bead_id"],
            worker_id=row["worker_id"],
            level=row["level"],
            details=row["details"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_permission_audit_for_worker(
    db: Database,
    worker_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[PermissionAudit]:
    """Get audit log entries for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID
        limit: Max entries to return
        offset: Offset for pagination

    Returns:
        List of PermissionAudit records
    """
    rows = db.fetchall(
        """SELECT * FROM permission_audit
           WHERE worker_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (worker_id, limit, offset)
    )
    return [
        PermissionAudit(
            id=row["id"],
            action=row["action"],
            bead_id=row["bead_id"],
            worker_id=row["worker_id"],
            level=row["level"],
            details=row["details"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_permission_denials(
    db: Database,
    limit: int = 50,
    offset: int = 0,
) -> list[PermissionAudit]:
    """Get recent permission denials.

    Args:
        db: Database instance
        limit: Max entries to return
        offset: Offset for pagination

    Returns:
        List of PermissionAudit records with action='deny'
    """
    rows = db.fetchall(
        """SELECT * FROM permission_audit
           WHERE action = 'deny' ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset)
    )
    return [
        PermissionAudit(
            id=row["id"],
            action=row["action"],
            bead_id=row["bead_id"],
            worker_id=row["worker_id"],
            level=row["level"],
            details=row["details"],
            created_at=row["created_at"],
        )
        for row in rows
    ]

__all__ = [
    "EffectivePermission",
    "Permission",
    "PermissionAudit",
    "delete_effective_permission",
    "delete_effective_permissions_for_bead",
    "get_effective_permission",
    "get_permission",
    "get_permission_audit_for_bead",
    "get_permission_audit_for_worker",
    "get_permission_denials",
    "get_permission_for_grantee",
    "get_permissions_for_bead",
    "get_permissions_for_team",
    "get_permissions_for_worker",
    "grant_permission",
    "log_permission_audit",
    "revoke_permission",
    "revoke_permission_for_grantee",
    "set_effective_permission",
]
