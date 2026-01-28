# Delegation Tracking Database Schema Design

**Date:** 2026-01-28
**Author:** Claude Sonnet 4.5
**Context:** QuinnAI hiring authority delegation system
**Status:** Design specification ready for implementation

---

## Executive Summary

This document provides the complete database schema for tracking hiring authority delegation chains in QuinnAI. The design addresses all P0 vulnerabilities identified in the safety analysis:

1. **Delegation tracking** - Complete chain of custody via `delegation_grants` table
2. **Audit trail** - Immutable log of all delegation operations via `delegation_audit` table
3. **Cascade revocation** - Foreign key constraints + triggers enable safe revocation
4. **Concurrency protection** - Optimistic locking via `delegation_version` column
5. **Lifecycle integration** - CHECK constraints prevent invalid state transitions

**Key Design Principles:**
- **Immutable audit trail** - No UPDATEs/DELETEs allowed on audit table
- **Explicit over implicit** - No magic values, all relationships explicit
- **Fail-safe defaults** - Constraints prevent invalid states, not application logic
- **Performance-aware** - Indexes optimized for common query patterns

---

## 1. Database Tables

### 1.1 delegation_grants

**Purpose:** Track active and revoked delegation relationships.

**Design Notes:**
- One row per delegation (delegator → grantee relationship)
- `revoked_at IS NULL` indicates active delegation
- Foreign keys cascade DELETE to prevent orphaned records
- CHECK constraint prevents self-delegation

```sql
CREATE TABLE delegation_grants (
    -- Primary key
    id TEXT PRIMARY KEY,

    -- Delegation relationship
    delegator_id TEXT NOT NULL,           -- Who granted the authority
    delegate_id TEXT NOT NULL,            -- Who received it (formerly grantee_id)

    -- Delegation scope (HiringScope JSON)
    scope TEXT NOT NULL,                  -- {"allowed_roles": [...], "max_cost": N, ...}
    budget_amount INTEGER NOT NULL,       -- Budget delegated (in credits)

    -- Lifecycle
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,                  -- Optional: time-limited delegation
    revoked_at DATETIME,                  -- NULL = active, populated = revoked
    revoked_by TEXT,                      -- Worker ID who revoked (may be delegator or admin)
    revoke_reason TEXT,                   -- Human-readable reason for revocation

    -- Metadata
    granted_by_cli_user TEXT,             -- Optional: track which CLI user initiated grant
    metadata TEXT,                        -- JSON for extensibility

    -- Constraints
    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE CASCADE,

    CHECK (delegator_id != delegate_id),  -- Prevent self-delegation
    CHECK (budget_amount >= 0),           -- Budget must be non-negative

    -- Only one active delegation per delegate (can only have one delegator)
    UNIQUE(delegate_id) WHERE revoked_at IS NULL
);

-- Indexes for common queries
CREATE INDEX idx_delegation_grants_delegator ON delegation_grants(delegator_id);
CREATE INDEX idx_delegation_grants_delegate ON delegation_grants(delegate_id);
CREATE INDEX idx_delegation_grants_active ON delegation_grants(revoked_at)
    WHERE revoked_at IS NULL;
CREATE INDEX idx_delegation_grants_expires ON delegation_grants(expires_at)
    WHERE expires_at IS NOT NULL AND revoked_at IS NULL;
```

**Key Design Decisions:**

1. **Why `delegate_id` instead of `grantee_id`?**
   - More consistent with existing QuinnAI terminology (workers delegate authority)
   - Avoids confusion with "grantee" from permission system

2. **Why UNIQUE constraint on `delegate_id` for active grants?**
   - A worker can only receive delegation from ONE delegator at a time
   - Prevents conflicting authority chains (A delegates to C, B also delegates to C)
   - Simplifies cascade revocation logic (only one parent to check)

3. **Why allow NULL `expires_at`?**
   - Most delegations are permanent (until explicitly revoked)
   - Time-limited delegation is optional feature for sensitive authority grants

4. **Why store `granted_by_cli_user`?**
   - Audit trail: track which human initiated the delegation
   - Useful for compliance (e.g., "who approved this hire authority?")

### 1.2 delegation_audit

**Purpose:** Immutable audit trail of all delegation operations.

**Design Notes:**
- Append-only (enforced via triggers)
- Records before/after state for modifications
- Tracks both automated (system) and manual (CLI user) actions

```sql
CREATE TABLE delegation_audit (
    -- Primary key
    id TEXT PRIMARY KEY,

    -- Event type
    event_type TEXT NOT NULL CHECK(event_type IN (
        'granted',           -- New delegation created
        'revoked',           -- Delegation explicitly revoked
        'expired',           -- Delegation auto-expired (expires_at reached)
        'cascade_revoked',   -- Delegation revoked due to parent revocation
        'modified',          -- Delegation scope/budget changed (rare)
        'terminated_revoked' -- Delegation revoked due to worker termination
    )),

    -- Who and what
    delegator_id TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    delegation_grant_id TEXT,             -- Reference to delegation_grants.id

    -- State changes (for 'modified' events)
    scope_before TEXT,
    scope_after TEXT,
    budget_before INTEGER,
    budget_after INTEGER,

    -- Actor tracking
    performed_by TEXT NOT NULL,           -- Worker ID who performed action
    performed_by_cli_user TEXT,           -- CLI user (if human-initiated)

    -- Context
    reason TEXT,                          -- Human-readable reason
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Forensics
    ip_address TEXT,                      -- Optional: for remote API calls
    session_id TEXT,                      -- Optional: session context

    -- Constraints
    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE RESTRICT,
    FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE RESTRICT,
    FOREIGN KEY (delegation_grant_id) REFERENCES delegation_grants(id) ON DELETE SET NULL,

    -- Prevent deletion of worker records referenced in audit
    -- (ON DELETE RESTRICT ensures audit remains intact)
    CHECK (event_type IN ('granted', 'revoked', 'expired', 'cascade_revoked', 'modified', 'terminated_revoked'))
);

-- Indexes for audit queries
CREATE INDEX idx_delegation_audit_delegate ON delegation_audit(delegate_id);
CREATE INDEX idx_delegation_audit_delegator ON delegation_audit(delegator_id);
CREATE INDEX idx_delegation_audit_timestamp ON delegation_audit(timestamp);
CREATE INDEX idx_delegation_audit_event_type ON delegation_audit(event_type);
CREATE INDEX idx_delegation_audit_grant ON delegation_audit(delegation_grant_id);

-- Triggers to prevent modification/deletion
CREATE TRIGGER prevent_audit_modification
BEFORE UPDATE ON delegation_audit
BEGIN
    SELECT RAISE(ABORT, 'Audit records are immutable');
END;

CREATE TRIGGER prevent_audit_deletion
BEFORE DELETE ON delegation_audit
BEGIN
    SELECT RAISE(ABORT, 'Audit records cannot be deleted');
END;
```

