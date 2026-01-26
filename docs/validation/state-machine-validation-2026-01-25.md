# State Machine Implementation Validation

**Date:** 2026-01-25
**Validated Against:** STATEMACHINES.md
**Status:** ❌ Multiple critical mismatches found

## Summary

| State Machine | Status | Critical Issues |
|---------------|--------|-----------------|
| Org Lifecycle | ⚠️ Partial | No rollback, resume inconsistency |
| Worker Lifecycle | ❌ MISMATCH | States don't match documentation |
| Session Lifecycle | ❌ MISMATCH | Missing working/blocked states |
| Status Sync | ❌ Broken | No automatic propagation |
| Onboarding Sequence | ⚠️ Partial | No checkpointing, no rollback |
| Budget Enforcement | ⚠️ Partial | No transaction wrapping |

---

## Org Lifecycle State Machine

**Implementation:** `cli/core/org.py`
**Validation Status:** ⚠️ Partial match with known gaps

### States: ✅ MATCH

**Documented:** uninitialized, initialized, running, stopped
**Code:** Matches (`shared/state_machines.py:56`)

```python
ORG_STATES = frozenset([
    "uninitialized",
    "initialized",
    "running",
    "stopped",
])
```

### Transitions: ⚠️ Partial Implementation

#### T1: uninitialized → initialized

**Status:** ✅ Implemented
**Location:** `org.py:127` (`Org.init()`)
**Validation:** ✅ Calls `_validate_transition()` before state change
**Preconditions:** ✅ Checks current state via validation
**Actions:** ✅ All documented actions present:
- Creates root team
- Creates CEO worker
- Allocates budget
- Creates channels
- Initializes beads
**Error Handling:** ✅ DatabaseError handled (implicit transaction)

---

#### T2: initialized → running (first start)

**Status:** ⚠️ Implemented with **documented gaps**
**Location:** `org.py:223` (`Org.start()` - lines 234-250)
**Validation:** ✅ Calls `_validate_transition()`
**Preconditions:** ✅ Checks org_status == 'initialized'
**Actions:** ✅ All documented actions present:
- CEO.start_onboarding()
- CEO.complete_onboarding()
- Delivers briefing if exists
- Updates org_status
**Error Handling:** ❌ **MISSING** - No rollback on CEO activation failure

**VIOLATION: Incomplete**
```
Problem: If CEO.complete_onboarding() fails, org_status is already 'running'
Result: Inconsistent state (org running, CEO not active)
Expected: Transaction wrapping with rollback
Found: No try/except, no rollback
```

**Session Spawn:** ❌ **MISSING** - Code does NOT spawn CEO session
**Expected:** Lines from `qn org start` CLI should spawn CEO session with `--spawn-ceo=True`
**Found:** No spawn_session() call in org.py:start()
**Note:** Spawn may happen in CLI layer (`cli/commands/org/start.py`)

---

#### T3: running → stopped

**Status:** ⚠️ Implemented with **documented gaps**
**Location:** `org.py:351` (`Org.stop()`)
**Validation:** ✅ Calls `_validate_transition()`
**Preconditions:** ✅ Checks org_status == 'running'
**Actions:** ⚠️ Partial
- ✅ Updates org_status to 'stopped'
- ⚠️ Sessions stopped externally (not in this method)
**Error Handling:** ❌ **MISSING** - No verification sessions actually stopped

**VIOLATION: Incomplete**
```
Problem: Method assumes sessions already stopped
Result: Can transition to 'stopped' with active sessions still running
Expected: Call stop_all_sessions() and verify success
Found: No session management in Org.stop()
Note: Documentation says "Worker sessions should be stopped separately"
```

---

#### T4: stopped → running (resume)

**Status:** ❌ **BROKEN** - Inconsistent with T2
**Location:** `org.py:251-254`
**Validation:** ✅ Calls `_validate_transition()`
**Preconditions:** ✅ Checks org_status == 'stopped'
**Actions:** ❌ **INCOMPLETE** - Only updates status
**Error Handling:** ✅ InvalidOrgTransition raised

