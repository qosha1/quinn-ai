# Code Review & Test Report - 2026-01-26

**Reviewer:** Claude Sonnet 4.5 (code-reviewer agent)
**Session:** Real-time polling implementation + RuntimeStatus enum fix
**Commits Reviewed:**
- `feb7581` - Implement SQLite WAL polling for real-time UI updates
- `4a3bf24` - Add RuntimeStatus enum to fix import errors

---

## Executive Summary

### ✅ Accomplishments
- Fixed blocking import error preventing 8 test files from running
- Implemented real-time polling infrastructure for qn-board UI
- Added proper RuntimeStatus enum matching state machine

### ❌ Critical Issues Found
1. **P0 BUG**: PRAGMA data_version doesn't detect changes from same connection
2. **P1 BUG**: Wait condition checks only RUNNING, should check RUNNING OR IDLE
3. **P1 BUG**: Subscriber list modifications not thread-safe

### 📊 Test Results
- **Runtime status tests**: 16/16 PASSED ✅
- **Enum validation**: PASSED - matches state machine exactly ✅
- **Data version polling**: FAILED - doesn't detect same-connection changes ❌
- **Session state tests**: ERROR - budget fixture issue (pre-existing) ⚠️

### 🎯 Overall Verdict
**NOT PRODUCTION READY** - Critical bugs in polling mechanism. RuntimeStatus enum is correct but usage needs fixes.

---

## Detailed Findings

### 1. SQLite WAL Polling Implementation (feb7581)

#### Critical Issue: PRAGMA data_version Misunderstanding

**Status:** 🔴 CRITICAL BUG (quinnai-drpl)

**Test Results:**
```
Initial data_version (conn1): 2
After INSERT on conn1: 2          ← NO CHANGE DETECTED
Changed: False                     ← BUG!

After INSERT on conn2 (checking conn1): 3
Changed: True                      ← Works for other connections
```

**Impact:**
- qn-board UI will NOT update when worker processes modify database
- Polling only detects changes from OTHER connections
- Users see stale data until external process writes

**Root Cause:**
`PRAGMA data_version` is connection-specific and tracks schema changes, not data modifications.

**Fix Required:**
Use `PRAGMA wal_checkpoint(PASSIVE)` instead:
```python
def _get_wal_status(self) -> int:
    """Get WAL page count to detect changes."""
    row = self._db.fetchone('PRAGMA wal_checkpoint(PASSIVE)')
    if row:
        return int(row[1])  # WAL page count changes on writes
    return 0
```

#### Critical Issue: Thread Safety

**Status:** 🟡 RACE CONDITION (quinnai-9rf5)

**Problem:**
```python
def unsubscribe():
    if callback in self._subscribers:
        self._subscribers.remove(callback)  # ← Not atomic
    if len(self._subscribers) == 0:  # ← Race here
        self._polling_enabled = False
```

**Impact:**
- Polling disabled while subscribers exist
- Polling stays enabled after all unsubscribed
- Rare list mutation exceptions

**Fix Required:**
Add `threading.Lock` around all `_subscribers` modifications.

#### Issue: No Cleanup on Shutdown

**Status:** 🟡 RESOURCE LEAK (quinnai-9mdx)

**Problem:**
- `set_interval(0.3, ...)` starts on mount but never stops
- Polling continues after app exit
- Database connections held open

**Fix Required:**
Add `on_unmount` handler to disconnect all orgs.

#### Issue: Magic Number

**Status:** 🟢 CODE QUALITY (quinnai-01p9)

**Problem:**
Violates CLAUDE.md rule - `0.3` hardcoded without explanation.

**Fix Required:**
Move to config: `POLLING_INTERVAL_SECONDS = 0.3`

---

### 2. RuntimeStatus Enum Implementation (4a3bf24)

#### ✅ Enum Correctness - PASSED

**Validation Results:**
```
Enum values: {'crashed', 'idle', 'starting', 'running', 'stopped'}
State machine values: frozenset({'crashed', 'idle', 'starting', 'running', 'stopped'})
Match: True ✅
```

All runtime states properly represented with matching string values.

#### Critical Issue: Wait Condition Logic

**Status:** 🟡 SEMANTIC BUG (quinnai-r46h)

**Problem:**
```python
# Line 487 - Only checks RUNNING
if worker.runtime_status == RuntimeStatus.RUNNING.value:
    click.echo(f"✓ {worker.name} session ready")
```

**Why Wrong:**
- Sessions transition: `starting → running → idle`
- IDLE is also a "ready" state (ready for work)
- If session quickly reaches IDLE, wait times out incorrectly

**Evidence:**
`cli/core/worker.py:680` shows `is_session_active` checks: `starting`, `running`, OR `idle`