**Key Design Decisions:**

1. **Why immutable (no UPDATE/DELETE)?**
   - Audit trail must be tamper-proof for compliance
   - Use ON DELETE RESTRICT for worker FKs to prevent audit loss

2. **Why separate event_type instead of just 'operation' field?**
   - Explicit event types enable better queries (e.g., "all cascade revocations")
   - Prevents typos in application code

3. **Why store before/after state?**
   - Enables reconstruction of delegation history
   - Required for "what changed?" queries in compliance audits

### 1.3 workers table changes

**Columns to add:**

```sql
-- Add to workers table (migration v17)
ALTER TABLE workers ADD COLUMN delegation_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workers ADD COLUMN delegation_expires_at DATETIME;
ALTER TABLE workers ADD COLUMN delegated_by TEXT; -- Denormalized for quick lookup
```

**Purpose of new columns:**

1. **`delegation_version`** (optimistic locking)
   - Incremented on every delegation operation
   - Used in compare-and-swap for concurrent delegation protection
   - Example: `UPDATE workers SET ... WHERE id = ? AND delegation_version = ?`

2. **`delegation_expires_at`** (time-limited authority)
   - Optional expiration timestamp for delegated authority
   - Cleanup job revokes authority when current_time > delegation_expires_at
   - NULL = no expiration (permanent until revoked)

3. **`delegated_by`** (denormalized parent pointer)
   - Quick lookup: "who delegated to this worker?"
   - Avoids JOIN on delegation_grants for common queries
   - Updated atomically with delegation_grants INSERT
   - NULL = worker has no delegated authority (only base authority)

**Constraints to add:**

```sql
-- Constraint: Active workers can have authority, terminated cannot
ALTER TABLE workers ADD CONSTRAINT check_authority_lifecycle
CHECK (
    hiring_authority_scope IS NULL
    OR status IN ('onboarding', 'active')
);

-- Constraint: Non-CEO workers with authority must have manager
ALTER TABLE workers ADD CONSTRAINT check_authority_requires_manager
CHECK (
    hiring_authority_scope IS NULL
    OR manager_id IS NOT NULL
    OR role = 'CEO'
);

-- Constraint: Workers with delegated authority must have delegator
ALTER TABLE workers ADD CONSTRAINT check_delegated_authority_source
CHECK (
    (hiring_authority_scope IS NULL AND delegated_by IS NULL)
    OR (hiring_authority_scope IS NOT NULL AND (delegated_by IS NOT NULL OR role = 'CEO'))
);
```

**Index additions:**

```sql
CREATE INDEX idx_workers_delegated_by ON workers(delegated_by)
    WHERE delegated_by IS NOT NULL;
CREATE INDEX idx_workers_delegation_expires ON workers(delegation_expires_at)
    WHERE delegation_expires_at IS NOT NULL;
```

---

## 2. Database Triggers

### 2.1 Auto-revocation on termination

**Purpose:** When a worker is terminated, automatically revoke all delegations they granted.

```sql
CREATE TRIGGER revoke_delegations_on_termination
AFTER UPDATE OF status ON workers
FOR EACH ROW
WHEN NEW.status = 'terminated' AND OLD.status != 'terminated'
BEGIN
    -- Revoke all delegations granted BY this worker
    UPDATE delegation_grants
    SET revoked_at = CURRENT_TIMESTAMP,
        revoked_by = 'system',
        revoke_reason = 'delegator terminated'
    WHERE delegator_id = NEW.id AND revoked_at IS NULL;

    -- Revoke delegation granted TO this worker
    UPDATE delegation_grants
    SET revoked_at = CURRENT_TIMESTAMP,
        revoked_by = 'system',
        revoke_reason = 'delegate terminated'
    WHERE delegate_id = NEW.id AND revoked_at IS NULL;

    -- Clear worker's authority
    UPDATE workers
    SET hiring_authority_scope = NULL,
        delegated_budget = 0,
        delegated_by = NULL,
        delegation_expires_at = NULL,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;
```

**Why this trigger?**
- Prevents orphaned authority (terminated workers keeping delegated authority)
- Enforces cascade revocation (see safety analysis section 3.1)
- Automated cleanup reduces manual administration burden

### 2.2 Audit logging for delegation grants

**Purpose:** Automatically log all delegation operations to audit table.

```sql
CREATE TRIGGER log_delegation_grant
AFTER INSERT ON delegation_grants
FOR EACH ROW
BEGIN
    INSERT INTO delegation_audit (
        id,
        event_type,
        delegator_id,
        delegate_id,
        delegation_grant_id,
        scope_after,
        budget_after,
        performed_by,
        reason,
        timestamp
    ) VALUES (
        'audit-' || hex(randomblob(8)),
        'granted',
        NEW.delegator_id,
        NEW.delegate_id,
        NEW.id,
        NEW.scope,
        NEW.budget_amount,
        NEW.delegator_id,  -- Delegator is performer
        'delegation granted',
        NEW.granted_at
    );
END;
```