**VIOLATION: Incorrect**
```
Problem: Resume (T4) behaves differently than first start (T2)
T2 (first start): Activates CEO, delivers briefing, optionally spawns session
T4 (resume): ONLY updates org_status to 'running', nothing else
Expected: Consistent behavior - spawn CEO session like T2
Found: Different code paths with different behavior
Impact: CEO has no active session after org resume
```

---

### Validation Issues: Org Lifecycle

**MISSING (1):**
- Rollback mechanism on T2 failure

**INCOMPLETE (2):**
- T2: No error handling for CEO activation failure
- T3: No session stop verification

**INCORRECT (1):**
- T4: Inconsistent behavior compared to T2 (resume vs first start)

---

## Worker Lifecycle State Machine

**Implementation:** `cli/core/worker.py`
**Validation Status:** ❌ CRITICAL MISMATCH - States don't match

### States: ❌ MISMATCH

**Documented:** pending, onboarding, active, suspended, terminated

**Code:** (`shared/state_machines.py:13`)
```python
LIFECYCLE_STATES = frozenset([
    "pending",
    "onboarding",
    "active",
    "offboarding",    # ❌ NOT documented
    "terminated",
])
```

**VIOLATION: Extra State**
```
State: "offboarding"
Found in: shared/state_machines.py:17, LIFECYCLE_TRANSITIONS
Documented: NO - not in STATEMACHINES.md Worker Lifecycle
Impact: Code has state that's not in specification
```

**VIOLATION: Missing State**
```
State: "suspended"
Documented: YES - in STATEMACHINES.md Worker Lifecycle
Found in code: NO - not in LIFECYCLE_STATES
Impact: Documented transitions (active ⇄ suspended) cannot be implemented
```

### Transitions: ❌ MISMATCH

**Documented:**
```
pending → onboarding
onboarding → active
active ⇄ suspended
any → terminated
```

**Code:** (`shared/state_machines.py:21`)
```python
LIFECYCLE_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["onboarding"],           # ✅ Match
    "onboarding": ["active", "terminated"],  # ✅ Match
    "active": ["offboarding"],            # ❌ Mismatch
    "offboarding": ["terminated"],        # ❌ Extra
    "terminated": [],                     # ✅ Match
}
```

**VIOLATION: Missing Transitions**
```
Documented: active → suspended, suspended → active, suspended → terminated
Found: NONE of these in LIFECYCLE_TRANSITIONS
Impact: Cannot implement suspend/unsuspend as documented
```

**VIOLATION: Extra Transition**
```
Transition: active → offboarding → terminated
Found in: LIFECYCLE_TRANSITIONS (lines 24-25)
Documented: NO - offboarding not in specification
Impact: Code implements undocumented state and transition
```

### Implementation Methods: ⚠️ Partial Match

**Documented T1: pending → onboarding**
- ✅ Found: `worker.py:678` (`start_onboarding()`)
- ✅ Validation: Calls `_validate_lifecycle_transition()`
- ✅ Status: Implemented

**Documented T2: onboarding → active**
- ✅ Found: `worker.py:686` (`complete_onboarding()`)
- ✅ Validation: Calls `_validate_lifecycle_transition()`
- ✅ Status: Implemented

**Extra: onboarding → terminated**
- ✅ Found: `worker.py:694` (`fail_onboarding()`)
- ⚠️ Not documented in STATEMACHINES.md
- Status: Extra functionality (not a violation if valid use case)

**Documented T3: active → suspended**
- ❌ NOT FOUND - No `suspend()` method
- ❌ State 'suspended' not in LIFECYCLE_STATES
- Status: Missing

**Documented T4: suspended → active**
- ❌ NOT FOUND - No `unsuspend()` method
- ❌ State 'suspended' not in LIFECYCLE_STATES
- Status: Missing

**Documented T5: any → terminated**
- ✅ Found: `worker.py:888` (`terminate()`)
- ✅ Validation: Calls `_validate_lifecycle_transition()`
- ✅ Actions: Stops session, freezes storage, unsubscribes, updates org-chart
- ✅ Status: Implemented

