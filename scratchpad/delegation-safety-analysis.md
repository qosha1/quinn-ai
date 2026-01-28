# Hiring Authority Delegation Safety Analysis

**Date:** 2026-01-28
**System:** QuinnAI Hierarchical AI Organization Management
**Focus:** Edge cases, failure modes, and security concerns for hiring authority delegation cascade

---

## Executive Summary

The hiring authority delegation system in QuinnAI allows managers to grant subordinates the ability to hire within specified constraints. This creates a cascade of authority from CEO → Directors → Managers → Individual Contributors. While the current implementation (`Worker.delegate_authority()` in `cli/core/worker.py:564-623`) provides basic validation, several critical safety concerns remain unaddressed:

**Critical Gaps:**
1. No tracking of delegation chains (who delegated to whom, when)
2. No automatic revocation when delegator loses authority
3. No protection against concurrent delegation modifications
4. No audit trail for compliance/forensics
5. No safeguards against circular references or invalid hierarchy relationships

**Recommended Actions:**
1. Add delegation tracking table to database schema
2. Implement cascading revocation logic
3. Add database transaction protection for delegation operations
4. Build audit logging infrastructure
5. Add validation layer to prevent hierarchy violations

---

## 1. Circular/Invalid Delegation Scenarios

### 1.1 Non-Direct Report Delegation

**Current Behavior:**
```python
# In Worker.delegate_authority() line 585-588
if report.manager_id != self.id:
    raise ValueError(
        f"Worker {report.id} is not a direct report of {self.id}"
    )
```

✅ **PROTECTED**: Code explicitly checks `report.manager_id == self.id` before allowing delegation.

**Edge Case:** What if `manager_id` is NULL?
- CEO has `manager_id = NULL` (no manager)
- Could someone try to delegate to CEO? Yes, but check fails (NULL != self.id)
- **Status:** Safe

### 1.2 Self-Delegation

**Current Behavior:** No explicit check for `report.id == self.id`.

❌ **VULNERABLE**: Code does not prevent:
```python
manager = Worker.get(db, "alice")
manager.delegate_authority(
    report=manager,  # Self-reference
    budget=1000,
    scope=HiringScope(allowed_roles={"engineer"}, max_cost=50)
)
```

**Impact:** Worker can artificially increase their own authority by "delegating" to themselves repeatedly.

**Recommended Fix:**
```python
# Add to delegate_authority() at line 584
if report.id == self.id:
    raise ValueError("Cannot delegate authority to self")
```

### 1.3 Circular Delegation Chain (A → B → C → A)

**Current Behavior:** No tracking of delegation chains exists.

❌ **VULNERABLE**: Database schema has no `delegation_history` or `delegated_by` tracking.