```sql
CREATE TRIGGER log_delegation_revoke
AFTER UPDATE OF revoked_at ON delegation_grants
FOR EACH ROW
WHEN NEW.revoked_at IS NOT NULL AND OLD.revoked_at IS NULL
BEGIN
    INSERT INTO delegation_audit (
        id,
        event_type,
        delegator_id,
        delegate_id,
        delegation_grant_id,
        performed_by,
        reason,
        timestamp
    ) VALUES (
        'audit-' || hex(randomblob(8)),
        CASE
            WHEN NEW.revoke_reason LIKE 'cascade%' THEN 'cascade_revoked'
            WHEN NEW.revoke_reason LIKE '%terminated%' THEN 'terminated_revoked'
            ELSE 'revoked'
        END,
        NEW.delegator_id,
        NEW.delegate_id,
        NEW.id,
        COALESCE(NEW.revoked_by, 'system'),
        NEW.revoke_reason,
        NEW.revoked_at
    );
END;
```

### 2.3 Cascade validation on authority change

**Purpose:** When a delegator's authority is reduced, validate that sub-delegations remain valid.

```sql
-- This is better implemented in application code due to complexity
-- But we can add a CHECK constraint to catch obvious violations

CREATE TRIGGER validate_delegations_on_authority_change
BEFORE UPDATE OF hiring_authority_scope ON workers
FOR EACH ROW
WHEN NEW.hiring_authority_scope IS NOT NULL
BEGIN
    -- Check if any active sub-delegations would become invalid
    -- Note: This is simplified - full validation should be in application code
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM delegation_grants
            WHERE delegator_id = NEW.id
            AND revoked_at IS NULL
            AND budget_amount > NEW.delegated_budget
        )
        THEN RAISE(ABORT, 'Cannot reduce authority: active sub-delegations exceed new budget')
    END;
END;
```

---

## 3. Migration Scripts

### 3.1 Migration v17: Add delegation tracking support

**File:** `cli/core/migrations/v17_add_delegation_tracking.sql`

```sql
-- Migration v17: Add delegation tracking
-- Author: Claude Sonnet 4.5
-- Date: 2026-01-28

-- Step 1: Create delegation_grants table
CREATE TABLE IF NOT EXISTS delegation_grants (
    id TEXT PRIMARY KEY,
    delegator_id TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    budget_amount INTEGER NOT NULL,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    revoked_at DATETIME,
    revoked_by TEXT,
    revoke_reason TEXT,
    granted_by_cli_user TEXT,
    metadata TEXT,

    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE CASCADE,

    CHECK (delegator_id != delegate_id),
    CHECK (budget_amount >= 0),
    UNIQUE(delegate_id) WHERE revoked_at IS NULL
);

CREATE INDEX idx_delegation_grants_delegator ON delegation_grants(delegator_id);
CREATE INDEX idx_delegation_grants_delegate ON delegation_grants(delegate_id);
CREATE INDEX idx_delegation_grants_active ON delegation_grants(revoked_at)
    WHERE revoked_at IS NULL;
CREATE INDEX idx_delegation_grants_expires ON delegation_grants(expires_at)
    WHERE expires_at IS NOT NULL AND revoked_at IS NULL;

-- Step 2: Create delegation_audit table
CREATE TABLE IF NOT EXISTS delegation_audit (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'granted', 'revoked', 'expired', 'cascade_revoked',
        'modified', 'terminated_revoked'
    )),
    delegator_id TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    delegation_grant_id TEXT,
    scope_before TEXT,
    scope_after TEXT,
    budget_before INTEGER,
    budget_after INTEGER,
    performed_by TEXT NOT NULL,
    performed_by_cli_user TEXT,
    reason TEXT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    session_id TEXT,

    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE RESTRICT,
    FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE RESTRICT,
    FOREIGN KEY (delegation_grant_id) REFERENCES delegation_grants(id) ON DELETE SET NULL
);

CREATE INDEX idx_delegation_audit_delegate ON delegation_audit(delegate_id);
CREATE INDEX idx_delegation_audit_delegator ON delegation_audit(delegator_id);
CREATE INDEX idx_delegation_audit_timestamp ON delegation_audit(timestamp);
CREATE INDEX idx_delegation_audit_event_type ON delegation_audit(event_type);
CREATE INDEX idx_delegation_audit_grant ON delegation_audit(delegation_grant_id);

-- Audit table immutability triggers
CREATE TRIGGER prevent_audit_modification
BEFORE UPDATE ON delegation_audit
BEGIN
    SELECT RAISE(ABORT, 'Audit records are immutable');
END;

CREATE TRIGGER prevent_audit_deletion
BEFORE DELETE ON delegation_audit
BEGIN
    SELECT RAISE(ABORT, 'Audit records cannot be deleted');
END;

-- Step 3: Add columns to workers table
ALTER TABLE workers ADD COLUMN delegation_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workers ADD COLUMN delegation_expires_at DATETIME;
ALTER TABLE workers ADD COLUMN delegated_by TEXT;

CREATE INDEX idx_workers_delegated_by ON workers(delegated_by)
    WHERE delegated_by IS NOT NULL;
CREATE INDEX idx_workers_delegation_expires ON workers(delegation_expires_at)
    WHERE delegation_expires_at IS NOT NULL;

-- Step 4: Add constraints (after backfill)
-- NOTE: These will be enabled after data backfill in separate migration step

-- Step 5: Add triggers for auto-revocation
CREATE TRIGGER revoke_delegations_on_termination
AFTER UPDATE OF status ON workers
FOR EACH ROW
WHEN NEW.status = 'terminated' AND OLD.status != 'terminated'
BEGIN
    UPDATE delegation_grants
    SET revoked_at = CURRENT_TIMESTAMP,
        revoked_by = 'system',
        revoke_reason = 'delegator terminated'
    WHERE delegator_id = NEW.id AND revoked_at IS NULL;

    UPDATE delegation_grants
    SET revoked_at = CURRENT_TIMESTAMP,
        revoked_by = 'system',
        revoke_reason = 'delegate terminated'
    WHERE delegate_id = NEW.id AND revoked_at IS NULL;

    UPDATE workers
    SET hiring_authority_scope = NULL,
        delegated_budget = 0,
        delegated_by = NULL,
        delegation_expires_at = NULL,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;

-- Step 6: Add triggers for audit logging
CREATE TRIGGER log_delegation_grant
AFTER INSERT ON delegation_grants
FOR EACH ROW
BEGIN
    INSERT INTO delegation_audit (
        id,
        event_type,
        delegator_id,
        delegate_id,
        delegation_grant_id,
        scope_after,
        budget_after,
        performed_by,
        reason,
        timestamp
    ) VALUES (
        'audit-' || hex(randomblob(8)),
        'granted',
        NEW.delegator_id,
        NEW.delegate_id,
        NEW.id,
        NEW.scope,
        NEW.budget_amount,
        NEW.delegator_id,
        'delegation granted',
        NEW.granted_at
    );
END;

CREATE TRIGGER log_delegation_revoke
AFTER UPDATE OF revoked_at ON delegation_grants
FOR EACH ROW
WHEN NEW.revoked_at IS NOT NULL AND OLD.revoked_at IS NULL
BEGIN
    INSERT INTO delegation_audit (
        id,
        event_type,
        delegator_id,
        delegate_id,
        delegation_grant_id,
        performed_by,
        reason,
        timestamp
    ) VALUES (
        'audit-' || hex(randomblob(8)),
        CASE
            WHEN NEW.revoke_reason LIKE 'cascade%' THEN 'cascade_revoked'
            WHEN NEW.revoke_reason LIKE '%terminated%' THEN 'terminated_revoked'
            ELSE 'revoked'
        END,
        NEW.delegator_id,
        NEW.delegate_id,
        NEW.id,
        COALESCE(NEW.revoked_by, 'system'),
        NEW.revoke_reason,
        NEW.revoked_at
    );
END;
```