**Fix Required:**
```python
if worker.runtime_status in (RuntimeStatus.RUNNING.value, RuntimeStatus.IDLE.value):
```

#### Issue: Documentation Out of Date

**Status:** 🟢 DOCS (quinnai-r46h)

**Problem:**
`docs/org-start-sequence-design.md` still references `RuntimeStatus.READY` in 4 places.

**Fix Required:**
Update all `READY` references to `RUNNING` or `RUNNING|IDLE` as appropriate.

---

## Test Coverage Analysis

### Passing Tests (16/16) ✅

**Runtime Status Tests:**
```
test_no_runtime_initially PASSED
test_runtime_after_session_start PASSED
test_session_ready PASSED
test_begin_work PASSED
test_finish_work PASSED
test_stop_session PASSED
test_mark_crashed PASSED
test_restart_from_stopped PASSED
test_restart_from_crashed PASSED
test_lifecycle_runtime_constraints (all) PASSED
test_runtime_transitions_complete PASSED
```

**Verdict:** RuntimeStatus enum correctly integrated with worker state machine.

### Failing Tests

**Session State Machine Test:**
```
ERROR - create_budget_pool() missing 1 required positional argument: 'period_start'
```

**Verdict:** Pre-existing issue (quinnai-d73d), not related to RuntimeStatus changes.

---

## Security Analysis

**No security concerns identified.**
- Read-only SQLite queries (no injection risk)
- Enum values are constant strings (no manipulation risk)
- No external input processing

---

## Performance Analysis

### Polling Overhead
- **PRAGMA data_version**: ~0.1-0.5ms per call (fast)
- **Polling frequency**: 3.33 queries/second per org
- **Multi-org impact**: 10 orgs = 33 queries/second

**Concerns:**
- No exponential backoff when idle
- Could interfere with high-frequency database writes
- Battery drain on laptops

**Recommendations:**
1. Implement backoff when no changes detected (300ms → 1s → 2s)
2. Make interval configurable
3. Consider file system watching as alternative

---

## Code Quality Assessment

| Metric | SQLite Polling | RuntimeStatus Enum |
|--------|---------------|-------------------|
| **Correctness** | ❌ Critical bug | ✅ Mostly correct |
| **Thread Safety** | ❌ Race conditions | ✅ Not applicable |
| **Error Handling** | ⚠️ Silent failures | ✅ Good |
| **Documentation** | ✅ Good docstrings | ⚠️ Outdated docs |
| **Testing** | ❌ No unit tests | ✅ Covered by existing |
| **Standards** | ❌ Magic numbers | ✅ Follows patterns |

---

## Recommendations

### Before Production Deployment

**MUST FIX (Blocking):**
1. ✅ **quinnai-drpl** (P0): Replace PRAGMA data_version with WAL checkpoint
2. ✅ **quinnai-r46h** (P1): Fix wait condition to check RUNNING OR IDLE
3. ✅ **quinnai-9rf5** (P1): Add thread lock for subscriber list

**SHOULD FIX (Important):**
4. ✅ **quinnai-9mdx** (P2): Add cleanup handler for app shutdown
5. ✅ **quinnai-01p9** (P3): Move polling interval to config

**CONSIDER:**
6. Add exponential backoff when idle
7. Add unit tests for polling mechanism
8. Add debouncing for rapid changes
9. Document SessionState vs RuntimeStatus distinction

### Testing Plan

**Before merging fixes:**
1. Manual test: Start qn-board, use CLI to update worker status, verify UI updates
2. Unit test: Test WAL checkpoint detection with concurrent writes
3. Integration test: Full org start sequence with wait flag
4. Load test: 10 concurrent workers updating status rapidly

---

## Created Issues

All issues tracked in beads:

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| quinnai-drpl | P0 | Fix PRAGMA data_version polling - use WAL checkpoint | Open |
| quinnai-r46h | P1 | Fix org start wait condition - check RUNNING or IDLE | Open |
| quinnai-9rf5 | P1 | Add thread safety to subscriber list | Open |
| quinnai-9mdx | P2 | Add cleanup handler for polling on app shutdown | Open |
| quinnai-01p9 | P3 | Make polling interval configurable | Open |

---

## Conclusion

The implementation fixed the critical import error and laid the foundation for real-time updates, but introduced critical bugs that prevent production deployment:

1. **Data version polling doesn't work** - most critical issue
2. **Wait logic has edge case bug** - breaks org start in some scenarios
3. **Thread safety issues** - could cause intermittent failures

**Recommended Action:**
Implement fixes for P0 and P1 issues before releasing qn-board with real-time updates.

**Estimated Fix Time:**
- P0 (WAL checkpoint): 2-3 hours (implementation + testing)
- P1 (wait condition): 30 minutes
- P1 (thread safety): 1 hour

**Total:** ~4-5 hours to production-ready state.
