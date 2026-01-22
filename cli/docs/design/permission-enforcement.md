# Permission Enforcement System Design

## Overview

This document defines the permission enforcement system for QuinnAI. The system controls which workers can perform which actions on beads, ensuring team isolation while supporting hierarchical permission inheritance from the org-chart.

**Core Principle**: Marketing can't modify engineering beads. Permissions flow down the org-chart hierarchy. Parent teams inherit visibility into child team work.

## 1. Permission Levels

Permission levels form a strict hierarchy where each level includes all capabilities of lower levels.

```
none → read → comment → write → approve → admin
  0      1       2        3        4        5
```

| Level | Numeric | Capabilities |
|-------|---------|--------------|
| `none` | 0 | No access (cannot even see the bead exists) |
| `read` | 1 | View bead details, metadata, comments, history |
| `comment` | 2 | Add comments, subscribe to updates |
| `write` | 3 | Modify bead content, status, assignees, labels |
| `approve` | 4 | Approve/reject beads, close, change lifecycle state |
| `admin` | 5 | Delete, change permissions, transfer ownership |

### Level Comparison

```python
class PermissionLevel(IntEnum):
    NONE = 0
    READ = 1
    COMMENT = 2
    WRITE = 3
    APPROVE = 4
    ADMIN = 5

def has_permission(required: PermissionLevel, actual: PermissionLevel) -> bool:
    """Higher levels include all lower level capabilities."""
    return actual >= required
```

## 2. Enforcement Location

Permission checks occur at **three layers** with different responsibilities:

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│  - Early rejection for UX (fast feedback)                   │
│  - Uses cached permissions                                   │
│  - NOT authoritative (can be bypassed)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Service Layer                           │
│  - AUTHORITATIVE enforcement                                 │
│  - Decorator-based checks before business logic              │
│  - Loads permissions from cache or DB                        │
│  - Raises PermissionDenied on failure                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Database Layer                         │
│  - Row-level security (optional, defense in depth)          │
│  - Triggers for audit logging                               │
│  - NOT primary enforcement (performance cost)               │
└─────────────────────────────────────────────────────────────┘
```

### Service Layer = Single Source of Truth

All permission checks MUST go through the service layer. The `bd_wrapper.py` module becomes the enforcement point for all bead operations:

```python
# cli/core/bd_wrapper.py additions

class BeadService:
    """Bead operations with permission enforcement."""

    def __init__(self, db: Database, worker_id: str):
        self.db = db
        self.worker_id = worker_id
        self._permission_cache = PermissionCache(db, worker_id)

    @requires_permission(PermissionLevel.WRITE)
    def update_bead(self, bead_id: str, **updates) -> Bead:
        """Update a bead (requires write permission)."""
        # Business logic here
        ...

    @requires_permission(PermissionLevel.APPROVE)
    def close_bead(self, bead_id: str, resolution: str) -> Bead:
        """Close a bead (requires approve permission)."""
        ...
```

## 3. Inheritance Rules

Permissions flow from multiple sources with explicit precedence. The effective permission for a worker on a bead is the **maximum** of all applicable grants.

### Permission Sources (in precedence order)

1. **Direct Grant** - Explicit permission on the specific bead
2. **Team Ownership** - Worker's team owns the bead
3. **Org Hierarchy** - Worker is in a parent team of the owning team
4. **Manager Chain** - Worker is in the management chain of the assignee
5. **Default** - Organization-wide default (typically `none`)

### Inheritance Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     Board (org-wide visibility)              │
│                        ┌───────────┐                         │
│                        │  CEO      │ ← Admin on all beads    │
│                        └─────┬─────┘                         │
│                              │                               │
│           ┌──────────────────┼──────────────────┐           │
│           │                  │                  │           │
│     ┌─────▼─────┐      ┌─────▼─────┐     ┌─────▼─────┐     │
│     │Engineering│      │ Product   │     │ Marketing │     │
│     │   Lead    │      │   Lead    │     │   Lead    │     │
│     └─────┬─────┘      └─────┬─────┘     └─────┬─────┘     │
│           │                  │                  │           │
│     ┌─────▼─────┐      ┌─────▼─────┐     ┌─────▼─────┐     │
│     │  Backend  │      │  Design   │     │  Content  │     │
│     │   Team    │      │   Team    │     │   Team    │     │
│     └───────────┘      └───────────┘     └───────────┘     │
└──────────────────────────────────────────────────────────────┘

Permissions flow DOWN (parent teams can see child team work)
                  └─ Engineering Lead has READ on Backend beads
                  └─ CEO has ADMIN on all beads

Permissions DO NOT flow ACROSS
                  └─ Marketing CANNOT see Engineering beads
                  └─ Unless explicitly granted
```