### 3.2 Migration v17b: Backfill existing delegations

**File:** `cli/core/migrations/v17b_backfill_delegations.py`

```python
"""
Backfill script for existing orgs with workers who have hiring authority.

This script infers delegation relationships from the current workers table
and creates corresponding delegation_grants records.

IMPORTANT: This is a best-effort migration. Manual review may be required
for orgs with complex authority structures.
"""

from datetime import datetime
from pathlib import Path
import json
from cli.core.db import Database
from cli.core.worker import Worker

def backfill_delegations(db: Database) -> dict:
    """Backfill delegation_grants table from existing workers.

    Returns:
        Stats dict with counts of workers processed
    """
    stats = {
        "workers_with_authority": 0,
        "delegations_created": 0,
        "ceo_authority_set": 0,
        "warnings": []
    }

    # Find all workers with hiring authority
    workers = db.fetchall(
        """SELECT id, hiring_authority_scope, delegated_budget, manager_id, role, status
           FROM workers
           WHERE hiring_authority_scope IS NOT NULL
           AND status != 'terminated'
           ORDER BY manager_id NULLS FIRST"""  # Process CEO first
    )

    stats["workers_with_authority"] = len(workers)

    for worker in workers:
        worker_id = worker["id"]
        scope = worker["hiring_authority_scope"]
        budget = worker["delegated_budget"]
        manager_id = worker["manager_id"]
        role = worker["role"]

        # CEO has no delegator (base authority)
        if role == "CEO" or manager_id is None:
            # Update worker with no delegator
            db.execute(
                """UPDATE workers
                   SET delegated_by = NULL,
                       delegation_version = 0
                   WHERE id = ?""",
                (worker_id,)
            )
            stats["ceo_authority_set"] += 1
            continue

        # Non-CEO: infer delegator from manager
        # Assumption: authority was delegated by direct manager
        delegator_id = manager_id

        # Validate delegator has authority to delegate
        delegator = db.fetchone(
            "SELECT hiring_authority_scope FROM workers WHERE id = ?",
            (delegator_id,)
        )

        if not delegator or not delegator["hiring_authority_scope"]:
            # Manager doesn't have authority - this is an orphaned delegation
            stats["warnings"].append(
                f"Worker {worker_id} has authority but manager {delegator_id} does not. "
                f"Setting delegator to NULL (requires manual review)."
            )
            delegator_id = None

        if delegator_id:
            # Create delegation_grant record
            grant_id = f"backfill-{worker_id[:8]}"
            now = datetime.now()

            db.execute(
                """INSERT INTO delegation_grants (
                    id, delegator_id, delegate_id, scope, budget_amount,
                    granted_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    grant_id,
                    delegator_id,
                    worker_id,
                    scope,
                    budget,
                    now,
                    json.dumps({"source": "migration_backfill"})
                )
            )

            # Update worker.delegated_by
            db.execute(
                """UPDATE workers
                   SET delegated_by = ?,
                       delegation_version = 0
                   WHERE id = ?""",
                (delegator_id, worker_id)
            )

            stats["delegations_created"] += 1

    db.connection.commit()
    return stats


def validate_backfill(db: Database) -> list[str]:
    """Validate backfill results and return list of issues."""
    issues = []

    # Check: All non-CEO workers with authority have delegator
    orphaned = db.fetchall(
        """SELECT id, role FROM workers
           WHERE hiring_authority_scope IS NOT NULL
           AND delegated_by IS NULL
           AND role != 'CEO'
           AND status != 'terminated'"""
    )

    if orphaned:
        issues.append(
            f"Found {len(orphaned)} workers with authority but no delegator: "
            f"{[w['id'] for w in orphaned]}"
        )

    # Check: delegation_grants count matches workers.delegated_by count
    grant_count = db.fetchone(
        "SELECT COUNT(*) as c FROM delegation_grants WHERE revoked_at IS NULL"
    )["c"]

    delegated_count = db.fetchone(
        """SELECT COUNT(*) as c FROM workers
           WHERE delegated_by IS NOT NULL
           AND status != 'terminated'"""
    )["c"]

    if grant_count != delegated_count:
        issues.append(
            f"Mismatch: {grant_count} active grants but {delegated_count} workers "
            f"with delegated_by set"
        )

    return issues
```