---

### Validation Issues: Worker Lifecycle

**MISSING (1 state, 2 transitions):**
- State: 'suspended'
- Transition: active → suspended
- Transition: suspended → active

**EXTRA (1 state, 2 transitions):**
- State: 'offboarding'
- Transition: active → offboarding
- Transition: offboarding → terminated

**RECOMMENDATION:**
- Either: Update STATEMACHINES.md to document offboarding state
- Or: Remove offboarding from code and implement suspended state
- Decision needed: Which is the correct design?

---

## Session Lifecycle State Machine

**Implementation:** `cli/core/worker.py`, runtime status methods
**Validation Status:** ❌ MISMATCH - Missing working/blocked states

### States: ❌ MISMATCH

**Documented:** not_spawned, starting, running, idle, working, blocked, stopped, crashed

**Code:** (`shared/state_machines.py:33`)
```python
RUNTIME_STATES = frozenset([
    "starting",
    "running",
    "idle",
    "stopped",
    "crashed",
])
```

**VIOLATION: Missing States**
```
States: "working", "blocked"
Documented: YES - in STATEMACHINES.md Session Lifecycle
Found in code: NO - not in RUNTIME_STATES
Impact: Transitions T4, T5, T6 cannot be implemented
```

**Note:** 'not_spawned' is implicit (NULL runtime_status), not a database value

### Transitions: ⚠️ Partial Implementation

**Documented T1: not_spawned → starting**
- ✅ Found: `worker.py:1163` (`spawn_session()`)
- ✅ Budget enforcement: `_enforce_spawn_budget()` (line 1228)
- ✅ Validation: Checks for existing active session
- ✅ Actions: Updates runtime_status to 'starting'
- ⚠️ Rollback: ❌ MISSING - budget deducted before spawn

**Documented T2: starting → running**
- ✅ Found: `worker.py:1032` (`session_ready()`)
- ✅ Validation: Calls `_validate_runtime_transition()`
- ❌ **CRITICAL:** Session adapters DON'T call this automatically

**VIOLATION: Missing Callback**
```
Problem: session_ready() exists but is never called
Expected: Session adapters call worker.session_ready() when ready
Found: No callback from session adapters to worker methods
Impact: runtime_status stuck at 'starting', never transitions to 'running'
Status: DOCUMENTED in STATEMACHINES.md as "Critical Issue"
```

**Documented T3: running ⇄ idle**
- ✅ Found: `worker.py:1038, 1048` (`begin_work()`, `finish_work()`)
- ✅ Validation: Calls `_validate_runtime_transition()`
- ❌ **MANUAL ONLY** - No automatic triggers

**Documented T4: running → working**
- ❌ NOT FOUND - No method to transition to 'working'
- ❌ State 'working' not in RUNTIME_STATES
- Status: Missing

**Documented T5: working → blocked**
- ❌ NOT FOUND - No method to transition to 'blocked'
- ❌ State 'blocked' not in RUNTIME_STATES
- Status: Missing

**Documented T6: blocked → working**
- ❌ NOT FOUND - No method to resolve blocked state
- ❌ State 'blocked' not in RUNTIME_STATES
- Status: Missing

**Documented T7: any → stopped**
- ✅ Found: `worker.py:1059` (`stop_session()`)
- ✅ Validation: Calls `_validate_runtime_transition()`
- ✅ Actions: Updates runtime_status, clears pid
- ✅ Status: Implemented

**Documented T8: any → crashed**
- ✅ Found: `worker.py:1065` (`mark_crashed()`)
- ⚠️ Validation: Manual check instead of `_validate_runtime_transition()`
- ⚠️ May not be called on actual crashes

---

### Runtime Transitions: Code vs Documented

**Code:** (`shared/state_machines.py:41`)
```python
RUNTIME_TRANSITIONS: dict[str, list[str]] = {
    "starting": ["running", "crashed"],
    "running": ["idle", "stopped", "crashed"],
    "idle": ["running", "stopped"],
    "stopped": ["starting"],
    "crashed": ["starting"],
}
```

