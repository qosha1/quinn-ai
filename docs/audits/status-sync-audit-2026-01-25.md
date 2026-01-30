# Worker Status Syncing Audit - 2026-01-25

**Task:** quinnai-fsfl
**Auditor:** Claude (automated)
**Scope:** Document current worker status tracking and identify sync failures

---

## Executive Summary

Identified the full status tracking pipeline from worker sessions to terminal UI. The system relies on **database polling** with potential race conditions and stale data issues. No real-time update mechanism exists.

### Root Cause Hypothesis
**qn board ui UI does not properly update worker status because:**
1. No push-based updates (polling only)
2. Worker sessions may not call status update functions
3. Caching in Worker class may serve stale data
4. Terminal app refresh rate may be too slow

---

## Status Data Sources

### 1. Database Table: `worker_state`

**Schema (relevant columns):**
```sql
worker_id TEXT PRIMARY KEY
runtime_status TEXT  -- starting, running, idle, working, blocked, stopped
current_task_id TEXT
pid INTEGER
last_activity TIMESTAMP
updated_at TIMESTAMP
tasks_completed INTEGER
tasks_failed INTEGER
```

**Authoritative source of runtime status for UI**

### 2. Worker Class Property (cli/core/worker.py:600-604)

```python
@property
def runtime_status(self) -> Optional[str]:
    """Get current runtime status, or None if no session."""
    if self._state_data is None:
        self._load_state()
    return self._state_data.runtime_status if self._state_data else None
```

**Issue:** Lazy loading with caching
- `_state_data` is cached after first load
- Only reloaded if explicitly set to `None`
- Stale data may be returned if database updated externally

### 3. Sessions Table (cli/core/sessions.py)

**Separate tracking for session lifecycle:**
- States: `starting`, `running`, `idle`, `stopped`, `error`, `crashed`
- NOT the same as `worker_state.runtime_status`
- No automatic sync between tables

---

## Status Update Flow

### Writers (Who Updates Status)

#### 1. Worker Methods (cli/core/worker.py)

**start_session()** (line 1000-1030):
```python
def start_session(self, pid: Optional[int] = None) -> None:
    self._validate_runtime_transition("starting")
    update_worker_runtime_status(self.db, self.id, "starting")
    # Updates PID if provided
    self._state_data = None  # Invalidate cache
```

**session_ready()** (line 1032-1036):
```python
def session_ready(self) -> None:
    self._validate_runtime_transition("running")
    update_worker_runtime_status(self.db, self.id, "running")
    self._state_data = None
```

**begin_work()**, **finish_work()**, **stop_session()**, **crash_session()** - Similar pattern

**ISSUE:** These methods are only called if Worker instance methods are invoked
- Session adapters may not call these
- Workers inside sessions don't have direct access to Worker instance
- Status may not update if session changes state independently

#### 2. Queries Module (cli/core/queries.py:677-682)

**update_worker_runtime_status()**:
```python
def update_worker_runtime_status(
    db: Database,
    worker_id: str,
    runtime_status: str,
    current_task_id: Optional[str] = None,
) -> None:
    now = datetime.now()
    db.execute(
        """UPDATE worker_state SET runtime_status = ?, current_task_id = ?,
           last_activity = ?, updated_at = ? WHERE worker_id = ?""",
        (runtime_status, current_task_id, now, now, worker_id)
    )
    db.connection.commit()
```

**Direct database update** - No validation, no state machine checks

**ISSUE:** Multiple code paths can update status
- Worker class methods
- Direct calls to update_worker_runtime_status
- Potential race conditions
- No single source of truth

### Readers (Who Reads Status)

#### 1. Terminal App (terminal-app/src/board_ui/services/org_connection.py)

**get_workers()** (lines 599-611):
```python
# Read from worker_state table
state_rows = self._db.fetchall(
    """SELECT worker_id, current_task_id, runtime_status
       FROM worker_state"""
)

for row in state_rows:
    worker_id = row["worker_id"]
    if worker_id not in result:
        result[worker_id] = {"state": row["runtime_status"]}
    result[worker_id]["current_task_id"] = row["current_task_id"]
```