### Inheritance Rules

| Rule | Description |
|------|-------------|
| **Parent Visibility** | Parent teams have implicit `read` on child team beads |
| **Manager Visibility** | Managers have implicit `read` on direct reports' beads |
| **Owner Write** | Owning team members have implicit `write` on team beads |
| **Assignee Write** | Assigned worker has implicit `write` on assigned beads |
| **Creator Admin** | Bead creator has `admin` on beads they created |
| **Explicit Override** | Direct grants override all implicit permissions |

### Inheritance Resolution Algorithm

```python
def resolve_effective_permission(
    db: Database,
    worker_id: str,
    bead_id: str
) -> PermissionLevel:
    """
    Resolve the effective permission level for a worker on a bead.

    Returns the MAXIMUM of all applicable permission sources.
    """
    permissions = []

    # 1. Check direct grant (highest specificity)
    direct = get_direct_permission(db, worker_id, bead_id)
    if direct:
        permissions.append(direct)

    # 2. Check if worker created the bead (creator gets admin)
    bead = get_bead(db, bead_id)
    if bead.created_by == worker_id:
        permissions.append(PermissionLevel.ADMIN)

    # 3. Check if worker is assigned (assignee gets write)
    if bead.assignee_id == worker_id:
        permissions.append(PermissionLevel.WRITE)

    # 4. Check team ownership
    worker = get_worker(db, worker_id)
    if bead.team_id == worker.team_id:
        # Same team = write access
        permissions.append(PermissionLevel.WRITE)

    # 5. Check if worker's team is parent of bead's team
    if is_ancestor_team(db, worker.team_id, bead.team_id):
        # Parent team = read access
        permissions.append(PermissionLevel.READ)

    # 6. Check manager chain (if worker manages the assignee)
    if bead.assignee_id:
        if is_in_management_chain(db, worker_id, bead.assignee_id):
            permissions.append(PermissionLevel.READ)

    # 7. Check role-based permissions (e.g., CEO gets admin everywhere)
    role_permission = get_role_permission(db, worker.role, bead_id)
    if role_permission:
        permissions.append(role_permission)

    # 8. Check team grants (permission granted to worker's team)
    team_grant = get_team_permission(db, worker.team_id, bead_id)
    if team_grant:
        permissions.append(team_grant)

    # Return maximum permission, or NONE if empty
    return max(permissions) if permissions else PermissionLevel.NONE
```

## 4. Team Boundaries

Teams form the primary organizational boundary for permissions. Beads belong to teams, not individuals.

### Team Isolation Model

```
┌─────────────────────────────────────────────────────────────┐
│                      Engineering Team                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   Team Beads                         │   │
│  │  - All team members have WRITE                      │   │
│  │  - Team lead has APPROVE                            │   │
│  │  - Parent team (e.g., VP) has READ                  │   │
│  │  - Other teams have NONE (by default)               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Team Members: [dev-1, dev-2, dev-3]                       │
│  Team Lead: eng-lead                                        │
│  Parent: Executive                                          │
└─────────────────────────────────────────────────────────────┘
```

### Cross-Team Collaboration

When teams need to collaborate, explicit permission grants are required:

```python
# Grant Marketing read access to a specific Engineering bead
grant_permission(
    db,
    bead_id="eng-123",
    grantee_type="team",
    grantee_id="marketing-team",
    level=PermissionLevel.READ
)

# Grant a specific worker write access
grant_permission(
    db,
    bead_id="eng-123",
    grantee_type="worker",
    grantee_id="marketing-analyst-1",
    level=PermissionLevel.COMMENT
)
```

### Team Membership Roles

Workers have roles within their team that affect default permissions:

| Team Role | Default Permission on Team Beads |
|-----------|----------------------------------|
| `member` | WRITE |
| `lead` | APPROVE |
| `admin` | ADMIN |

```sql
-- Team membership with roles
INSERT INTO team_members (team_id, worker_id, role)
VALUES ('engineering', 'dev-1', 'member');

INSERT INTO team_members (team_id, worker_id, role)
VALUES ('engineering', 'eng-lead', 'lead');
```

## 5. Action Mapping

Every action in the system maps to a required permission level.

### Bead Actions