**Documented:**
```
starting → running (T2)
starting → crashed (T8)
running → idle (T3)
idle → running (T3)
running → working (T4) ❌ MISSING
working → blocked (T5) ❌ MISSING
blocked → working (T6) ❌ MISSING
working → idle (documented) ❌ MISSING
any → stopped (T7)
any → crashed (T8)
```

**VIOLATION: Incomplete State Machine**
```
Documented states: 8 (including not_spawned)
Code states: 5 (in RUNTIME_STATES)
Missing: working, blocked
Impact: Task assignment and escalation workflows cannot be tracked
```

---

### Validation Issues: Session Lifecycle

**MISSING (2 states, 4 transitions):**
- State: 'working'
- State: 'blocked'
- Transition: running → working
- Transition: working → blocked
- Transition: blocked → working
- Transition: working → idle

**INCOMPLETE (2):**
- T1: No rollback on spawn failure after budget deduction
- T2: Session adapters don't call session_ready() automatically

**BROKEN (1):**
- Status Sync: No automatic propagation from session to database

---

## Status Sync Propagation

**Implementation:** `cli/core/sessions/*.py`, `cli/core/worker.py`
**Validation Status:** ❌ BROKEN - No automatic callbacks

### Component 1: Session Adapter Callbacks

**Location:** `cli/core/sessions/claude_code.py`, `gemini.py`
**Expected:** `_on_state_change()` calls `update_worker_runtime_status()`
**Found:** ❌ NOT IMPLEMENTED

**VIOLATION: Missing Implementation**
```
Component: Session state change callback
Expected: session._on_state_change() → update_worker_runtime_status()
Found: _on_state_change() exists but doesn't update database
Impact: Session state changes don't propagate to worker_state table
Evidence: STATEMACHINES.md lines 226-257 document this as "Critical Issue"
```

### Component 2: Worker Runtime Status Update

**Location:** `cli/core/queries.py:677` (assumed)
**Expected:** Direct database UPDATE
**Status:** ⚠️ Assumed working (not validated in this pass)

### Component 3: Worker Cache Invalidation

**Location:** `cli/core/worker.py:600` (assumed)
**Expected:** Always reload runtime_status
**Found:** ❌ Likely caching (not validated in this pass)

### Component 4: UI Auto-Refresh

**Location:** `terminal-app/src/board_ui/views/team.py:76`
**Expected:** `set_interval(2.0, refresh_workers)`
**Found:** ❌ NOT IMPLEMENTED (documented as missing)

---

## Onboarding Sequence

**Implementation:** `cli/core/onboarding.py`
**Validation Status:** ⚠️ Partial - Works but no error recovery

### Phase Idempotency: ⚠️ Mixed

**Phases 1-5:** ✅ Idempotent (read-only or overwrite)
**Phase 6 (spawn_session):** ❌ NOT idempotent (deducts budget, spawns process)
**Phase 7 (complete_onboarding):** ✅ Idempotent (state update)

**VIOLATION: Incomplete - No Checkpointing**
```
Problem: Failure at Phase 6 requires restart from Phase 1
Expected: Checkpoint after each phase, resume from last checkpoint
Found: No checkpoint storage in worker_state table
Impact: Budget wasted if Phase 6 fails and must retry
Status: DOCUMENTED in STATEMACHINES.md lines 201-215
```

**VIOLATION: Incomplete - No Rollback**
```
Problem: Phase 6 failure leaves budget deducted with no session
Expected: Transaction wrapping budget + spawn
Found: No rollback mechanism
Impact: Budget leak on spawn failure
Status: DOCUMENTED in STATEMACHINES.md lines 188-198
```

---

## Budget Enforcement

**Implementation:** `cli/core/worker.py:1228` (`_enforce_spawn_budget()`)
**Validation Status:** ⚠️ Partial - No transaction wrapping

### Decision Flow: ✅ Implemented

**Cost Estimation:** ✅ Line 1245 (`estimate_cost()`)
**Budget Check:** ✅ Line 1252 (`enforce_budget()`)
**CEO Bypass:** ⚠️ Assumed (not validated in this pass)