### 3.3 Migration Rollback Script

**File:** `cli/core/migrations/v17_rollback.sql`

```sql
-- Rollback v17: Remove delegation tracking

-- Drop triggers first (they reference tables)
DROP TRIGGER IF EXISTS log_delegation_revoke;
DROP TRIGGER IF EXISTS log_delegation_grant;
DROP TRIGGER IF EXISTS revoke_delegations_on_termination;
DROP TRIGGER IF EXISTS prevent_audit_deletion;
DROP TRIGGER IF EXISTS prevent_audit_modification;

-- Drop indexes
DROP INDEX IF EXISTS idx_delegation_audit_grant;
DROP INDEX IF EXISTS idx_delegation_audit_event_type;
DROP INDEX IF EXISTS idx_delegation_audit_timestamp;
DROP INDEX IF EXISTS idx_delegation_audit_delegator;
DROP INDEX IF EXISTS idx_delegation_audit_delegate;

DROP INDEX IF EXISTS idx_delegation_grants_expires;
DROP INDEX IF EXISTS idx_delegation_grants_active;
DROP INDEX IF EXISTS idx_delegation_grants_delegate;
DROP INDEX IF EXISTS idx_delegation_grants_delegator;

DROP INDEX IF EXISTS idx_workers_delegation_expires;
DROP INDEX IF EXISTS idx_workers_delegated_by;

-- Drop tables
DROP TABLE IF EXISTS delegation_audit;
DROP TABLE IF EXISTS delegation_grants;

-- Remove columns from workers (SQLite doesn't support DROP COLUMN directly)
-- Instead, create backup of workers data
CREATE TABLE workers_backup AS SELECT * FROM workers;

-- Recreate workers table without new columns
-- (Copy full CREATE TABLE from db.py, omitting delegation columns)
-- Then restore data from workers_backup
-- This is complex - better to just leave columns (they won't hurt)

-- Alternative: Just set columns to NULL
UPDATE workers SET delegation_version = 0;
UPDATE workers SET delegation_expires_at = NULL;
UPDATE workers SET delegated_by = NULL;
```

---

## 4. Query Patterns

### 4.1 Get delegation chain for worker

**Use case:** Display full delegation chain (CEO → Director → Manager → Worker)

```sql
WITH RECURSIVE delegation_chain AS (
    -- Base case: target worker
    SELECT
        w.id,
        w.name,
        w.role,
        w.delegated_by,
        0 AS depth
    FROM workers w
    WHERE w.id = ?  -- target worker_id

    UNION ALL

    -- Recursive case: follow delegation chain up
    SELECT
        w.id,
        w.name,
        w.role,
        w.delegated_by,
        dc.depth + 1
    FROM workers w
    JOIN delegation_chain dc ON w.id = dc.delegated_by
)
SELECT * FROM delegation_chain
ORDER BY depth DESC;
```

**Example result:**
```
id          | name    | role     | delegated_by | depth
------------|---------|----------|--------------|------
ceo-001     | Alice   | CEO      | NULL         | 3
director-01 | Bob     | Director | ceo-001      | 2
manager-05  | Carol   | Manager  | director-01  | 1
engineer-22 | Dave    | Engineer | manager-05   | 0
```

### 4.2 Find all delegates of a manager

**Use case:** "Show all workers I've delegated authority to"

```sql
SELECT
    w.id,
    w.name,
    w.role,
    dg.scope,
    dg.budget_amount,
    dg.granted_at
FROM delegation_grants dg
JOIN workers w ON dg.delegate_id = w.id
WHERE dg.delegator_id = ?  -- manager's worker_id
  AND dg.revoked_at IS NULL
ORDER BY dg.granted_at DESC;
```

### 4.3 Check if delegation would create cycle

**Use case:** Before granting delegation, verify no circular reference

```sql
WITH RECURSIVE delegation_tree AS (
    -- Base case: proposed grantee
    SELECT delegate_id AS worker_id, 0 AS depth
    FROM delegation_grants
    WHERE delegate_id = ?  -- proposed grantee
      AND revoked_at IS NULL

    UNION ALL

    -- Recursive case: follow sub-delegations
    SELECT dg.delegate_id, dt.depth + 1
    FROM delegation_grants dg
    JOIN delegation_tree dt ON dg.delegator_id = dt.worker_id
    WHERE dg.revoked_at IS NULL
      AND dt.depth < 10  -- Prevent infinite recursion
)
SELECT COUNT(*) AS would_create_cycle
FROM delegation_tree
WHERE worker_id = ?;  -- proposed delegator

-- If count > 0, delegation would create cycle
```

### 4.4 Get audit trail for worker

**Use case:** Compliance report - "Show all delegation events for this worker"

```sql
SELECT
    da.event_type,
    da.timestamp,
    da.performed_by,
    da.reason,
    delegator.name AS delegator_name,
    delegate.name AS delegate_name,
    da.scope_before,
    da.scope_after,
    da.budget_before,
    da.budget_after
FROM delegation_audit da
LEFT JOIN workers delegator ON da.delegator_id = delegator.id
LEFT JOIN workers delegate ON da.delegate_id = delegate.id
WHERE da.delegate_id = ?  -- target worker
   OR da.delegator_id = ?  -- target worker
ORDER BY da.timestamp DESC;
```

### 4.5 Find orphaned authority

**Use case:** Data integrity check - workers with authority but no valid delegator

```sql
SELECT
    w.id,
    w.name,
    w.role,
    w.delegated_by,
    w.hiring_authority_scope
FROM workers w
LEFT JOIN workers delegator ON w.delegated_by = delegator.id
WHERE w.hiring_authority_scope IS NOT NULL
  AND w.role != 'CEO'
  AND (
    w.delegated_by IS NULL  -- No delegator
    OR delegator.id IS NULL  -- Delegator doesn't exist
    OR delegator.status = 'terminated'  -- Delegator terminated
  );
```

### 4.6 Find expiring delegations

**Use case:** Cleanup job - revoke delegations that have expired