| Action | Required Level | Notes |
|--------|----------------|-------|
| `list` (own team) | READ | Filter results by permission |
| `list` (other team) | READ | Only shows if granted |
| `show` | READ | View bead details |
| `subscribe` | READ | Watch for updates |
| `comment` | COMMENT | Add comments |
| `create` | WRITE | Creates in worker's team |
| `update` | WRITE | Modify content, labels |
| `assign` | WRITE | Change assignee |
| `link` | WRITE | Add dependencies |
| `transition` | WRITE | Change lifecycle state |
| `approve` | APPROVE | Mark as approved |
| `reject` | APPROVE | Mark as rejected |
| `close` | APPROVE | Close the bead |
| `reopen` | APPROVE | Reopen closed bead |
| `delete` | ADMIN | Soft delete |
| `purge` | ADMIN | Hard delete |
| `grant_permission` | ADMIN | Add permissions |
| `revoke_permission` | ADMIN | Remove permissions |
| `transfer_team` | ADMIN | Move to another team |

### Message Actions

| Action | Required Level | Notes |
|--------|----------------|-------|
| `read_channel` | READ | Based on channel permissions |
| `send_message` | COMMENT | Must be channel member |
| `edit_own_message` | COMMENT | Can edit own messages |
| `delete_own_message` | COMMENT | Can delete own messages |
| `pin_message` | WRITE | Requires write on channel |
| `delete_any_message` | ADMIN | Requires admin on channel |

### Worker Actions (Org-Level)

| Action | Required Role | Notes |
|--------|---------------|-------|
| `hire` | Manager of target team | Uses budget, creates worker |
| `fire` | Manager of worker | Starts offboarding |
| `promote` | Manager's manager | Elevates role |
| `transfer` | Both team managers | Moves between teams |

## 6. Cache Strategy

Permission lookups happen frequently. A multi-layer caching strategy minimizes database hits.

### Cache Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    L1: Request Cache                         │
│  - In-memory dict per request/operation                      │
│  - TTL: Request lifetime (single operation)                  │
│  - Hit rate: ~80% (same bead checked multiple times)        │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    L2: Worker Session Cache                  │
│  - In-memory dict per worker session                        │
│  - TTL: 5 minutes (configurable)                            │
│  - Stores: worker's team ancestry, role permissions         │
│  - Invalidated on: team change, role change                 │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    L3: Precomputed Effective Permissions     │
│  - Database table: effective_permissions                    │
│  - Updated on: permission grant/revoke, team change         │
│  - Indexed for fast lookup                                  │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    L4: Source Tables                         │
│  - permissions, teams, team_members, workers                │
│  - Only hit on cache miss or invalidation                   │
└──────────────────────────────────────────────────────────────┘
```

### Cache Implementation

```python
from functools import lru_cache
from typing import Optional
from datetime import datetime, timedelta


class PermissionCache:
    """Multi-layer permission cache for a worker session."""

    def __init__(self, db: Database, worker_id: str, ttl_seconds: int = 300):
        self.db = db
        self.worker_id = worker_id
        self.ttl = timedelta(seconds=ttl_seconds)

        # L1: Request-level cache (cleared per operation)
        self._request_cache: dict[str, PermissionLevel] = {}

        # L2: Session-level cache (persists across operations)
        self._session_cache: dict[str, tuple[PermissionLevel, datetime]] = {}

        # Precomputed worker context (team ancestry, role)
        self._worker_context: Optional[WorkerContext] = None
        self._context_loaded_at: Optional[datetime] = None

    def get_permission(self, bead_id: str) -> PermissionLevel:
        """Get effective permission for bead, using cache layers."""

        # L1: Check request cache
        if bead_id in self._request_cache:
            return self._request_cache[bead_id]

        # L2: Check session cache (with TTL)
        if bead_id in self._session_cache:
            level, cached_at = self._session_cache[bead_id]
            if datetime.now() - cached_at < self.ttl:
                self._request_cache[bead_id] = level
                return level

        # L3: Check precomputed table
        precomputed = self._get_precomputed(bead_id)
        if precomputed is not None:
            self._cache_result(bead_id, precomputed)
            return precomputed

        # L4: Compute from source tables
        computed = resolve_effective_permission(
            self.db, self.worker_id, bead_id
        )
        self._cache_result(bead_id, computed)
        return computed

    def _cache_result(self, bead_id: str, level: PermissionLevel) -> None:
        """Store result in both cache layers."""
        self._request_cache[bead_id] = level
        self._session_cache[bead_id] = (level, datetime.now())

    def _get_precomputed(self, bead_id: str) -> Optional[PermissionLevel]:
        """Check precomputed effective_permissions table."""
        row = self.db.fetchone(
            """SELECT level FROM effective_permissions
               WHERE worker_id = ? AND bead_id = ?""",
            (self.worker_id, bead_id)
        )
        return PermissionLevel(row['level']) if row else None

    def invalidate(self, bead_id: Optional[str] = None) -> None:
        """Invalidate cache entries."""
        if bead_id:
            self._request_cache.pop(bead_id, None)
            self._session_cache.pop(bead_id, None)
        else:
            self._request_cache.clear()
            self._session_cache.clear()

    def clear_request_cache(self) -> None:
        """Clear L1 cache (call at start of new operation)."""
        self._request_cache.clear()

    def get_worker_context(self) -> 'WorkerContext':
        """Get cached worker context (team ancestry, role)."""
        if self._worker_context is None or self._is_context_stale():
            self._worker_context = self._load_worker_context()
            self._context_loaded_at = datetime.now()
        return self._worker_context

    def _is_context_stale(self) -> bool:
        """Check if worker context needs refresh."""
        if self._context_loaded_at is None:
            return True
        return datetime.now() - self._context_loaded_at > self.ttl

    def _load_worker_context(self) -> 'WorkerContext':
        """Load worker context from database."""
        worker = get_worker(self.db, self.worker_id)
        team_ancestry = get_team_ancestry(self.db, worker.team_id)
        team_role = get_team_role(self.db, worker.team_id, self.worker_id)

        return WorkerContext(
            worker_id=self.worker_id,
            team_id=worker.team_id,
            team_ancestry=team_ancestry,
            team_role=team_role,
            org_role=worker.role
        )