**Attack Scenario:**
1. Alice (Director) delegates to Bob (Manager)
2. Bob uses delegated authority to hire Carol (Manager)
3. Carol is hired with hiring authority
4. Carol delegates back to Alice (if Alice somehow becomes Carol's report through org restructure)

**Why This is Dangerous:**
- Authority amplification loop
- Unclear accountability
- Revocation becomes impossible (who should lose authority first?)

**Current Database Schema (workers table):**
```sql
hiring_authority_scope TEXT,        -- What can they hire
delegated_budget INTEGER,            -- How much budget they have
max_reports INTEGER,                 -- Max direct reports
```

**Missing:**
```sql
delegated_by_worker_id TEXT,         -- Who granted this authority
delegation_granted_at DATETIME,      -- When was it granted
delegation_expires_at DATETIME,      -- Optional: time-based delegation
```

**Recommended Fix:**
Create `delegation_grants` table:
```sql
CREATE TABLE delegation_grants (
    id TEXT PRIMARY KEY,
    delegator_id TEXT NOT NULL,           -- Who granted the authority
    grantee_id TEXT NOT NULL,             -- Who received it
    scope TEXT NOT NULL,                  -- HiringScope JSON
    budget_amount INTEGER NOT NULL,
    granted_at DATETIME NOT NULL,
    revoked_at DATETIME,
    revoked_by TEXT,
    revoke_reason TEXT,
    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (grantee_id) REFERENCES workers(id) ON DELETE CASCADE,
    CHECK (delegator_id != grantee_id)    -- Prevent self-delegation
);

CREATE INDEX idx_delegation_grants_grantee ON delegation_grants(grantee_id);
CREATE INDEX idx_delegation_grants_delegator ON delegation_grants(delegator_id);
```

**Circular Reference Detection:**
```python
def _check_delegation_cycle(db: Database, delegator_id: str, grantee_id: str) -> bool:
    """Check if granting delegation would create a cycle.

    A cycle exists if grantee_id has (directly or transitively)
    delegated to delegator_id in the past.
    """
    visited = set()
    queue = [grantee_id]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        if current == delegator_id:
            return True  # Cycle detected

        # Find who current has delegated to
        grants = db.fetchall(
            """SELECT grantee_id FROM delegation_grants
               WHERE delegator_id = ? AND revoked_at IS NULL""",
            (current,)
        )
        queue.extend([g["grantee_id"] for g in grants])

    return False
```

---

## 2. Concurrent Modification Scenarios

### 2.1 Race Condition: Two Processes Delegate Simultaneously

**Scenario:**
```
Process A: Alice delegates to Bob at T=0
Process B: Alice delegates to Carol at T=1
Both read Alice's delegated_budget = $10,000
Both attempt to delegate $8,000
```

**Current Behavior:**
```python
# Line 604-607 in delegate_authority()
if budget > self.delegated_budget:
    raise InsufficientHiringAuthority(
        f"Cannot delegate budget {budget} exceeding own {self.delegated_budget}"
    )
```

❌ **VULNERABLE**: No database transaction wrapping the check + update.

**Current Implementation:**
```python
# Line 611-619
self.db.execute(
    """UPDATE workers
       SET hiring_authority_scope = ?,
           delegated_budget = ?,
           updated_at = ?
       WHERE id = ?""",
    (scope.to_json(), budget, now, report.id)
)
self.db.connection.commit()
```

**Problem:** The sequence is:
1. Read `self.delegated_budget` (cached property)
2. Validate budget >= required
3. UPDATE workers table

Between steps 1-3, another process can modify `delegated_budget`, causing over-allocation.

**Recommended Fix: Optimistic Locking**
```python
# Add version field to workers table (migration)
ALTER TABLE workers ADD COLUMN delegation_version INTEGER NOT NULL DEFAULT 0;

# In delegate_authority()
def delegate_authority(self, report: Worker, budget: int, scope: HiringScope):
    # ... validation ...

    # Read current state with version
    row = self.db.fetchone(
        "SELECT delegated_budget, delegation_version FROM workers WHERE id = ?",
        (self.id,)
    )
    current_budget = row["delegated_budget"]
    current_version = row["delegation_version"]

    if budget > current_budget:
        raise InsufficientHiringAuthority(...)

    # Atomic compare-and-swap
    result = self.db.execute(
        """UPDATE workers
           SET hiring_authority_scope = ?,
               delegated_budget = delegated_budget - ?,
               delegation_version = delegation_version + 1,
               updated_at = ?
           WHERE id = ? AND delegation_version = ?""",
        (scope.to_json(), budget, now, report.id, current_version)
    )

    if result.rowcount == 0:
        # Version mismatch - someone else modified
        raise ConcurrentModificationError(
            "Delegation failed: worker authority was modified concurrently. Retry."
        )

    self.db.connection.commit()
```

### 2.2 Delegator Loses Authority Mid-Delegation

**Scenario:**
```
T=0: Alice (Director) has hiring authority
T=1: Alice starts delegation to Bob
T=2: CEO fires Alice (authority revoked)
T=3: Alice's delegation transaction completes
```

**Current Behavior:** No lifecycle check in `delegate_authority()`.

❌ **VULNERABLE**: Terminated/offboarding workers can still delegate.

**Recommended Fix:**
```python
# Add at line 584 in delegate_authority()
if self.lifecycle_status not in ("active",):
    raise InvalidLifecycleState(
        "delegate authority",
        self.lifecycle_status
    )

# Also check report is active
if report.lifecycle_status not in ("active",):
    raise InvalidLifecycleState(
        f"receive delegation (grantee {report.name})",
        report.lifecycle_status
    )
```

### 2.3 Worker Fired During Delegation

**Scenario:**
```
T=0: Alice delegates to Bob (in progress)
T=1: CEO fires Bob (Worker.terminate() called)
T=2: Alice's delegation UPDATE completes
```

**Current Database Constraint:**
```sql
FOREIGN KEY (manager_id) REFERENCES workers(id) ON DELETE SET NULL
```

**Behavior:** If Bob is deleted from `workers` table, the UPDATE would fail with foreign key constraint error.

✅ **PROTECTED** (by accident): Foreign key constraint prevents writing to deleted worker.

**However:** Bob is not deleted during `terminate()`, only status changes to "terminated". The UPDATE would succeed, granting authority to a terminated worker.

❌ **VULNERABLE**: Terminated workers can receive authority.

**Recommended Fix:** Add trigger to prevent authority grants to non-active workers:
```sql
CREATE TRIGGER prevent_delegation_to_terminated
BEFORE UPDATE ON workers
FOR EACH ROW
WHEN NEW.hiring_authority_scope IS NOT NULL
     AND NEW.status NOT IN ('active')
BEGIN
    SELECT RAISE(ABORT, 'Cannot delegate authority to non-active worker');
END;
```

Or better: Add status check in application code (see 2.2 above).

---

## 3. Cascading Effect Scenarios

### 3.1 Manager Loses Authority → What Happens to Sub-Delegations?

**Scenario:**
```
CEO → delegates to Alice (Director)
Alice → delegates to Bob (Manager)
Bob → delegates to Carol (Engineer)

CEO revokes Alice's authority.
```

**Question:** Should Bob and Carol automatically lose their delegated authority?

**Current Behavior:** No automatic revocation exists.

❌ **VULNERABLE**: Sub-delegations persist even after source authority is revoked.

**Design Options:**

**Option A: Cascading Revocation (Recommended)**
```python
def revoke_authority(db: Database, worker_id: str, cascade: bool = True):
    """Revoke hiring authority from a worker.

    Args:
        worker_id: Worker whose authority to revoke
        cascade: If True, recursively revoke all sub-delegations
    """
    if cascade:
        # Find all workers who received delegation from this worker
        sub_grants = db.fetchall(
            """SELECT grantee_id FROM delegation_grants
               WHERE delegator_id = ? AND revoked_at IS NULL""",
            (worker_id,)
        )

        # Recursively revoke sub-delegations
        for grant in sub_grants:
            revoke_authority(db, grant["grantee_id"], cascade=True)

    # Revoke this worker's authority
    now = datetime.now()
    db.execute(
        """UPDATE workers
           SET hiring_authority_scope = NULL,
               delegated_budget = 0,
               updated_at = ?
           WHERE id = ?""",
        (now, worker_id)
    )

    # Mark delegation grants as revoked
    db.execute(
        """UPDATE delegation_grants
           SET revoked_at = ?, revoke_reason = 'cascade'
           WHERE grantee_id = ?""",
        (now, worker_id)
    )
    db.connection.commit()
```

**Option B: Orphaned Delegation (Dangerous)**
- Sub-delegations remain valid even after parent authority revoked
- Creates "authority laundering" attack vector
- NOT RECOMMENDED

**Option C: Notification + Manual Review**
- System creates notification beads for affected workers
- Requires manual decision per case
- Slow, error-prone
- NOT RECOMMENDED for security-critical revocations

### 3.2 Manager with 10 Reports Gets Fired

**Current Behavior:**
```python
# In Worker.terminate() line 917-995
# ... stops session, freezes storage ...

# NO CHECK for active delegations or reports
```

❌ **MISSING SAFEGUARD**: No warning or blocking when firing a manager with active delegations.

**Impact:** Orphaned reports, unclear chain of command.

**Database Constraint:**
```sql
FOREIGN KEY (manager_id) REFERENCES workers(id) ON DELETE SET NULL
```

**Behavior When Manager Fired:**
- Worker status → "terminated"
- BUT manager_id is NOT set to NULL (worker row persists)
- Reports still have manager_id pointing to terminated worker
- Reports cannot get new assignments from terminated manager

**Cascading Questions:**
1. Should reports be auto-reassigned to grandparent manager?
2. Should termination be blocked until reports are reassigned?
3. Should system create "reassignment" beads for HR?

**Recommended Fix:**
```python
# In Worker.terminate() before line 932
def terminate(self) -> None:
    """Terminate worker - freeze storage, update org-chart, fire event."""

    # CHECK: Does worker have active reports?
    direct_reports = get_workers_by_manager(self.db, self.id)
    active_reports = [r for r in direct_reports if r.status == "active"]

    if active_reports:
        raise CannotTerminateError(
            f"Cannot terminate {self.name}: has {len(active_reports)} active reports. "
            "Reassign or terminate reports first."
        )

    # CHECK: Does worker have active delegations granted to them?
    delegation = self.db.fetchone(
        """SELECT delegator_id FROM delegation_grants
           WHERE grantee_id = ? AND revoked_at IS NULL""",
        (self.id,)
    )

    if delegation:
        # Auto-revoke delegation on termination
        revoke_authority(self.db, self.id, cascade=True)

    # ... rest of termination ...
```

### 3.3 Should Revocation Cascade Down?

**Answer: YES** (with audit trail)

**Rationale:**
- Delegated authority is derived from delegator's authority
- If source authority is invalid, all downstream grants are invalid
- Similar to certificate revocation in PKI systems

**Implementation:**
```python
def revoke_delegation_cascade(
    db: Database,
    worker_id: str,
    reason: str,
    revoked_by: str,
) -> int:
    """Revoke all delegations in the subtree rooted at worker_id.

    Returns:
        Number of delegations revoked
    """
    count = 0

    # DFS traversal of delegation tree
    def revoke_subtree(current_id: str):
        nonlocal count

        # Find direct sub-delegations
        grants = db.fetchall(
            """SELECT id, grantee_id FROM delegation_grants
               WHERE delegator_id = ? AND revoked_at IS NULL""",
            (current_id,)
        )

        for grant in grants:
            # Recursively revoke sub-tree
            revoke_subtree(grant["grantee_id"])

            # Revoke this grant
            now = datetime.now()
            db.execute(
                """UPDATE delegation_grants
                   SET revoked_at = ?,
                       revoked_by = ?,
                       revoke_reason = ?
                   WHERE id = ?""",
                (now, revoked_by, f"cascade: {reason}", grant["id"])
            )
            count += 1

            # Clear worker's authority
            db.execute(
                """UPDATE workers
                   SET hiring_authority_scope = NULL,
                       delegated_budget = 0,
                       updated_at = ?
                   WHERE id = ?""",
                (now, grant["grantee_id"])
            )

    revoke_subtree(worker_id)
    db.connection.commit()
    return count
```

---

## 4. Authority Conflict Scenarios

### 4.1 Worker Has Scope But No Budget

**Scenario:**
```python
worker.hiring_authority_scope = {"allowed_roles": {"engineer"}, "max_cost": 50}
worker.delegated_budget = 0
```

**Current Behavior:** `Worker.can_hire()` checks budget:
```python
# Line 444-466 in can_hire()
if scope.max_total_budget > 0:
    cumulative_cost = # ... sum of existing hires ...
    if total_with_new_hire > scope.max_total_budget:
        return False, "Budget exceeded..."
```

✅ **PROTECTED** (partially): Budget check exists, but only for `max_total_budget`.

❌ **GAP**: No check for `delegated_budget` being sufficient for the hire cost.

**Issue:** `delegated_budget` is used for delegating to others, not for hiring directly. This is a **semantic confusion** in the schema.

**Recommended Clarification:**
- `hiring_budget` = Budget for THIS worker's direct hires
- `delegation_budget` = Budget this worker can grant to subordinates

**Schema Change:**
```sql
ALTER TABLE workers ADD COLUMN hiring_budget INTEGER NOT NULL DEFAULT 0;
-- hiring_budget: Worker's own budget for hiring
-- delegated_budget: Renamed to delegation_pool (budget worker can sub-allocate)
```

### 4.2 Worker Has Budget But No Scope

**Scenario:**
```python
worker.delegated_budget = 10000
worker.hiring_authority_scope = None  # or empty JSON
```

**Current Behavior:**
```python
# Line 427-428 in can_hire()
if not scope.allowed_roles:
    return False, "No hiring authority - no allowed roles"
```

✅ **PROTECTED**: Empty scope is checked first, prevents hiring.

### 4.3 Worker Authority Exceeds Manager's Authority

**Scenario:**
```
Manager Alice:
  - allowed_roles: {"engineer"}
  - max_cost: 50

Manager delegates to Bob:
  - allowed_roles: {"engineer", "designer"}  # INVALID: designer not in Alice's scope
  - max_cost: 80                              # INVALID: exceeds Alice's max_cost
```

**Current Behavior:**
```python
# Line 591-601 in delegate_authority()
for role in scope.allowed_roles:
    if role not in own_scope.allowed_roles:
        raise InsufficientHiringAuthority(...)

if scope.max_cost > own_scope.max_cost:
    raise InsufficientHiringAuthority(...)
```

✅ **PROTECTED**: Code validates delegated scope is subset of delegator's scope.

**Edge Case:** What if Alice's scope changes AFTER delegation?

**Scenario:**
```
T=0: Alice has scope={"engineer", "designer"}, max_cost=80
T=1: Alice delegates to Bob: scope={"designer"}, max_cost=70
T=2: CEO downgrades Alice: scope={"engineer"}, max_cost=50
T=3: Bob still has scope={"designer"}, max_cost=70 (INVALID)
```

❌ **VULNERABLE**: No validation that active delegations remain valid after delegator's authority changes.

**Recommended Fix: Delegation Validation on Authority Change**
```python
def update_worker_authority(
    db: Database,
    worker_id: str,
    new_scope: HiringScope,
    new_budget: int,
):
    """Update worker's hiring authority, validating delegations.

    Raises:
        DelegationValidationError: If active sub-delegations would become invalid
    """
    # Find active delegations
    grants = db.fetchall(
        """SELECT g.id, g.grantee_id, w.hiring_authority_scope
           FROM delegation_grants g
           JOIN workers w ON g.grantee_id = w.id
           WHERE g.delegator_id = ? AND g.revoked_at IS NULL""",
        (worker_id,)
    )

    invalid_grants = []
    for grant in grants:
        grantee_scope = HiringScope.from_json(grant["hiring_authority_scope"])

        # Check if grantee's scope would be invalid under new delegator scope
        for role in grantee_scope.allowed_roles:
            if role not in new_scope.allowed_roles:
                invalid_grants.append((grant["grantee_id"], f"role {role}"))

        if grantee_scope.max_cost > new_scope.max_cost:
            invalid_grants.append((grant["grantee_id"], f"max_cost {grantee_scope.max_cost}"))

    if invalid_grants:
        raise DelegationValidationError(
            f"Cannot reduce authority: {len(invalid_grants)} active delegations would become invalid. "
            f"Revoke delegations first: {invalid_grants}"
        )

    # Update authority
    now = datetime.now()
    db.execute(
        """UPDATE workers
           SET hiring_authority_scope = ?,
               delegated_budget = ?,
               updated_at = ?
           WHERE id = ?""",
        (new_scope.to_json(), new_budget, now, worker_id)
    )
    db.connection.commit()
```

---

## 5. Database Consistency Scenarios

### 5.1 Orphaned Delegations (Delegator Deleted)

**Current Schema:**
```sql
-- No delegation_grants table exists
-- Authority is stored directly in workers table
```

**If delegation_grants table is added:**
```sql
FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE
```

✅ **PROTECTED**: `ON DELETE CASCADE` would auto-delete delegation grants when delegator is deleted.

**However:** Workers are never deleted, only status → "terminated". So grants would persist.

**Recommended:** Use triggers or cleanup jobs:
```sql
-- Trigger to revoke delegations when worker is terminated
CREATE TRIGGER revoke_delegations_on_termination
AFTER UPDATE OF status ON workers
FOR EACH ROW
WHEN NEW.status = 'terminated' AND OLD.status != 'terminated'
BEGIN
    UPDATE delegation_grants
    SET revoked_at = CURRENT_TIMESTAMP,
        revoke_reason = 'delegator terminated'
    WHERE delegator_id = NEW.id AND revoked_at IS NULL;
END;
```

### 5.2 Authority Mismatch After Manager Update

**Scenario:**
```
T=0: Bob (Manager) has hiring authority delegated by Alice (Director)
T=1: Bob is reassigned to Charlie (different Director)
T=2: Bob's authority still references Alice as delegator (stale)
```

**Current Behavior:** No tracking of delegator, so this is not detectable.

❌ **VULNERABLE**: Authority can outlive the reporting relationship that granted it.

**Recommended Fix:**
```python
# In set_manager() or similar manager reassignment function
def reassign_worker_manager(
    db: Database,
    worker_id: str,
    new_manager_id: str,
):
    """Reassign worker to new manager, revoking delegated authority."""

    # Check if worker has delegated authority
    current = get_worker(db, worker_id)

    if current.hiring_authority_scope:
        # Authority was delegated by old manager, revoke it
        revoke_authority(db, worker_id, cascade=True)

        # Create notification for new manager to re-delegate if needed
        create_notification_bead(
            db=db,
            worker_id=new_manager_id,
            type="ask",
            title=f"Re-evaluate hiring authority for {current.name}",
            description=f"{current.name} was reassigned to you from another manager. "
                       f"Their hiring authority was revoked. Review and re-delegate if appropriate."
        )

    # Update manager_id
    now = datetime.now()
    db.execute(
        "UPDATE workers SET manager_id = ?, updated_at = ? WHERE id = ?",
        (new_manager_id, now, worker_id)
    )
    db.connection.commit()
```

### 5.3 Worker with Authority But manager_id = NULL

**Scenario:**
```python
worker.manager_id = None
worker.hiring_authority_scope = {"allowed_roles": {"engineer"}}
```

**Current Validation:** No check for this in `delegate_authority()`.

**Impact:** Only CEO should have authority with manager_id = NULL. Others indicate data corruption.

**Recommended Fix:**
```python
# Database constraint
CREATE TRIGGER check_authority_requires_manager
BEFORE UPDATE ON workers
FOR EACH ROW
WHEN NEW.hiring_authority_scope IS NOT NULL
     AND NEW.manager_id IS NULL
     AND NEW.role != 'CEO'
BEGIN
    SELECT RAISE(ABORT, 'Non-CEO workers must have a manager to receive hiring authority');
END;
```

---

## 6. Migration Scenarios

### 6.1 Existing Orgs With Workers Hired Before Delegation Feature

**Challenge:** Existing workers have no `hiring_authority_scope`, `delegated_budget`, or `max_reports` values.

**Schema Migration (v7):**
```sql
ALTER TABLE workers ADD COLUMN hiring_authority_scope TEXT;
ALTER TABLE workers ADD COLUMN delegated_budget INTEGER NOT NULL DEFAULT 0;
ALTER TABLE workers ADD COLUMN max_reports INTEGER NOT NULL DEFAULT 10;
```

**Data Migration Required:**
```python
def migrate_existing_orgs_to_delegation_model(db: Database):
    """Backfill hiring authority for existing managers.

    Heuristic:
    - CEO gets wildcard authority
    - Directors get authority based on their team's roles
    - Managers get subset of their director's authority
    - Individual contributors get no authority
    """
    # 1. Grant CEO full authority
    ceo = db.fetchone(
        "SELECT id FROM workers WHERE role = 'CEO' AND status != 'terminated'"
    )
    if ceo:
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = ?,
                   max_reports = ?
               WHERE id = ?""",
            (
                HiringScope(allowed_roles={"*"}, max_cost=100, max_total_budget=1000000).to_json(),
                1000000,
                50,
                ceo["id"]
            )
        )

    # 2. Grant authority to existing managers based on their reports
    managers = db.fetchall(
        """SELECT w.id, w.role, COUNT(r.id) as report_count
           FROM workers w
           LEFT JOIN workers r ON r.manager_id = w.id
           WHERE w.status = 'active'
           GROUP BY w.id
           HAVING report_count > 0"""
    )

    for manager in managers:
        # Infer allowed roles from existing reports
        report_roles = db.fetchall(
            "SELECT DISTINCT role FROM workers WHERE manager_id = ?",
            (manager["id"],)
        )
        allowed_roles = set(r["role"] for r in report_roles)

        # Grant conservative authority
        scope = HiringScope(
            allowed_roles=allowed_roles,
            max_cost=50,  # Conservative default
            max_total_budget=100000
        )

        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = 10000,
                   max_reports = 20
               WHERE id = ?""",
            (scope.to_json(), manager["id"])
        )

    db.connection.commit()
```

### 6.2 Upgrading CEO from Wildcard "*" to Explicit Role List

**Challenge:** Wildcard "*" is convenient but lacks granularity. Some orgs may want explicit role lists.

**Migration Strategy:**
```python
def expand_wildcard_to_explicit_roles(db: Database):
    """Replace wildcard "*" with explicit list of all roles in use."""

    # Get all unique roles currently in org
    roles = db.fetchall(
        "SELECT DISTINCT role FROM workers WHERE status != 'terminated'"
    )
    role_list = [r["role"] for r in roles]

    # Find workers with wildcard
    wildcards = db.fetchall(
        """SELECT id, hiring_authority_scope FROM workers
           WHERE hiring_authority_scope LIKE '%"*"%'"""
    )

    for worker in wildcards:
        scope = HiringScope.from_json(worker["hiring_authority_scope"])
        if "*" in scope.allowed_roles:
            # Replace wildcard with explicit roles
            scope.allowed_roles = set(role_list)

            db.execute(
                "UPDATE workers SET hiring_authority_scope = ? WHERE id = ?",
                (scope.to_json(), worker["id"])
            )

    db.connection.commit()
```

### 6.3 Schema Migration for Delegation Tracking

**Required Tables:**
```sql
-- Migration v17: Add delegation tracking
CREATE TABLE IF NOT EXISTS delegation_grants (
    id TEXT PRIMARY KEY,
    delegator_id TEXT NOT NULL,
    grantee_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    budget_amount INTEGER NOT NULL,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at DATETIME,
    revoked_by TEXT,
    revoke_reason TEXT,
    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (grantee_id) REFERENCES workers(id) ON DELETE CASCADE,
    CHECK (delegator_id != grantee_id)
);

CREATE INDEX idx_delegation_grants_grantee ON delegation_grants(grantee_id);
CREATE INDEX idx_delegation_grants_delegator ON delegation_grants(delegator_id);
CREATE INDEX idx_delegation_grants_active ON delegation_grants(revoked_at) WHERE revoked_at IS NULL;

-- Add version field for optimistic locking
ALTER TABLE workers ADD COLUMN delegation_version INTEGER NOT NULL DEFAULT 0;

-- Backfill existing delegations (if inferable)
-- This is a best-effort migration - may require manual review
```

---

## 7. Security Threat Model

### 7.1 Privilege Escalation

**Attack:** Low-privilege worker gains high-privilege authority through delegation chain manipulation.

**Vectors:**
1. **Self-Delegation Loop:** Worker delegates to self repeatedly
   - **Mitigation:** Prevent self-delegation (see 1.2)

2. **Circular Delegation:** A → B → C → A creates authority amplification
   - **Mitigation:** Detect cycles before granting (see 1.3)

3. **Authority Laundering:** Worker receives delegation, then manager's authority is revoked but worker keeps authority
   - **Mitigation:** Cascading revocation (see 3.1)

4. **Concurrent Over-Allocation:** Two processes delegate simultaneously, exceeding delegator's budget
   - **Mitigation:** Optimistic locking (see 2.1)

### 7.2 Budget Exhaustion Attack

**Attack:** Malicious manager delegates all budget to subordinates, leaving none for org.

**Scenario:**
```
CEO allocates $100k to Alice
Alice immediately delegates:
  - $30k to Bob
  - $30k to Carol
  - $30k to Dave
  - $10k to Eve
Alice retains $0, cannot hire anyone
```

**Current Behavior:** No limit on how much budget a manager can delegate away.

**Recommended Mitigation:**
```python
# Add max_delegation_percent to budget allocations
ALTER TABLE budget_allocations ADD COLUMN max_delegation_percent INTEGER CHECK(max_delegation_percent <= 100);

# In delegate_authority()
def delegate_authority(self, report, budget, scope):
    # ... existing checks ...

    # Check delegation limits
    allocation = get_worker_allocation(self.db, self.id)
    max_delegate = (allocation.allocated_credits * allocation.max_delegation_percent) / 100

    total_delegated = self.db.fetchone(
        "SELECT SUM(budget_amount) FROM delegation_grants WHERE delegator_id = ? AND revoked_at IS NULL",
        (self.id,)
    )["SUM(budget_amount)"] or 0

    if total_delegated + budget > max_delegate:
        raise InsufficientHiringAuthority(
            f"Cannot delegate {budget}: would exceed max delegation limit "
            f"({max_delegate:.2f}, already delegated {total_delegated:.2f})"
        )
```

### 7.3 Unauthorized Hiring

**Attack:** Terminated worker still has authority in database, uses it to hire.

**Current Vulnerability:** No lifecycle check in `delegate_authority()` (see 2.2).

**Recommended Mitigation:**
1. Check lifecycle status before delegation (see 2.2)
2. Add trigger to revoke authority on termination (see 5.1)
3. Add CHECK constraint:
   ```sql
   ALTER TABLE workers ADD CONSTRAINT check_authority_requires_active
   CHECK (
       hiring_authority_scope IS NULL
       OR status IN ('onboarding', 'active')
   );
   ```

### 7.4 Audit Trail Tampering

**Attack:** Manager modifies delegation records to hide unauthorized grants.

**Current Vulnerability:** No audit log for delegation operations.

**Recommended Mitigation:**
```sql
-- Add delegation audit table
CREATE TABLE delegation_audit (
    id TEXT PRIMARY KEY,
    operation TEXT NOT NULL CHECK(operation IN ('grant', 'revoke', 'modify')),
    delegator_id TEXT NOT NULL,
    grantee_id TEXT NOT NULL,
    scope_before TEXT,
    scope_after TEXT,
    budget_before INTEGER,
    budget_after INTEGER,
    actor_id TEXT NOT NULL,  -- Who performed the operation
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    reason TEXT
);

CREATE INDEX idx_delegation_audit_grantee ON delegation_audit(grantee_id);
CREATE INDEX idx_delegation_audit_timestamp ON delegation_audit(timestamp);
```

**Immutable Audit Trail (Append-Only):**
```sql
-- Prevent UPDATE/DELETE on audit table
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

### 7.5 Cost Inflation Attack

**Attack:** Worker delegates authority with higher max_cost than allowed, enabling expensive hires.

**Current Protection:** `delegate_authority()` checks:
```python
if scope.max_cost > own_scope.max_cost:
    raise InsufficientHiringAuthority(...)
```

✅ **PROTECTED**

**Edge Case:** What if max_cost is set very high but total_budget is low?

**Scenario:**
```
Manager has: max_cost=100, max_total_budget=10,000
Tries to hire worker with cost=95
Cost is within max_cost (95 <= 100) ✓
But total_budget allows only ~10 such hires
```

**Current Behavior:** `can_hire()` checks `max_total_budget` (line 444-466).

✅ **PROTECTED**

---

## 8. Recommended Safeguards (Priority Order)

### Priority 1: Critical Security Fixes

1. **Add Self-Delegation Prevention**
   - File: `cli/core/worker.py:delegate_authority()`
   - Add: `if report.id == self.id: raise ValueError("Cannot delegate to self")`

2. **Add Lifecycle Checks**
   - File: `cli/core/worker.py:delegate_authority()`
   - Add: Status checks for both delegator and grantee (see 2.2)

3. **Add Database Constraint for Terminated Workers**
   - File: `cli/core/db.py` (migration)
   - Add CHECK constraint preventing authority on terminated workers

### Priority 2: Data Integrity Protection

4. **Implement Optimistic Locking for Delegation**
   - File: `cli/core/worker.py:delegate_authority()`
   - Add: `delegation_version` field and compare-and-swap logic (see 2.1)

5. **Create delegation_grants Tracking Table**
   - File: `cli/core/db.py` (migration v17)
   - Add: Full delegation history table (see 1.3)

6. **Add Circular Delegation Detection**
   - File: `cli/core/worker.py` (new function)
   - Add: `_check_delegation_cycle()` (see 1.3)

### Priority 3: Audit & Compliance

7. **Add Delegation Audit Log**
   - File: `cli/core/db.py` (migration)
   - Add: Immutable audit table (see 7.4)

8. **Implement Cascading Revocation**
   - File: `cli/core/worker.py` (new function)
   - Add: `revoke_delegation_cascade()` (see 3.3)

9. **Add Trigger for Auto-Revocation on Termination**
   - File: `cli/core/db.py` (migration)
   - Add: Trigger to revoke delegations when worker terminated (see 5.1)

### Priority 4: Migration & Maintenance

10. **Create Migration for Existing Orgs**
    - File: `cli/commands/admin/migrate_delegation.py` (new)
    - Add: Backfill script for existing workers (see 6.1)

11. **Add Authority Validation on Manager Change**
    - File: `cli/core/worker.py` or `cli/core/org.py`
    - Add: Revoke authority when worker reassigned (see 5.2)

12. **Add Budget Delegation Limits**
    - File: `cli/core/db.py` (migration)
    - Add: `max_delegation_percent` field and validation (see 7.2)

---

## 9. Testing Strategy

### Unit Tests Required

```python
# cli/tests/test_delegation_safety.py

def test_self_delegation_prevented():
    """Cannot delegate authority to self."""
    manager = Worker.get(db, "alice")
    with pytest.raises(ValueError, match="Cannot delegate to self"):
        manager.delegate_authority(
            report=manager,
            budget=1000,
            scope=HiringScope(allowed_roles={"engineer"}, max_cost=50)
        )

def test_circular_delegation_detected():
    """Detect circular delegation chains."""
    # A → B → C → attempt A (should fail)
    alice = Worker.get(db, "alice")
    bob = Worker.get(db, "bob")  # bob reports to alice
    carol = Worker.get(db, "carol")  # carol reports to bob

    alice.delegate_authority(bob, 1000, ...)  # Alice → Bob ✓
    bob.delegate_authority(carol, 500, ...)    # Bob → Carol ✓

    # Now try to make Alice report to Carol (hierarchy inversion)
    with pytest.raises(DelegationCycleError):
        carol.delegate_authority(alice, 200, ...)  # Would create cycle

def test_concurrent_delegation_fails():
    """Concurrent delegations handled with optimistic locking."""
    alice = Worker.get(db, "alice")

    # Simulate concurrent delegation
    def delegate_to_bob():
        bob = Worker.get(db, "bob")
        alice.delegate_authority(bob, 8000, ...)

    def delegate_to_carol():
        carol = Worker.get(db, "carol")
        alice.delegate_authority(carol, 8000, ...)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(delegate_to_bob)
        f2 = executor.submit(delegate_to_carol)

        # One should succeed, one should fail
        results = [f1.result(), f2.result()]
        assert sum(1 for r in results if isinstance(r, Exception)) == 1

def test_terminated_worker_authority_revoked():
    """Authority auto-revoked when worker terminated."""
    alice = Worker.get(db, "alice")

    # Alice has authority
    assert alice.hiring_authority_scope.allowed_roles == {"engineer"}

    # Terminate Alice
    alice.terminate()

    # Authority should be gone
    alice.refresh()
    assert alice.hiring_authority_scope.allowed_roles == set()

def test_cascading_revocation():
    """Sub-delegations revoked when source authority removed."""
    # CEO → Alice → Bob → Carol
    ceo.delegate_authority(alice, 10000, ...)
    alice.delegate_authority(bob, 5000, ...)
    bob.delegate_authority(carol, 2000, ...)

    # Revoke Alice's authority
    revoke_authority(db, alice.id, cascade=True)

    # Bob and Carol should also lose authority
    bob.refresh()
    carol.refresh()
    assert bob.hiring_authority_scope.allowed_roles == set()
    assert carol.hiring_authority_scope.allowed_roles == set()
```

### Integration Tests Required

```python
# cli/tests/test_delegation_integration.py

def test_full_delegation_lifecycle():
    """Test complete delegation flow: grant → use → revoke."""
    # ... comprehensive end-to-end test

def test_manager_reassignment_revokes_authority():
    """Worker's authority revoked when reassigned to new manager."""
    # ... test reassignment logic

def test_org_migration_preserves_authority():
    """Schema migration doesn't break existing authority grants."""
    # ... test backward compatibility
```

---

## 10. Monitoring & Observability

### Metrics to Track

```python
# cli/core/metrics.py

class DelegationMetrics:
    """Metrics for delegation system health."""

    def count_active_delegations(self, db: Database) -> int:
        """Total active delegation grants."""
        return db.fetchone(
            "SELECT COUNT(*) FROM delegation_grants WHERE revoked_at IS NULL"
        )[0]

    def count_delegation_depth(self, db: Database) -> dict[int, int]:
        """Distribution of delegation chain depths."""
        # depth 0: direct from CEO
        # depth 1: CEO → Director → this worker
        # depth 2: CEO → Director → Manager → this worker
        # etc.
        pass

    def count_orphaned_authority(self, db: Database) -> int:
        """Workers with authority but terminated manager."""
        return db.fetchone(
            """SELECT COUNT(*) FROM workers w
               WHERE w.hiring_authority_scope IS NOT NULL
               AND w.manager_id IN (
                   SELECT id FROM workers WHERE status = 'terminated'
               )"""
        )[0]

    def count_over_allocated_budget(self, db: Database) -> int:
        """Workers who have delegated more budget than they have."""
        # Should always be 0
        pass
```

### Alerts to Configure

1. **Orphaned Authority Alert**
   - Trigger: `count_orphaned_authority() > 0`
   - Severity: HIGH
   - Action: Manual review required

2. **Deep Delegation Chain Alert**
   - Trigger: Any delegation chain depth > 5
   - Severity: MEDIUM
   - Action: Review org structure

3. **Budget Over-Allocation Alert**
   - Trigger: `count_over_allocated_budget() > 0`
   - Severity: CRITICAL
   - Action: Immediate investigation (data corruption)

---

## 11. Comparison to Similar Systems

### QuinnAI Permission System

**File:** `cli/core/authorization.py`

**Pattern:**
- Authorization checks via `AuthorizationManager.can(worker_id, permission, target_id)`
- Permissions like "hire", "fire", "delegate_budget", "escalate"
- Checks include reporting relationship, lifecycle status, budget availability

**Similarities to Delegation:**
- Both check reporting relationships
- Both verify lifecycle status
- Both have cascading effects (permission inheritance)

**Difference:**
- Permissions are check-only (no state modification)
- Delegation modifies database state (grants authority)

**Lessons to Apply:**
1. Use manager pattern (`AuthorizationManager`) for delegation checks
2. Centralize validation logic
3. Add comprehensive permission enum

### QuinnAI OKR System

**File:** `cli/core/queries.py:3174` (OKR cascade)

**Pattern:**
- OKRs cascade: Board → CEO → Directors → Managers → Workers
- Parent OKR relationship tracked via `parent_okr_id`
- Hierarchy queries via recursive CTEs

**Lessons to Apply:**
1. Track parent relationship (`delegated_by` field)
2. Use recursive queries for cascade operations
3. Validate hierarchy integrity (no cycles)

### QuinnAI Budget System

**File:** `cli/core/budget.py:471`

**Pattern:**
- Budget flows: Org Pool → CEO → Directors → Managers → Workers
- `source_worker_id` tracks where budget came from
- Transactions are atomic (wrapped in `db.transaction()`)
- Immutable ledger (`budget_transactions` table)

**Lessons to Apply:**
1. Use transaction wrapping for state modifications
2. Track source of authority (`source_worker_id` equivalent)
3. Create immutable audit trail
4. Use triggers to maintain consistency

**Key Insight:** Delegation is analogous to budget allocation - both are cascading authority transfers. Use same patterns.

---

## 12. Conclusion

The current hiring authority delegation implementation in QuinnAI provides basic validation but lacks critical safety mechanisms for production use. The most serious vulnerabilities are:

1. **No delegation tracking** - Impossible to audit or revoke delegations
2. **No concurrency protection** - Race conditions can cause over-allocation
3. **No cascading revocation** - Sub-delegations persist after source authority removed
4. **No lifecycle integration** - Terminated workers can retain/grant authority

**Immediate Actions (Must-Fix Before Production):**
- Add self-delegation prevention check
- Add lifecycle status checks to `delegate_authority()`
- Create `delegation_grants` table for tracking
- Implement cascading revocation logic

**Medium-Term Actions (Improve Robustness):**
- Add optimistic locking for concurrent delegation
- Add circular delegation detection
- Create delegation audit log
- Build monitoring dashboards

**Long-Term Actions (Scale & Compliance):**
- Implement time-based delegation expiration
- Add role-based delegation policies
- Create compliance reporting tools
- Build automated delegation review system

This analysis provides a foundation for hardening the delegation system against edge cases and attacks. Prioritize the immediate actions to prevent data corruption and security vulnerabilities in production deployments.

---

**Appendix: Database Schema Additions**

See inline SQL in sections above for complete schema changes. Key additions:

```sql
-- Track delegation relationships
CREATE TABLE delegation_grants (...);

-- Audit all delegation operations (immutable)
CREATE TABLE delegation_audit (...);

-- Add version field for optimistic locking
ALTER TABLE workers ADD COLUMN delegation_version INTEGER;

-- Constraints to prevent invalid states
ALTER TABLE workers ADD CONSTRAINT check_authority_requires_active ...;
CREATE TRIGGER prevent_delegation_to_terminated ...;
CREATE TRIGGER revoke_delegations_on_termination ...;
```

**File References:**
- Current implementation: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/worker.py:564-623`
- Database schema: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/db.py`
- Authorization patterns: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/authorization.py`
- Budget cascade reference: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/budget.py:471`