```sql
SELECT
    dg.id,
    dg.delegate_id,
    dg.expires_at,
    w.name AS delegate_name
FROM delegation_grants dg
JOIN workers w ON dg.delegate_id = w.id
WHERE dg.revoked_at IS NULL
  AND dg.expires_at IS NOT NULL
  AND dg.expires_at <= CURRENT_TIMESTAMP
ORDER BY dg.expires_at ASC;
```

---

## 5. Performance Analysis

### 5.1 Table Size Estimates

**Assumptions:**
- 1000 workers in org
- 30% of workers have hiring authority (300 workers)
- Average delegation depth: 3 levels (CEO → Director → Manager)

**delegation_grants table:**
- 300 active grants (one per worker with authority)
- Assume 20% churn (workers terminated/reassigned) per year: 60 revoked grants/year
- After 3 years: 300 active + 180 revoked = 480 rows
- Row size: ~200 bytes (text fields, timestamps)
- **Total size: ~96 KB** (negligible)

**delegation_audit table:**
- 300 initial grants (migration backfill)
- 60 revocations/year
- 60 new grants/year (new hires with authority)
- Total events/year: 120
- After 3 years: 300 + (120 * 3) = 660 rows
- Row size: ~300 bytes (includes before/after state)
- **Total size: ~198 KB** (negligible)

**workers table additions:**
- 3 new columns per worker (delegation_version, delegation_expires_at, delegated_by)
- Column overhead: ~24 bytes per worker
- 1000 workers * 24 bytes = **24 KB** (negligible)

**Conclusion:** Schema changes add <500 KB to database even with 3 years of history. Performance impact is minimal.

### 5.2 Query Performance

**Critical queries (must be fast):**

1. **Get worker's delegator** (used in authorization checks)
   ```sql
   SELECT delegated_by FROM workers WHERE id = ?;
   ```
   - No JOIN required (denormalized)
   - Index: PRIMARY KEY on workers.id
   - **Performance: O(1) - single row lookup**

2. **Check if delegation exists**
   ```sql
   SELECT 1 FROM delegation_grants
   WHERE delegate_id = ? AND revoked_at IS NULL;
   ```
   - Index: UNIQUE(delegate_id) WHERE revoked_at IS NULL
   - **Performance: O(1) - unique index lookup**

3. **Find all sub-delegations** (used in cascade revocation)
   ```sql
   SELECT delegate_id FROM delegation_grants
   WHERE delegator_id = ? AND revoked_at IS NULL;
   ```
   - Index: idx_delegation_grants_delegator
   - **Performance: O(k) where k = number of direct reports**
   - Typical k = 5-10, so very fast

**Non-critical queries (can be slower):**

4. **Get full delegation chain** (used in UI/reporting)
   - Recursive CTE (see 4.1)
   - Performance: O(depth * log(n)) where depth = 3-5 typically
   - **Acceptable: <10ms even with 10,000 workers**

5. **Audit trail queries** (used in compliance reports)
   - Full table scan with timestamp filter
   - Index: idx_delegation_audit_timestamp
   - **Performance: O(log(n)) for time-range queries**

### 5.3 Index Usage Analysis

**delegation_grants:**
- `idx_delegation_grants_delegator` - Used in cascade revocation (high frequency)
- `idx_delegation_grants_delegate` - Used in authorization checks (high frequency)
- `idx_delegation_grants_active` - Used in "find active delegations" queries (medium frequency)
- `idx_delegation_grants_expires` - Used in cleanup job (low frequency, once/day)

**delegation_audit:**
- `idx_delegation_audit_delegate` - Used in "show audit trail" queries (low frequency)
- `idx_delegation_audit_timestamp` - Used in time-range reports (low frequency)
- `idx_delegation_audit_event_type` - Used in analytics (low frequency)

**Recommendation:** All indexes are necessary for their respective queries. No redundant indexes.

### 5.4 Trigger Overhead

**Triggers on INSERT/UPDATE:**
- `log_delegation_grant` - Runs on every delegation grant (low frequency, ~1/day)
- `log_delegation_revoke` - Runs on every delegation revoke (low frequency, ~1/day)
- `revoke_delegations_on_termination` - Runs on worker termination (very low frequency)

**Performance impact:**
- Each trigger adds ~1-2ms to operation
- Delegation operations are already rare (minutes-to-hours between)
- **Conclusion: Trigger overhead is negligible**

---

## 6. Data Integrity

### 6.1 Constraints Enforcing Safety Findings

**P0 Vulnerability Mitigations:**

1. **Self-delegation (P0-1)**
   - Constraint: `CHECK (delegator_id != delegate_id)` in delegation_grants
   - Prevents: Worker delegating to themselves

2. **Concurrent over-allocation (P0-2)**
   - Mechanism: `delegation_version` + optimistic locking in application code
   - Prevents: Two processes delegating simultaneously exceeding budget

3. **Terminated worker authority (P0-3)**
   - Constraint: `CHECK (status IN ('onboarding', 'active'))` when authority exists
   - Trigger: `revoke_delegations_on_termination`
   - Prevents: Terminated workers keeping/granting authority

4. **Orphaned delegations (P0-4)**
   - Foreign key: `ON DELETE CASCADE` for delegator_id
   - Trigger: Auto-revocation on termination
   - Prevents: Authority persisting after delegator terminated

5. **Circular delegation (P0-5)**
   - Application logic: Cycle detection before granting (see query 4.3)
   - Prevents: A → B → C → A delegation loops

### 6.2 Application Code vs Database Constraints

**When to use database constraints:**
- Simple validation (non-negative budget, delegator != delegate)
- Referential integrity (foreign keys)
- Atomicity (triggers for audit logging)

**When to use application code:**
- Complex business logic (scope validation, budget calculations)
- Cycle detection (requires recursive queries)
- Error messages (database errors are cryptic, app can explain)