@dataclass
class WorkerContext:
    """Cached worker context for permission resolution."""
    worker_id: str
    team_id: str
    team_ancestry: list[str]  # [parent_id, grandparent_id, ...]
    team_role: str  # member, lead, admin
    org_role: str   # CEO, Manager, Developer, etc.
```

### Cache Invalidation

Cache invalidation occurs on specific events:

| Event | Invalidation Scope |
|-------|-------------------|
| Permission grant/revoke | Specific bead + grantee |
| Team membership change | Worker's entire cache |
| Team hierarchy change | All workers in affected teams |
| Worker role change | Worker's entire cache |
| Bead team transfer | All workers who had access |

```python
def invalidate_on_permission_change(
    db: Database,
    bead_id: str,
    grantee_type: str,
    grantee_id: str
) -> None:
    """Invalidate caches when permission changes."""

    if grantee_type == 'worker':
        # Invalidate specific worker's cache for this bead
        invalidate_worker_bead_cache(db, grantee_id, bead_id)

    elif grantee_type == 'team':
        # Invalidate all team members' caches for this bead
        members = get_team_members(db, grantee_id)
        for member in members:
            invalidate_worker_bead_cache(db, member.worker_id, bead_id)

    # Also update precomputed table
    recompute_effective_permissions(db, bead_id)
```

## 7. SQL Schema

### Permission Tables

```sql
-- ===================
-- PERMISSION TABLES
-- ===================

-- Team membership with roles
CREATE TABLE IF NOT EXISTS team_members (
    team_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('member', 'lead', 'admin')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, worker_id),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_team_members_worker ON team_members(worker_id);

