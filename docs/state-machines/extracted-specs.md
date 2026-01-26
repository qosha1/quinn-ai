# Extracted State Machine Specifications
**Task:** quinnai-mf6e
**Source:** Audit documents in docs/audits/
**Date:** 2026-01-25

---

## 1. Org Lifecycle State Machine

**Source:** org-start-audit-2026-01-25.md, org-stop-audit-2026-01-25.md

### States
```
uninitialized → initialized → running ⇄ stopped
```

#### State Definitions
- **uninitialized**: Org directory exists but no quinn.db created
- **initialized**: Database created, CEO worker created, ready to start
- **running**: Org operational, workers can spawn sessions
- **stopped**: Org paused, sessions terminated, can resume

### Transitions

#### T1: uninitialized → initialized (`qn org init`)
**Preconditions:**
- Org directory exists
- No quinn.db file exists

**Actions:**
1. Create root team (Executive)
2. Create CEO worker (no manager, high cost tier)
3. Add CEO to team_members table
4. Create budget pool and allocation
5. Subscribe CEO to team channel
6. Create org-wide channels (general, board-channel)
7. Initialize beads database (`.beads/`)
8. Update org_status to 'initialized'

**Postconditions:**
- org_status = 'initialized'
- CEO worker exists with lifecycle_status = 'pending'
- Budget allocated to CEO
- Channels created and CEO subscribed

**Error Cases:**
- Database creation fails → rollback, remove quinn.db
- CEO creation fails → rollback transaction

#### T2: initialized → running (`qn org start`, first time)
**Preconditions:**
- org_status = 'initialized'
- CEO worker exists
- Provider config valid

**Actions:**
1. Validate state transition
2. Get CEO worker instance
3. CEO.start_onboarding() → CEO lifecycle = 'onboarding'
4. CEO.complete_onboarding() → CEO lifecycle = 'active'
5. Deliver CEO briefing (if config/ceo_briefing.md exists):
   - Create message in board-channel
   - Create notification bead (P0)
6. Update org_status to 'running'
7. Update org-chart
8. Spawn CEO session (if --spawn-ceo=True):
   - prepare_worker_onboarding()
   - generate_welcome_message()
   - spawn_session()

**Postconditions:**
- org_status = 'running'
- CEO lifecycle_status = 'active'
- CEO session spawned (if requested)
- Briefing delivered (if exists)

**Error Cases:**
- CEO activation fails → INCONSISTENT STATE (org running, CEO not active)
- Session spawn fails → INCONSISTENT STATE (org running, CEO session dead)
- **NO ROLLBACK IMPLEMENTED**

**Critical Gap:** Partial failures leave org in inconsistent state

#### T3: running → stopped (`qn org stop`)
**Preconditions:**
- org_status = 'running'

**Actions:**
1. Stop all worker sessions:
   - Call stop_all_sessions(db, force=force)
   - Report stopped/failed counts
2. Validate state transition
3. Update org_status to 'stopped'
4. Log state change
5. Run notification cleanup (if --cleanup=True)

**Postconditions:**
- org_status = 'stopped'
- Worker sessions stopped (best-effort)
- Old notifications purged

**Error Cases:**
- Some sessions fail to stop → Continues anyway, shows warnings
- Cleanup fails → Org already stopped, no rollback

**Critical Gap:** No verification that sessions actually stopped

#### T4: stopped → running (`qn org start`, resume)
**Preconditions:**
- org_status = 'stopped'

**Actions:**
1. Validate state transition
2. Update org_status to 'running'
3. Log state change
4. **NO CEO SESSION SPAWN** (different from T2!)

**Postconditions:**
- org_status = 'running'
- CEO lifecycle unchanged (already 'active')
- **NO CEO SESSION** (must manually spawn)

**Critical Gap:** Inconsistent behavior - resume doesn't spawn CEO session