**VIOLATION: Incomplete - No Transaction Wrapping**
```
Problem: Budget deducted before session spawn
Expected: Transaction { deduct budget; spawn session; commit }
Found: Budget deducted in _enforce_spawn_budget(), spawn in _start_session()
Impact: Budget lost if spawn fails after deduction
Code location: worker.py:1186-1192 (sequential, not transactional)
Status: DOCUMENTED in STATEMACHINES.md lines 116-151
```

---

## Summary of Violations

### Critical (Must Fix)

1. **Worker Lifecycle State Mismatch** - Code has 'offboarding', doc has 'suspended'
2. **Session States Missing** - 'working' and 'blocked' not in RUNTIME_STATES
3. **Status Sync Broken** - Session adapters don't call Worker methods
4. **Budget/Spawn No Rollback** - Budget deducted before spawn, no transaction wrapping

### High Priority (Inconsistencies)

5. **Org Resume Inconsistent** - T4 behaves differently than T2
6. **Session Ready Not Called** - session_ready() exists but never triggered automatically
7. **Org Stop No Verification** - Can transition to 'stopped' with active sessions

### Medium Priority (Missing Features)

8. **Onboarding No Checkpointing** - Must restart from Phase 1 on failure
9. **Worker Suspend/Unsuspend Missing** - Documented transitions not implemented
10. **Session Working/Blocked Missing** - Task assignment states not implemented

### Documentation Issues

11. **fail_onboarding() Not Documented** - Extra transition: onboarding → terminated
12. **Session Health Check Missing** - Org start doesn't verify CEO session ready

---

## Recommendations

### Immediate Actions

1. **Resolve State Machine Spec Conflict:**
   - Decision: Keep 'offboarding' or replace with 'suspended'?
   - Update either STATEMACHINES.md or shared/state_machines.py to match
   - Implement missing transitions based on decision

2. **Implement Session State Propagation:**
   - Add callbacks in `cli/core/sessions/claude_code.py`
   - Add callbacks in `cli/core/sessions/gemini.py`
   - Test: Session state changes appear in database < 500ms

3. **Add Transaction Wrapping:**
   - `Worker.spawn_session()`: Wrap budget + spawn in transaction
   - Rollback budget if spawn fails
   - Test: Spawn failure refunds budget

4. **Fix Org Resume Inconsistency:**
   - Make T4 (stopped → running) spawn CEO session like T2
   - Or: Document why T4 is different (design decision)

### Follow-Up Tasks

5. **Add working/blocked States:**
   - Add to RUNTIME_STATES
   - Add transitions to RUNTIME_TRANSITIONS
   - Implement Worker methods for task assignment tracking

6. **Add Onboarding Checkpointing:**
   - Add onboarding_checkpoint column to worker_state
   - Write checkpoint after each phase
   - Resume from last checkpoint on retry

7. **Add UI Auto-Refresh:**
   - `terminal-app/views/team.py` - Add set_interval(2.0)
   - Test: UI shows status changes < 2.5s

---

## Files Requiring Changes

### State Machine Definitions
- `shared/state_machines.py` - Fix LIFECYCLE_STATES mismatch

### Core Implementation
- `cli/core/org.py` - Add rollback, fix resume
- `cli/core/worker.py` - Add transaction wrapping, implement suspend/unsuspend
- `cli/core/sessions/claude_code.py` - Add state change callbacks
- `cli/core/sessions/gemini.py` - Add state change callbacks
- `cli/core/onboarding.py` - Add checkpointing

### UI
- `terminal-app/src/board_ui/views/team.py` - Add auto-refresh
- `terminal-app/src/board_ui/views/dashboard.py` - Add auto-refresh

### Tests
- Create validation tests for all state machines
- Test status sync latency (< 500ms)
- Test UI refresh latency (< 2.5s)
- Test rollback on failures

---

**Validation Complete:** 2026-01-25
**Next Steps:** Create issues for each violation, prioritize by severity