-- Direct permission grants
CREATE TABLE IF NOT EXISTS permissions (
    id TEXT PRIMARY KEY,
    bead_id TEXT NOT NULL,
    grantee_type TEXT NOT NULL CHECK(grantee_type IN ('worker', 'team', 'role')),
    grantee_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level >= 0 AND level <= 5),
    granted_by TEXT NOT NULL,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,  -- NULL = never expires
    UNIQUE(bead_id, grantee_type, grantee_id),
    FOREIGN KEY (granted_by) REFERENCES workers(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_permissions_bead ON permissions(bead_id);
CREATE INDEX IF NOT EXISTS idx_permissions_grantee ON permissions(grantee_type, grantee_id);
CREATE INDEX IF NOT EXISTS idx_permissions_expires ON permissions(expires_at)
    WHERE expires_at IS NOT NULL;

-- Precomputed effective permissions (cache table)
CREATE TABLE IF NOT EXISTS effective_permissions (
    worker_id TEXT NOT NULL,
    bead_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level >= 0 AND level <= 5),
    computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (worker_id, bead_id),
    FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_effective_perm_level ON effective_permissions(level);

-- Permission audit log
CREATE TABLE IF NOT EXISTS permission_audit (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK(action IN ('grant', 'revoke', 'check', 'deny')),
    bead_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    level INTEGER,
    details TEXT,  -- JSON with additional context
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_perm_audit_bead ON permission_audit(bead_id);
CREATE INDEX IF NOT EXISTS idx_perm_audit_worker ON permission_audit(worker_id);
CREATE INDEX IF NOT EXISTS idx_perm_audit_action ON permission_audit(action);
CREATE INDEX IF NOT EXISTS idx_perm_audit_time ON permission_audit(created_at);
```

### Helper Views

```sql
-- View: Worker's teams (including team ancestry)
CREATE VIEW IF NOT EXISTS worker_team_hierarchy AS
WITH RECURSIVE team_tree AS (
    -- Base: worker's direct team
    SELECT
        tm.worker_id,
        tm.team_id,
        tm.role as team_role,
        t.name as team_name,
        t.parent_team_id,
        0 as depth
    FROM team_members tm
    JOIN teams t ON tm.team_id = t.id

    UNION ALL

    -- Recursive: parent teams
    SELECT
        tt.worker_id,
        t.id as team_id,
        'inherited' as team_role,
        t.name as team_name,
        t.parent_team_id,
        tt.depth + 1
    FROM team_tree tt
    JOIN teams t ON tt.parent_team_id = t.id
)
SELECT * FROM team_tree;

-- View: Bead permissions summary
CREATE VIEW IF NOT EXISTS bead_permission_summary AS
SELECT
    p.bead_id,
    p.grantee_type,
    p.grantee_id,
    p.level,
    CASE p.level
        WHEN 0 THEN 'none'
        WHEN 1 THEN 'read'
        WHEN 2 THEN 'comment'
        WHEN 3 THEN 'write'
        WHEN 4 THEN 'approve'
        WHEN 5 THEN 'admin'
    END as level_name,
    p.granted_by,
    w.name as granted_by_name,
    p.granted_at,
    p.expires_at
FROM permissions p
LEFT JOIN workers w ON p.granted_by = w.id;
```

## 8. Python Implementation

### Permission Decorator

```python
# cli/core/permissions.py

from enum import IntEnum
from functools import wraps
from typing import Callable, Optional
from dataclasses import dataclass


class PermissionLevel(IntEnum):
    """Permission levels in ascending order of capability."""
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
        bead_id: str,
        required: PermissionLevel,
        actual: PermissionLevel,
        action: str
    ):
        self.worker_id = worker_id
        self.bead_id = bead_id
        self.required = required
        self.actual = actual
        self.action = action
        super().__init__(
            f"Permission denied: '{action}' requires {required.name} "
            f"but worker '{worker_id}' has {actual.name} on bead '{bead_id}'"
        )


def requires_permission(level: PermissionLevel, audit: bool = True):
    """
    Decorator to enforce permission level on bead operations.

    The decorated function MUST have:
    - 'self' with 'worker_id' and '_permission_cache' attributes
    - 'bead_id' as first positional arg or keyword arg

    Usage:
        @requires_permission(PermissionLevel.WRITE)
        def update_bead(self, bead_id: str, **updates):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, bead_id: str, *args, **kwargs):
            # Get effective permission from cache
            actual = self._permission_cache.get_permission(bead_id)

            # Check permission
            if actual < level:
                # Audit the denial
                if audit:
                    log_permission_denial(
                        self.db,
                        self.worker_id,
                        bead_id,
                        level,
                        actual,
                        func.__name__
                    )

                raise PermissionDenied(
                    worker_id=self.worker_id,
                    bead_id=bead_id,
                    required=level,
                    actual=actual,
                    action=func.__name__
                )

            # Audit successful check (optional, for debugging)
            if audit:
                log_permission_check(
                    self.db,
                    self.worker_id,
                    bead_id,
                    level,
                    actual,
                    func.__name__
                )

            # Execute the function
            return func(self, bead_id, *args, **kwargs)

        return wrapper
    return decorator


def log_permission_denial(
    db: Database,
    worker_id: str,
    bead_id: str,
    required: PermissionLevel,
    actual: PermissionLevel,
    action: str
) -> None:
    """Log permission denial for audit."""
    import json
    import uuid

    db.execute(
        """INSERT INTO permission_audit
           (id, action, bead_id, worker_id, level, details)
           VALUES (?, 'deny', ?, ?, ?, ?)""",
        (
            str(uuid.uuid4()),
            bead_id,
            worker_id,
            required,
            json.dumps({
                'action': action,
                'required': required.name,
                'actual': actual.name
            })
        )
    )
    db.connection.commit()


def log_permission_check(
    db: Database,
    worker_id: str,
    bead_id: str,
    required: PermissionLevel,
    actual: PermissionLevel,
    action: str
) -> None:
    """Log successful permission check (disabled by default for performance)."""
    # Only log in debug mode to avoid filling audit table
    pass
```

### Permission Service

```python
# cli/core/permission_service.py

from typing import Optional, List
from dataclasses import dataclass
import uuid

from .db import Database
from .permissions import PermissionLevel, PermissionDenied, requires_permission
from .cache import PermissionCache


@dataclass
class PermissionGrant:
    """A permission grant record."""
    id: str
    bead_id: str
    grantee_type: str  # 'worker', 'team', 'role'
    grantee_id: str
    level: PermissionLevel
    granted_by: str
    granted_at: str
    expires_at: Optional[str]


class PermissionService:
    """Service for managing permissions."""

    def __init__(self, db: Database, worker_id: str):
        self.db = db
        self.worker_id = worker_id
        self._permission_cache = PermissionCache(db, worker_id)

    def can(self, bead_id: str, level: PermissionLevel) -> bool:
        """Check if current worker has at least the given permission level."""
        actual = self._permission_cache.get_permission(bead_id)
        return actual >= level

    def get_effective_permission(self, bead_id: str) -> PermissionLevel:
        """Get the effective permission level for current worker on a bead."""
        return self._permission_cache.get_permission(bead_id)

    @requires_permission(PermissionLevel.ADMIN)
    def grant(
        self,
        bead_id: str,
        grantee_type: str,
        grantee_id: str,
        level: PermissionLevel,
        expires_at: Optional[str] = None
    ) -> PermissionGrant:
        """
        Grant permission on a bead.

        Requires ADMIN permission on the bead.
        """
        grant_id = str(uuid.uuid4())

        self.db.execute(
            """INSERT OR REPLACE INTO permissions
               (id, bead_id, grantee_type, grantee_id, level, granted_by, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (grant_id, bead_id, grantee_type, grantee_id, level,
             self.worker_id, expires_at)
        )
        self.db.connection.commit()

        # Invalidate caches
        self._invalidate_on_grant(bead_id, grantee_type, grantee_id)

        # Audit
        self._audit('grant', bead_id, level, {
            'grantee_type': grantee_type,
            'grantee_id': grantee_id
        })

        return PermissionGrant(
            id=grant_id,
            bead_id=bead_id,
            grantee_type=grantee_type,
            grantee_id=grantee_id,
            level=level,
            granted_by=self.worker_id,
            granted_at=str(datetime.now()),
            expires_at=expires_at
        )

    @requires_permission(PermissionLevel.ADMIN)
    def revoke(
        self,
        bead_id: str,
        grantee_type: str,
        grantee_id: str
    ) -> bool:
        """
        Revoke permission on a bead.

        Requires ADMIN permission on the bead.
        Returns True if a permission was revoked, False if none existed.
        """
        cursor = self.db.execute(
            """DELETE FROM permissions
               WHERE bead_id = ? AND grantee_type = ? AND grantee_id = ?""",
            (bead_id, grantee_type, grantee_id)
        )
        self.db.connection.commit()

        if cursor.rowcount > 0:
            # Invalidate caches
            self._invalidate_on_grant(bead_id, grantee_type, grantee_id)

            # Audit
            self._audit('revoke', bead_id, None, {
                'grantee_type': grantee_type,
                'grantee_id': grantee_id
            })
            return True

        return False

    def list_permissions(self, bead_id: str) -> List[PermissionGrant]:
        """List all permission grants for a bead."""
        # Check read access first
        if not self.can(bead_id, PermissionLevel.READ):
            raise PermissionDenied(
                self.worker_id, bead_id,
                PermissionLevel.READ,
                PermissionLevel.NONE,
                'list_permissions'
            )

        rows = self.db.fetchall(
            """SELECT * FROM permissions WHERE bead_id = ?""",
            (bead_id,)
        )

        return [
            PermissionGrant(
                id=row['id'],
                bead_id=row['bead_id'],
                grantee_type=row['grantee_type'],
                grantee_id=row['grantee_id'],
                level=PermissionLevel(row['level']),
                granted_by=row['granted_by'],
                granted_at=row['granted_at'],
                expires_at=row['expires_at']
            )
            for row in rows
        ]

    def _invalidate_on_grant(
        self,
        bead_id: str,
        grantee_type: str,
        grantee_id: str
    ) -> None:
        """Invalidate caches after permission change."""
        # Recompute effective permissions
        recompute_effective_permissions(self.db, bead_id)

    def _audit(
        self,
        action: str,
        bead_id: str,
        level: Optional[PermissionLevel],
        details: dict
    ) -> None:
        """Record audit entry."""
        import json

        self.db.execute(
            """INSERT INTO permission_audit
               (id, action, bead_id, worker_id, level, details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                action,
                bead_id,
                self.worker_id,
                level,
                json.dumps(details)
            )
        )
        self.db.connection.commit()
```

### Inheritance Resolution Implementation

```python
# cli/core/permission_resolver.py

from typing import List, Optional, Set
from .db import Database
from .permissions import PermissionLevel


def resolve_effective_permission(
    db: Database,
    worker_id: str,
    bead_id: str
) -> PermissionLevel:
    """
    Resolve the effective permission level for a worker on a bead.

    Algorithm:
    1. Collect all applicable permission sources
    2. Return the maximum permission level

    Sources (in order of evaluation):
    - Direct worker grant
    - Team grant (for worker's teams)
    - Role grant
    - Bead creator (admin)
    - Bead assignee (write)
    - Team ownership (write for same team)
    - Parent team visibility (read for parent teams)
    - Manager chain visibility (read for managers)
    """
    permissions: List[PermissionLevel] = []

    # Get worker context
    worker = _get_worker(db, worker_id)
    if not worker:
        return PermissionLevel.NONE

    # Get bead context
    bead = _get_bead(db, bead_id)
    if not bead:
        return PermissionLevel.NONE

    # 1. Direct worker grant
    direct = _get_direct_grant(db, bead_id, 'worker', worker_id)
    if direct is not None:
        permissions.append(direct)

    # 2. Team grants (check all teams worker belongs to)
    worker_teams = _get_worker_teams(db, worker_id)
    for team_id in worker_teams:
        team_grant = _get_direct_grant(db, bead_id, 'team', team_id)
        if team_grant is not None:
            permissions.append(team_grant)

    # 3. Role grant
    role_grant = _get_direct_grant(db, bead_id, 'role', worker['role'])
    if role_grant is not None:
        permissions.append(role_grant)

    # 4. Bead creator gets admin
    if bead.get('created_by') == worker_id:
        permissions.append(PermissionLevel.ADMIN)

    # 5. Bead assignee gets write
    if bead.get('assignee_id') == worker_id:
        permissions.append(PermissionLevel.WRITE)

    # 6. Same team = write (for primary team only)
    if bead.get('team_id') == worker['team_id']:
        # Check team role for higher permissions
        team_role = _get_team_role(db, worker['team_id'], worker_id)
        if team_role == 'admin':
            permissions.append(PermissionLevel.ADMIN)
        elif team_role == 'lead':
            permissions.append(PermissionLevel.APPROVE)
        else:
            permissions.append(PermissionLevel.WRITE)

    # 7. Parent team = read
    bead_team_ancestry = _get_team_ancestry(db, bead.get('team_id'))
    if worker['team_id'] in bead_team_ancestry:
        permissions.append(PermissionLevel.READ)

    # 8. Manager chain = read
    if bead.get('assignee_id'):
        if _is_in_management_chain(db, worker_id, bead['assignee_id']):
            permissions.append(PermissionLevel.READ)

    # 9. CEO gets admin on everything
    if worker['role'] == 'CEO':
        permissions.append(PermissionLevel.ADMIN)

    # Return maximum, or NONE if empty
    return max(permissions) if permissions else PermissionLevel.NONE


def _get_worker(db: Database, worker_id: str) -> Optional[dict]:
    """Get worker record."""
    row = db.fetchone("SELECT * FROM workers WHERE id = ?", (worker_id,))
    return dict(row) if row else None


def _get_bead(db: Database, bead_id: str) -> Optional[dict]:
    """Get bead record (from beads table)."""
    # Note: This assumes beads are in the same database
    # Adjust if beads are stored differently
    row = db.fetchone("SELECT * FROM beads WHERE id = ?", (bead_id,))
    return dict(row) if row else None


def _get_direct_grant(
    db: Database,
    bead_id: str,
    grantee_type: str,
    grantee_id: str
) -> Optional[PermissionLevel]:
    """Get direct permission grant."""
    row = db.fetchone(
        """SELECT level FROM permissions
           WHERE bead_id = ? AND grantee_type = ? AND grantee_id = ?
           AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)""",
        (bead_id, grantee_type, grantee_id)
    )
    return PermissionLevel(row['level']) if row else None


def _get_worker_teams(db: Database, worker_id: str) -> List[str]:
    """Get all teams a worker belongs to."""
    rows = db.fetchall(
        "SELECT team_id FROM team_members WHERE worker_id = ?",
        (worker_id,)
    )
    return [row['team_id'] for row in rows]


def _get_team_role(db: Database, team_id: str, worker_id: str) -> str:
    """Get worker's role within a team."""
    row = db.fetchone(
        "SELECT role FROM team_members WHERE team_id = ? AND worker_id = ?",
        (team_id, worker_id)
    )
    return row['role'] if row else 'member'


def _get_team_ancestry(db: Database, team_id: str) -> List[str]:
    """Get all ancestor team IDs (parent, grandparent, etc.)."""
    ancestors = []
    current = team_id

    while current:
        row = db.fetchone(
            "SELECT parent_team_id FROM teams WHERE id = ?",
            (current,)
        )
        if row and row['parent_team_id']:
            ancestors.append(row['parent_team_id'])
            current = row['parent_team_id']
        else:
            break

    return ancestors


def _is_in_management_chain(db: Database, manager_id: str, worker_id: str) -> bool:
    """Check if manager_id is in the management chain of worker_id."""
    current = worker_id
    visited: Set[str] = set()

    while current and current not in visited:
        visited.add(current)
        row = db.fetchone(
            "SELECT manager_id FROM workers WHERE id = ?",
            (current,)
        )
        if row and row['manager_id']:
            if row['manager_id'] == manager_id:
                return True
            current = row['manager_id']
        else:
            break

    return False


def recompute_effective_permissions(db: Database, bead_id: str) -> None:
    """
    Recompute effective permissions for a bead.

    Called after permission grants/revokes to update the cache table.
    """
    # Get all workers who might have access
    # (This could be optimized to only check relevant workers)
    workers = db.fetchall("SELECT id FROM workers WHERE status != 'terminated'")

    # Clear existing computed permissions for this bead
    db.execute(
        "DELETE FROM effective_permissions WHERE bead_id = ?",
        (bead_id,)
    )

    # Recompute for each worker
    for worker in workers:
        level = resolve_effective_permission(db, worker['id'], bead_id)
        if level > PermissionLevel.NONE:
            db.execute(
                """INSERT INTO effective_permissions (worker_id, bead_id, level)
                   VALUES (?, ?, ?)""",
                (worker['id'], bead_id, level)
            )

    db.connection.commit()
```

## 9. Usage Examples

### CLI Integration

```python
# cli/commands/bd/update.py

@click.command()
@click.argument('bead_id')
@click.option('--status', help='New status')
@click.option('--title', help='New title')
@pass_context
def update(ctx, bead_id: str, status: str, title: str):
    """Update a bead."""
    db = ctx.obj['db']
    worker_id = ctx.obj['worker_id']

    service = BeadService(db, worker_id)

    try:
        bead = service.update_bead(
            bead_id,
            status=status,
            title=title
        )
        click.echo(f"Updated bead {bead.id}")

    except PermissionDenied as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
```

### Worker Session Integration

```python
# In worker session initialization

class WorkerSession:
    def __init__(self, db: Database, worker_id: str):
        self.db = db
        self.worker_id = worker_id

        # Initialize permission cache for this session
        self._permission_cache = PermissionCache(db, worker_id)

        # Services with permission enforcement
        self.beads = BeadService(db, worker_id)
        self.permissions = PermissionService(db, worker_id)

    def refresh_permissions(self):
        """Force refresh of permission cache."""
        self._permission_cache.invalidate()
```

## 10. Performance Considerations

### Expected Performance

| Operation | Target Latency | Cache Hit | Cache Miss |
|-----------|----------------|-----------|------------|
| Permission check (L1 hit) | < 1ms | 80% | - |
| Permission check (L2 hit) | < 5ms | 15% | - |
| Permission check (L3/L4) | < 50ms | 5% | Full resolution |
| Grant/revoke | < 100ms | - | Includes invalidation |
| Precomputation (per bead) | < 500ms | - | Background job |

### Optimization Strategies

1. **Batch Permission Checks**: When listing beads, batch permission checks
2. **Precompute on Write**: Update effective_permissions on grant/revoke
3. **Lazy Loading**: Don't compute permissions until needed
4. **Index Everything**: All permission lookups should be indexed

### Monitoring

Track these metrics:
- Cache hit rate by layer (L1, L2, L3)
- Permission check latency (p50, p95, p99)
- Permission denial rate by action
- Cache invalidation frequency

## 11. Migration Path

### Phase 1: Schema Addition
1. Add permission tables to schema
2. Add team_members table
3. Create indexes

### Phase 2: Service Integration
1. Implement PermissionCache
2. Implement requires_permission decorator
3. Add to BeadService

### Phase 3: Enforcement Activation
1. Add permission checks to all bead operations
2. Enable audit logging
3. Monitor for issues

### Phase 4: Optimization
1. Implement precomputed effective_permissions
2. Add batch permission checking
3. Tune cache TTLs based on metrics

## Summary

The permission enforcement system provides:

1. **Hierarchical Levels**: none through admin with clear capability mapping
2. **Service Layer Enforcement**: Single authoritative check point via decorator
3. **Org-Chart Inheritance**: Permissions flow down from parent teams and managers
4. **Team Isolation**: Cross-team access requires explicit grants
5. **Complete Action Mapping**: Every action has a required permission level
6. **Multi-Layer Caching**: L1 (request), L2 (session), L3 (precomputed), L4 (source)
7. **Audit Trail**: All grants, revokes, and denials are logged
8. **Performance**: Sub-50ms permission checks with caching