### Invalid Transitions
- initialized → stopped (must start first)
- uninitialized → running (must init first)
- running → uninitialized (can't un-init)
- stopped → initialized (can't re-init)

### Dependencies
- **CEO Worker Lifecycle:** CEO must activate during T2
- **Session Lifecycle:** Sessions must stop during T3
- **Budget:** Budget allocation happens during T1

---

## 2. Worker Lifecycle State Machine

**Source:** org-start-audit-2026-01-25.md, stub-audit-2026-01-25.md, cli/core/worker.py

### States
```
pending → onboarding → active → suspended → terminated
                ↓
         (terminated from any state)
```

#### State Definitions
- **pending**: Worker created but not onboarded (can't spawn sessions)
- **onboarding**: Activation in progress (briefing, context generation)
- **active**: Fully operational, can spawn sessions and do work
- **suspended**: Temporarily inactive (can't spawn sessions, preserve state)
- **terminated**: Permanently removed from org

### Transitions

#### T1: pending → onboarding (`start_onboarding()`)
**Preconditions:**
- Worker exists with lifecycle_status = 'pending'

**Actions:**
1. Validate lifecycle transition
2. Update lifecycle_status to 'onboarding'
3. Trigger onboarding sequence (see Onboarding State Machine)

**Postconditions:**
- lifecycle_status = 'onboarding'

#### T2: onboarding → active (`complete_onboarding()`)
**Preconditions:**
- lifecycle_status = 'onboarding'
- Onboarding sequence completed (briefing, context, directory)

**Actions:**
1. Validate lifecycle transition
2. Update lifecycle_status to 'active'
3. Worker can now spawn sessions

**Postconditions:**
- lifecycle_status = 'active'
- can_work = True
- Sessions can be spawned

#### T3: active → suspended (`suspend()`)
**Preconditions:**
- lifecycle_status = 'active'
- No active session OR force=True

**Actions:**
1. Validate lifecycle transition
2. Stop active session (if exists)
3. Update lifecycle_status to 'suspended'

**Postconditions:**
- lifecycle_status = 'suspended'
- can_work = False
- Sessions cannot be spawned

#### T4: suspended → active (`unsuspend()`)
**Preconditions:**
- lifecycle_status = 'suspended'

**Actions:**
1. Validate lifecycle transition
2. Update lifecycle_status to 'active'

**Postconditions:**
- lifecycle_status = 'active'
- can_work = True

#### T5: any → terminated (`terminate()`)
**Preconditions:**
- Worker exists

**Actions:**
1. Stop active session (if exists, force=True)
2. Update lifecycle_status to 'terminated'
3. **Note:** Worker record remains in database (soft delete)

**Postconditions:**
- lifecycle_status = 'terminated'
- can_work = False
- Cannot spawn sessions
- Cannot transition to any other state

### Dependencies
- **Session Lifecycle:** Can only spawn session when lifecycle = 'active'
- **Org Lifecycle:** CEO activation triggered during org start (T2 of Org)
- **Onboarding Sequence:** Triggered during T1, must complete before T2

---

## 3. Session Lifecycle State Machine

**Source:** status-sync-audit-2026-01-25.md, org-stop-audit-2026-01-25.md

### States
```
not_spawned → starting → running ⇄ idle
                  ↓          ↓       ↓
              working → blocked
                  ↓
              stopped / crashed
```

#### State Definitions
- **not_spawned**: No session exists for worker
- **starting**: Session spawn in progress (process creating, connecting)
- **running**: Session ready and operational
- **idle**: Session ready but not processing tasks
- **working**: Actively executing a task
- **blocked**: Waiting on external dependency (escalation, I/O)
- **stopped**: Cleanly terminated session
- **crashed**: Abnormally terminated (error, timeout, kill)

### Transitions

#### T1: not_spawned → starting (`spawn_session()`)
**Preconditions:**
- Worker lifecycle_status = 'active'
- No existing active session
- Budget available (or is_ceo bypass)

**Actions:**
1. Validate worker can spawn session
2. Estimate spawn cost
3. Check budget allocation
4. Create session via registry (adapter-specific)
5. Update worker_state.runtime_status = 'starting'
6. Update worker_state.pid if available
7. Record spend against budget
8. Create session record in database

**Postconditions:**
- worker_state.runtime_status = 'starting'
- Session process spawning
- Budget deducted
- Session record exists

**Error Cases:**
- BudgetExhaustedError → Session not spawned
- ActiveSessionExistsError → Cannot spawn duplicate
- Provider error → Clean up budget deduction?

**Critical Gap:** Rollback on failure unclear

#### T2: starting → running (`session_ready()`)
**Preconditions:**
- worker_state.runtime_status = 'starting'
- Session adapter reports ready

**Actions:**
1. Validate runtime transition
2. Update worker_state.runtime_status = 'running'
3. Session is now available for work

**Postconditions:**
- worker_state.runtime_status = 'running'
- Session can accept tasks

**Critical Gap:** Session adapter state change doesn't automatically call this!

#### T3: running ⇄ idle (`begin_work()` / `finish_work()`)
**Preconditions:**
- worker_state.runtime_status = 'running' or 'idle'

**Actions (running → idle):**
1. Validate runtime transition
2. Update worker_state.runtime_status = 'idle'
3. Clear current_task_id

**Actions (idle → running):**
1. Validate runtime transition
2. Update worker_state.runtime_status = 'running'

**Postconditions:**
- worker_state.runtime_status updated
- Task assignment/completion reflected

#### T4: running → working (task assigned)
**Preconditions:**
- worker_state.runtime_status = 'running' or 'idle'
- Task assigned to worker

**Actions:**
1. Update worker_state.runtime_status = 'working'
2. Set worker_state.current_task_id

**Postconditions:**
- worker_state.runtime_status = 'working'
- current_task_id set

#### T5: working → blocked (escalation / waiting)
**Preconditions:**
- worker_state.runtime_status = 'working'
- Worker needs external help or resource

**Actions:**
1. Update worker_state.runtime_status = 'blocked'
2. Record blocking reason

**Postconditions:**
- worker_state.runtime_status = 'blocked'
- Worker cannot proceed until unblocked

#### T6: blocked → working (issue resolved)
**Preconditions:**
- worker_state.runtime_status = 'blocked'
- Blocking issue resolved

**Actions:**
1. Update worker_state.runtime_status = 'working'
2. Resume task execution

**Postconditions:**
- worker_state.runtime_status = 'working'

#### T7: any → stopped (`stop_session()`)
**Preconditions:**
- Session exists

**Actions:**
1. Gracefully stop session (signal handler, cleanup)
2. Update worker_state.runtime_status = 'stopped'
3. Clear worker_state.pid
4. Update session record state = 'stopped'

**Postconditions:**
- worker_state.runtime_status = 'stopped'
- Session process terminated
- can_work = False

#### T8: any → crashed (error / timeout / kill)
**Preconditions:**
- Session exists and encounters fatal error

**Actions:**
1. Detect crash (process exit, exception, timeout)
2. Update worker_state.runtime_status = 'crashed'
3. Clear worker_state.pid
4. Update session record state = 'crashed'
5. Log error details

**Postconditions:**
- worker_state.runtime_status = 'crashed'
- Session terminated abnormally
- Error logged for debugging

**Critical Gap:** Crash detection may not trigger this update!

### Dependencies
- **Worker Lifecycle:** Session can only be spawned when worker = 'active'
- **Budget:** Budget check happens during T1
- **Status Sync:** ALL transitions should update worker_state table

### Critical Issue: No Automatic Status Propagation
**Problem:** Session adapters change state internally but don't call Worker methods
- T2 (session_ready) must be called manually
- T7/T8 (stop/crash) must be called manually
- Session state ≠ worker_state.runtime_status

**Fix Required:** Session adapters need callbacks to update worker_state

---

## 4. Status Sync Propagation Flow

**Source:** status-sync-audit-2026-01-25.md

This is a **data propagation pipeline**, not a traditional state machine.

### Current (Broken) Flow

```
Session State Change (in adapter)
    ↓
  ❌ NO CALLBACK
    ↓
Worker._state_data (cached, stale)
    ↓
  ❌ worker_state table NOT updated
    ↓
Terminal UI polls database
    ↓
  ❌ Shows stale data
```

### Desired Flow

```
Session State Change (in adapter)
    ↓
Callback: _on_state_change(old, new)
    ↓
update_worker_runtime_status(db, worker_id, runtime_status)
    ↓
worker_state table UPDATED (commit)
    ↓
Terminal UI auto-refresh (polling or push)
    ↓
Fresh data displayed (< 2 seconds)
```

### Components

#### 1. Session Adapter State Change
**Location:** cli/core/sessions/claude_code.py, gemini.py
**Current:** Callbacks exist but don't update database
**Required:** Map session state → worker runtime_status, call update function

#### 2. Worker State Update
**Location:** cli/core/queries.py::update_worker_runtime_status()
**Current:** Direct database UPDATE, no validation
**Required:** Transaction, validation, consistency check

#### 3. Cache Invalidation
**Location:** cli/core/worker.py::runtime_status property
**Current:** Lazy load with caching (_state_data)
**Required:** Always reload for runtime_status (frequently changing)

#### 4. UI Refresh
**Location:** terminal-app/src/board_ui/views/team.py
**Current:** Manual refresh only (on mount, navigation)
**Required:** Periodic polling (every 2 seconds) OR push notifications

### Latency Requirements
- Session state change → Database update: **< 500ms**
- Database update → UI display: **< 2 seconds**
- Total end-to-end: **< 2.5 seconds**

### Consistency Guarantees
- **Eventually Consistent:** UI may lag database by up to 2 seconds
- **No Lost Updates:** All session state changes must propagate to database
- **No Stale Reads:** UI must not cache data longer than 2 seconds

---

## 5. Onboarding Sequence State Machine

**Source:** org-start-audit-2026-01-25.md, cli/core/onboarding.py

This is a **sequential workflow** within the Worker 'onboarding' lifecycle state.

### Phases (Sequential)

#### Phase 1: Briefing Preparation
**Input:** Worker ID, org path
**Actions:**
- Load worker data from database
- Determine if briefing exists (config/{role}_briefing.md)
- Read briefing content (if exists)
**Output:** Briefing content or None

#### Phase 2: Context Generation
**Input:** Worker data, org structure
**Actions:**
- Generate CLAUDE.md (role-specific instructions)
- Generate AGENTS.md (team hierarchy, escalation paths)
- Generate README.md (worker overview)
**Output:** Context files created in onboarding/configs/

#### Phase 3: Directory Setup
**Input:** Org path, worker ID
**Actions:**
- Create storage/workers/{worker_id}/
- Copy CLAUDE.md, AGENTS.md, README.md to worker dir
**Output:** Worker directory ready

#### Phase 4: Environment Variables
**Input:** Onboarding context, org path
**Actions:**
- Generate env vars (BRIEFING_PATH, WORKER_ID, etc)
**Output:** Dict of environment variables

#### Phase 5: Welcome Message
**Input:** Onboarding context, worker dir
**Actions:**
- Generate welcome message (first or returning)
- For first-time: Include briefing reference
- For returning: "Welcome back" message
**Output:** Welcome message string

#### Phase 6: Session Spawn
**Input:** Worker, SessionConfig
**Actions:**
- Create session via registry
- Attach session to worker
- Start session process
**Output:** Active session

#### Phase 7: Completion
**Input:** Worker ID
**Actions:**
- Worker.complete_onboarding() → lifecycle = 'active'
**Output:** Worker ready for work

### CEO Special Case

For CEO during org start (T2), additional steps:
- **Briefing Delivery:** Create message in board-channel with briefing
- **Notification:** Create P0 notification bead for CEO
- **Check Duplicate:** Don't deliver briefing twice

### Error Handling

**Failure Recovery:**
- Phases 1-5: Retryable (idempotent, no side effects)
- Phase 6: **NOT IDEMPOTENT** - spawns process, deducts budget
- Phase 7: Updates database state

**Rollback Strategy:**
- If Phase 6 fails: Kill spawned process, refund budget?
- If Phase 7 fails: Worker stuck in 'onboarding' state

**Idempotency:**
- Re-running Phases 1-5 is safe (regenerate files)
- Re-running Phase 6 should check for existing session first
- Re-running Phase 7 should check current lifecycle state

### Resume Capability

**Question:** Can onboarding resume from partial completion?
**Current:** No checkpoint system - must restart from Phase 1
**Desired:** Checkpoint after each phase, resume from last successful

---

## 6. Budget Enforcement State Machine

**Source:** org-start-audit-2026-01-25.md, cli/core/worker.py spawn_session()

This is a **decision tree** within session spawn (T1 of Session Lifecycle).

### Decision Flow

```
Session Spawn Requested
    ↓
Estimate Spawn Cost (based on worker.cost tier)
    ↓
Check Budget Allocation exists?
    ├─ No → Raise NoBudgetAllocationError
    ↓
Check allocated_credits >= cost?
    ├─ No → Raise BudgetExhaustedError
    ↓
Check is_ceo?
    ├─ Yes → BYPASS (continue without deduction)
    ↓
Deduct cost from allocation
    ↓
Record spend in budget table
    ↓
Proceed with session spawn
```

### States (Implicit)

- **budget_check_pending**: Before spawn, need to check budget
- **budget_available**: Sufficient credits, can proceed
- **budget_exhausted**: Insufficient credits, cannot proceed
- **spend_recorded**: Cost deducted, spawn proceeding

### Cost Estimation

**Algorithm:** Based on worker.cost tier (from workers table)
```python
if worker.cost <= 10:
    spawn_cost = 1.0  # Low tier
elif worker.cost <= 50:
    spawn_cost = 5.0  # Medium tier
else:
    spawn_cost = 10.0  # High tier (CEO)
```

**Note:** CEO has high cost but bypasses budget checks (is_ceo flag)

### Budget Check Queries

**Get Allocation:**
```sql
SELECT allocated_credits, spent_credits
FROM budget_allocations
WHERE worker_id = ? AND period_end > NOW()
```

**Check Availability:**
```python
remaining = allocated_credits - spent_credits
if remaining < spawn_cost:
    raise BudgetExhaustedError
```

### Spend Recording

**Update Allocation:**
```sql
UPDATE budget_allocations
SET spent_credits = spent_credits + ?
WHERE worker_id = ? AND period_end > NOW()
```

**Record Transaction:**
```sql
INSERT INTO budget_transactions (
    allocation_id, amount, transaction_type,
    description, created_at
) VALUES (?, ?, 'debit', 'Session spawn', NOW())
```

### Rollback Strategy

**Question:** If session spawn fails after budget deducted, refund?
**Current:** NO ROLLBACK - budget deducted even if spawn fails
**Desired:** Transaction wrapping budget + spawn, rollback on failure

### Special Cases

#### CEO Bypass
```python
if worker.role == 'CEO':
    # Skip budget checks, spawn directly
    return spawn_session_without_budget_check()
```

#### Budget Delegation
- Managers can allocate portion of their budget to reports
- `can_delegate` flag on allocation
- `delegation_limit` caps max delegation per subordinate

---

## Cross-Machine Dependencies

### Dependency Graph

```
Org Lifecycle
    ├─ triggers → Worker Lifecycle (CEO activation)
    └─ requires → Session Lifecycle (stop all sessions)

Worker Lifecycle
    ├─ gates → Session Lifecycle (must be 'active')
    └─ triggers → Onboarding Sequence (during activation)

Session Lifecycle
    ├─ requires → Worker Lifecycle = 'active'
    ├─ requires → Budget Enforcement (during spawn)
    └─ updates → Status Sync (all state changes)

Onboarding Sequence
    ├─ part of → Worker Lifecycle (onboarding state)
    └─ triggers → Session Spawn (Phase 6)

Budget Enforcement
    └─ part of → Session Spawn (precondition check)

Status Sync
    ├─ reads → Session Lifecycle (runtime_status)
    └─ updates → Worker State (worker_state table)
```

### Validation Rules

1. **Cannot spawn session if worker ≠ active**
   - Session.spawn() checks worker.lifecycle_status
   - Raise error if not 'active'

2. **CEO activation happens during org start**
   - Org.start() (initialized → running) triggers:
   - CEO.start_onboarding() → CEO.complete_onboarding()

3. **All sessions must stop before org stop completes**
   - Org.stop() calls stop_all_sessions()
   - Should verify all stopped before updating org_status

4. **Session state changes must update worker_state**
   - Every session transition should call update_worker_runtime_status()
   - Currently BROKEN - manual calls only

5. **Budget check gates session spawn**
   - Session.spawn() must call budget check before proceeding
   - CEO bypass OR sufficient credits required

---

## Implementation Status

### ✅ Implemented & Working
- Org lifecycle transitions (basic state updates)
- Worker lifecycle transitions (basic state updates)
- Budget enforcement (checks and recording)

### ⚠️ Partially Implemented
- Session lifecycle (states exist, but manual transitions only)
- Onboarding sequence (works but no error recovery)
- Status sync (database updates work, but not automatic)

### ❌ Not Implemented / Broken
- **Session state → worker_state propagation** (CRITICAL)
- **UI auto-refresh** (UI shows stale data)
- **Rollback on failures** (partial failures leave inconsistent state)
- **Org start resume behavior** (doesn't spawn CEO session)
- **Session stop verification** (org stops even if sessions fail)
- **Onboarding checkpointing** (can't resume partial onboarding)
- **Budget rollback** (budget deducted even if spawn fails)

---

## Next Steps

1. Design STATEMACHINES.md format (quinnai-3gls)
2. Create individual state machine documentation (quinnai-rzg5, 1t0c, gng3, 6h5i, jlmw, jer3)
3. Write unified STATEMACHINES.md (quinnai-kpgu)
4. Validate implementation (quinnai-14r7)
5. Create validation tests (quinnai-oven)
6. Run systemeval tests (quinnai-g0si)