**Direct database read** - No caching, fresh data each time

**ISSUE:** Called manually via `refresh_workers()`
- No automatic refresh
- No push notifications
- User must manually trigger refresh

#### 2. Team View (terminal-app/src/board_ui/views/team.py)

**refresh_workers()** (lines 76-94):
```python
async def refresh_workers(self) -> None:
    conn = self.app.org_connection
    workers = conn.get_workers()  # Database query
    self._populate_workers(workers)
```

**Called on mount** - Then only when explicitly triggered

**ISSUE:** No periodic refresh timer
- UI shows stale data until user navigates away and back
- No indication data is stale

---

## Status Propagation Paths

### Path 1: Worker Session → Database (BROKEN)

```
Worker Session State Change
    ↓ (MISSING: Callback or bridge)
Worker.method_call()  ← Who calls this?
    ↓
update_worker_runtime_status()
    ↓
Database UPDATE
```

**Problem:** Sessions don't automatically call Worker methods
- Session adapters (claude_code, gemini) manage their own state
- No bridge between session state and worker state
- Worker methods like session_ready() must be called externally

### Path 2: Database → Terminal UI (POLLING ONLY)

```
Database (worker_state table)
    ↓ (POLL: user navigation or manual refresh)
OrgConnection.get_workers()
    ↓
TeamView.refresh_workers()
    ↓
UI Update
```

**Problem:** Purely pull-based
- No push notifications
- No periodic polling
- Stale data until user action

### Path 3: Session Callbacks (INCOMPLETE)

**Session adapters support callbacks:**
```python
# cli/core/sessions/claude_code.py (line ~200)
def _on_state_change(self, old_state, new_state):
    # Callback when session state changes
    # BUT: Doesn't update worker_state table!
```

**Problem:** Callbacks exist but don't propagate to database
- Session state changes are internal
- No integration with Worker class
- worker_state table not updated automatically

---

## Critical Gaps Identified

### 1. **No Automatic Status Propagation** (BLOCKING)
- Session state changes don't update worker_state table
- Worker methods must be called manually
- No bridge/callback mechanism
- **Impact:** Status gets stale immediately after session changes

### 2. **No Push-Based Updates to UI** (BLOCKING)
- Terminal app has no notification system
- No periodic refresh timer
- UI only updates on manual refresh
- **Impact:** Users see outdated status indefinitely

### 3. **Cache Invalidation Issues** (HIGH)
- Worker._state_data cached after first load
- Only invalidated when explicitly set to None
- Multiple Worker instances may have different cached states
- **Impact:** Even programmatic access may get stale data

### 4. **Race Conditions** (HIGH)
- Multiple code paths update worker_state
- No locking or transaction isolation
- Concurrent updates may clobber each other
- **Impact:** Status updates may be lost

### 5. **No Status Consistency Validation** (MEDIUM)
- worker_state.runtime_status independent from sessions table
- No validation that they match
- Conflicting states possible (worker says "running", session says "crashed")
- **Impact:** Inconsistent data across system

### 6. **No Heartbeat Mechanism** (MEDIUM)
- record_worker_heartbeat() exists but may not be called
- Crashed workers may appear "running" forever
- No automatic detection of stale status
- **Impact:** Ghost workers in UI

---

## Recommendations

### P0 - Critical Fixes

#### 1. **Session State Callbacks → Database**
Implement automatic status sync on session state changes:

```python
# In session adapters
def _on_state_change(self, old_state, new_state):
    # Map session state to worker runtime_status
    runtime_status = self._map_session_to_runtime_state(new_state)

    # Update database directly
    update_worker_runtime_status(
        self._db,
        self._worker_id,
        runtime_status
    )
```

**Files to modify:**
- cli/core/sessions/claude_code.py
- cli/core/sessions/gemini.py
- cli/core/sessions/__init__.py (base session class)

#### 2. **Terminal App Auto-Refresh**
Add periodic polling to terminal app:

```python
# In TeamView
async def on_mount(self) -> None:
    await self.refresh_workers()

    # Set up periodic refresh (every 2 seconds)
    self.set_interval(2.0, self.refresh_workers)
```

**Files to modify:**
- terminal-app/src/board_ui/views/team.py
- terminal-app/src/board_ui/views/dashboard.py (CEO status)
- terminal-app/src/board_ui/app.py (global refresh timer)

#### 3. **Worker State Cache Invalidation**
Ensure Worker instances reload state from DB:

```python
@property
def runtime_status(self) -> Optional[str]:
    # ALWAYS reload from DB for runtime status
    # Don't trust cache for frequently-changing data
    self._load_state()  # Force reload
    return self._state_data.runtime_status if self._state_data else None
```

**Files to modify:**
- cli/core/worker.py (runtime_status property)
- Consider separate caching strategy for static vs dynamic data

### P1 - Important Improvements

#### 4. **Status Model Unification**
Create single source of truth for status:

```python
class WorkerStatus(Enum):
    # Lifecycle states
    PENDING = "pending"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"

    # Runtime states (only when active)
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    STOPPED = "stopped"
    CRASHED = "crashed"
```

**Validation:**
- Runtime states only valid when lifecycle == ACTIVE
- State transitions follow state machine
- Single update function enforces rules

#### 5. **Heartbeat System**
Implement automatic heartbeat from sessions:

```python
# In session adapters
async def _heartbeat_loop(self):
    while self._running:
        record_worker_heartbeat(self._db, self._worker_id)
        await asyncio.sleep(30)  # Every 30 seconds
```

**Stale detection:**
- If last_activity > 60 seconds and status == "running"
- Auto-transition to "crashed" or "stale"

#### 6. **Transaction-Based Updates**
Wrap multi-table updates in transactions:

```python
def update_worker_and_session_state(db, worker_id, runtime_status, session_state):
    with db.transaction():
        update_worker_runtime_status(db, worker_id, runtime_status)
        update_session_state(db, session_id, session_state)
        # Atomic - both succeed or both fail
```

### P2 - Nice to Have

#### 7. **Real-Time Push via WebSockets**
Replace polling with push notifications:
- Database trigger → Message queue → WebSocket → UI
- Instant updates without polling overhead
- Requires infrastructure changes

#### 8. **Status History Tracking**
Track status transitions for debugging:
```sql
CREATE TABLE worker_state_history (
    id TEXT PRIMARY KEY,
    worker_id TEXT,
    old_status TEXT,
    new_status TEXT,
    timestamp TIMESTAMP,
    source TEXT  -- 'worker', 'session', 'system'
)
```

---

## Test Scenarios

Need integration tests for:
- [ ] Session state change triggers database update
- [ ] Terminal app receives status update within 2 seconds
- [ ] Multiple concurrent status updates don't cause race
- [ ] Worker instance cache invalidation works correctly
- [ ] Crashed session auto-detects and updates status
- [ ] Heartbeat mechanism marks stale workers
- [ ] Status remains consistent across worker_state and sessions tables

---

## Files Involved

**Status Writers:**
- cli/core/worker.py (Worker methods)
- cli/core/queries.py (update_worker_runtime_status)
- cli/core/sessions/claude_code.py (session callbacks)
- cli/core/sessions/gemini.py (session callbacks)
- cli/core/sessions/persistence.py (session state updates)

**Status Readers:**
- terminal-app/src/board_ui/services/org_connection.py (get_workers)
- terminal-app/src/board_ui/views/team.py (TeamView.refresh_workers)
- terminal-app/src/board_ui/views/dashboard.py (CEO status display)
- cli/commands/org/status.py (CLI status command)

**Supporting:**
- shared/enums.py (status enums)
- cli/core/db.py (database connection)
- shared/pyterm/worker_bridge.py (potential bridge mechanism)

---

## Next Steps

1. Implement session state callbacks → database updates (P0.1)
2. Add terminal app auto-refresh timer (P0.2)
3. Fix Worker cache invalidation (P0.3)
4. Write integration tests for status sync
5. Design unified status model (P1.4)
6. Implement heartbeat system (P1.5)