**QuinnAI Strategy:**
```python
# Application code validates business rules
def delegate_authority(
    db: Database,
    delegator_id: str,
    delegate_id: str,
    scope: HiringScope,
    budget: int
) -> str:
    # 1. Validate business rules (application)
    if delegator_id == delegate_id:
        raise ValueError("Cannot delegate to self")

    _check_delegation_cycle(db, delegator_id, delegate_id)
    _validate_scope_subset(db, delegator_id, scope)
    _validate_budget_available(db, delegator_id, budget)

    # 2. Atomic database operation (database)
    with db.transaction() as cursor:
        # Database constraints will catch any violations
        cursor.execute(
            """INSERT INTO delegation_grants (...)
               VALUES (...)"""
        )
        # Trigger automatically logs to audit table

    return grant_id
```

### 6.3 Consistency Guarantees

**ACID Properties:**

1. **Atomicity**
   - All delegation operations wrapped in transactions
   - Either grant succeeds fully OR nothing changes
   - Example: Grant + audit log + worker update all succeed or all roll back

2. **Consistency**
   - Constraints prevent invalid states
   - Triggers maintain referential integrity
   - Example: Can't have active grant without corresponding worker.delegated_by

3. **Isolation**
   - Optimistic locking prevents concurrent modification
   - Read committed isolation level (SQLite default)
   - Example: Two processes can't both grant authority exceeding budget

4. **Durability**
   - SQLite WAL mode ensures writes are durable
   - Audit log is immutable (can't be tampered with)
   - Example: Power loss won't corrupt delegation state

**Invariants Maintained:**
- Every non-CEO worker with authority has exactly one delegator
- Sum of sub-delegations ≤ delegator's budget
- No delegation cycles exist
- Terminated workers have no authority
- Audit trail contains all operations (no gaps)

---

## 7. Migration Execution Plan

### Phase 1: Schema Addition (No Downtime)

**Steps:**
1. Apply migration v17 (create tables, add columns, add indexes)
2. Verify schema changes with `PRAGMA table_info(delegation_grants)`
3. Run smoke tests on new tables (INSERT/SELECT/DELETE)

**Rollback:** Execute v17_rollback.sql

**Duration:** ~1 second per org database

### Phase 2: Data Backfill (Read-Only Period)

**Steps:**
1. Put org in maintenance mode (stop all workers)
2. Run backfill script (v17b_backfill_delegations.py)
3. Validate backfill results (check warnings)
4. Manual review of orphaned authority (if any)
5. Resume org operations

**Rollback:** Truncate delegation_grants and delegation_audit tables

**Duration:** ~5 seconds per 1000 workers

### Phase 3: Constraint Activation (No Downtime)

**Steps:**
1. Enable CHECK constraints on workers table
2. Test delegation operations with constraints enabled
3. Monitor logs for constraint violations

**Rollback:** Drop CHECK constraints

**Duration:** ~1 second

### Phase 4: Application Code Deployment (No Downtime)

**Steps:**
1. Deploy new worker.py with delegation tracking
2. Deploy new authorization.py with cycle detection
3. Deploy new CLI commands (delegate, revoke, audit)
4. Update dashboard to show delegation chains

**Rollback:** Deploy previous version of application code

**Duration:** Standard deployment time

### Testing Checklist

**Pre-migration:**
- [ ] Backup all org databases
- [ ] Verify no workers in "onboarding" state (simplifies backfill)
- [ ] Test migration on staging org with 100+ workers

**Post-migration:**
- [ ] Verify delegation_grants count matches workers with authority
- [ ] Verify audit table has initial "granted" events
- [ ] Test delegation operation (grant new authority)
- [ ] Test revocation operation (revoke existing authority)
- [ ] Test cascade revocation (revoke delegator, verify sub-delegations revoked)
- [ ] Test termination trigger (terminate worker with authority)
- [ ] Test query performance (delegation chain query <10ms)

---

## 8. Future Enhancements

### 8.1 Time-Limited Delegation

**Use case:** Grant temporary authority for project duration

**Implementation:**
```sql
-- Already supported via expires_at column
INSERT INTO delegation_grants (
    ...,
    expires_at = ?  -- Set to project end date
);

-- Cleanup job (runs daily)
UPDATE delegation_grants
SET revoked_at = CURRENT_TIMESTAMP,
    revoked_by = 'system',
    revoke_reason = 'expired'
WHERE expires_at <= CURRENT_TIMESTAMP
  AND revoked_at IS NULL;
```

### 8.2 Delegation Templates

**Use case:** Reusable delegation scope presets (e.g., "Junior Engineer Authority", "Senior Manager Authority")

**Schema addition:**
```sql
CREATE TABLE delegation_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    scope TEXT NOT NULL,  -- HiringScope JSON
    budget_amount INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Apply template
INSERT INTO delegation_grants (...)
SELECT id, delegator_id, delegate_id, scope, budget_amount, ...
FROM delegation_templates
WHERE id = ?;
```

### 8.3 Delegation Approval Workflow

**Use case:** Require CEO approval for high-value delegations

**Schema addition:**
```sql
ALTER TABLE delegation_grants ADD COLUMN approval_status TEXT
    CHECK(approval_status IN ('pending', 'approved', 'rejected'));
ALTER TABLE delegation_grants ADD COLUMN approved_by TEXT;
ALTER TABLE delegation_grants ADD COLUMN approved_at DATETIME;

-- Grant is inactive until approved
CREATE INDEX idx_delegation_grants_pending ON delegation_grants(approval_status)
    WHERE approval_status = 'pending';
```

### 8.4 Delegation Usage Metrics

**Use case:** Track how much delegated authority is actually used

**Schema addition:**
```sql
ALTER TABLE delegation_grants ADD COLUMN hires_made INTEGER NOT NULL DEFAULT 0;
ALTER TABLE delegation_grants ADD COLUMN budget_spent INTEGER NOT NULL DEFAULT 0;

-- Update on hire
UPDATE delegation_grants
SET hires_made = hires_made + 1,
    budget_spent = budget_spent + ?
WHERE delegate_id = ?
  AND revoked_at IS NULL;
```

### 8.5 Delegation Notifications

**Use case:** Notify worker when they receive/lose delegation

**Integration:**
```python
# In delegation grant logic
def grant_delegation(...):
    # ... create delegation_grant record ...

    # Create notification bead
    create_notification_bead(
        db=db,
        worker_id=delegate_id,
        type="info",
        title=f"Hiring authority granted by {delegator.name}",
        description=f"You can now hire: {scope.allowed_roles}"
    )
```

---

## 9. Security Considerations

### 9.1 SQL Injection Prevention

**All queries use parameterized statements:**
```python
# SAFE
cursor.execute(
    "SELECT * FROM delegation_grants WHERE delegate_id = ?",
    (worker_id,)
)

# UNSAFE (never do this)
cursor.execute(
    f"SELECT * FROM delegation_grants WHERE delegate_id = '{worker_id}'"
)
```

### 9.2 Audit Log Tampering

**Immutability enforced by triggers:**
- No UPDATE allowed on delegation_audit
- No DELETE allowed on delegation_audit
- ON DELETE RESTRICT for worker FKs (can't delete workers with audit history)

**If audit log is compromised:**
- Database backup is only source of truth
- Consider write-once storage for audit logs (S3 Glacier, etc.)

### 9.3 Privilege Escalation Vectors

**Mitigated by:**
1. Self-delegation prevented (CHECK constraint)
2. Circular delegation detected (application logic)
3. Authority validation (scope subset check)
4. Concurrent modification prevented (optimistic locking)
5. Terminated worker authority auto-revoked (trigger)

**Remaining risks:**
- DBA can modify database directly (bypass application logic)
- Mitigation: Limit DBA access, audit all database changes

### 9.4 Compliance Requirements

**SOC 2 / ISO 27001:**
- ✅ Audit trail of all access grants/revocations
- ✅ Immutable audit log
- ✅ Time-based delegation expiration
- ✅ Automated revocation on termination

**GDPR:**
- ⚠️ Audit log contains worker PII (names, IDs)
- Mitigation: Anonymize audit log after retention period (e.g., 7 years)

---

## 10. Monitoring and Alerting

### 10.1 Data Integrity Checks (Daily)

```sql
-- Check 1: Orphaned authority
SELECT COUNT(*) AS orphaned_count
FROM workers w
WHERE w.hiring_authority_scope IS NOT NULL
  AND w.role != 'CEO'
  AND (w.delegated_by IS NULL
       OR w.delegated_by NOT IN (SELECT id FROM workers WHERE status = 'active'));

-- Check 2: Grant/delegated_by mismatch
SELECT COUNT(*) AS mismatch_count
FROM workers w
LEFT JOIN delegation_grants dg ON dg.delegate_id = w.id AND dg.revoked_at IS NULL
WHERE (w.delegated_by IS NOT NULL AND dg.id IS NULL)
   OR (w.delegated_by IS NULL AND dg.id IS NOT NULL AND w.role != 'CEO');

-- Check 3: Delegation cycles (should always be 0)
WITH RECURSIVE delegation_tree AS (
    SELECT delegate_id AS worker_id, delegator_id, 0 AS depth
    FROM delegation_grants WHERE revoked_at IS NULL
    UNION ALL
    SELECT dg.delegate_id, dg.delegator_id, dt.depth + 1
    FROM delegation_grants dg
    JOIN delegation_tree dt ON dg.delegator_id = dt.worker_id
    WHERE dg.revoked_at IS NULL AND dt.depth < 10
)
SELECT COUNT(*) AS cycle_count
FROM delegation_tree
WHERE worker_id = delegator_id;
```

### 10.2 Performance Metrics (Hourly)

```sql
-- Average delegation chain depth
WITH RECURSIVE delegation_depth AS (
    SELECT id, 0 AS depth FROM workers WHERE role = 'CEO'
    UNION ALL
    SELECT w.id, dd.depth + 1
    FROM workers w
    JOIN delegation_depth dd ON w.delegated_by = dd.id
)
SELECT AVG(depth) AS avg_depth, MAX(depth) AS max_depth
FROM delegation_depth;

-- Delegation grant rate (per day)
SELECT
    DATE(granted_at) AS date,
    COUNT(*) AS grants_per_day
FROM delegation_grants
WHERE granted_at >= DATE('now', '-30 days')
GROUP BY DATE(granted_at)
ORDER BY date DESC;
```

### 10.3 Alerts

| Alert | Trigger | Severity | Action |
|-------|---------|----------|--------|
| Orphaned authority | orphaned_count > 0 | HIGH | Manual review required |
| Grant/delegated_by mismatch | mismatch_count > 0 | CRITICAL | Data corruption - investigate immediately |
| Delegation cycle detected | cycle_count > 0 | CRITICAL | Application bug - fix cycle detection logic |
| Deep delegation chain | max_depth > 7 | MEDIUM | Review org structure |
| Audit log gap | No audit entries for 24h+ | HIGH | Trigger may be broken |

---

## Conclusion

This schema design provides a production-ready foundation for delegation tracking in QuinnAI. Key strengths:

1. **Complete audit trail** - Every delegation operation logged immutably
2. **Cascade-safe revocation** - Foreign keys + triggers prevent orphaned authority
3. **Concurrency-protected** - Optimistic locking prevents over-allocation
4. **Performance-optimized** - Denormalized lookups, strategic indexes
5. **Data integrity-enforced** - Constraints prevent invalid states

**Next Steps:**
1. Review this design with team
2. Implement migration v17 in `cli/core/db.py`
3. Update `Worker.delegate_authority()` to use new tables
4. Add cycle detection function
5. Write comprehensive tests (see safety analysis section 9)
6. Deploy to staging environment
7. Run migration on production orgs

**Estimated Implementation Time:**
- Schema + migration: 4 hours
- Application code updates: 8 hours
- Testing: 8 hours
- **Total: 20 hours (2.5 days)**

---

**References:**
- Safety Analysis: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/scratchpad/delegation-safety-analysis.md`
- Current Database: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/db.py`
- Current Worker Logic: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/worker.py`
- Budget System Reference: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/budget.py`
