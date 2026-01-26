# Org Stop Sequence Audit - 2026-01-25

**Task:** quinnai-65k7
**Auditor:** Claude (automated)
**Scope:** Document current 'org stop' behavior and identify gaps

---

## Command Entry Point

**File:** `cli/commands/org/stop.py`
**Function:** `stop_cmd()`

**Arguments:**
- `--cleanup/--no-cleanup` (default: True) - Run notification cleanup on stop
- `--worker <name|id>` - Stop workday for specific worker (org must be running)
- `--force` - Force kill sessions without waiting for graceful shutdown

---

## Execution Flow

### 1. **Pre-flight Checks** (stop.py:44-51)

```
✓ Check if quinn.db exists at org_path/live/quinn.db
✓ Open database connection
```

**Potential Issues:**
- No validation that org is in a stoppable state before proceeding
- Database open happens before all checks

### 2. **Worker-Specific Stop** (stop.py:58-111)

If `--worker` flag provided:

```
✓ Check org status == RUNNING (fail if not)
✓ Get worker by name or ID
✓ Create wrap-up notification:
  - Get/create 'general' channel
  - Create message requesting wrap-up
  - Create notification bead for worker (P2)
  - Message content: "Workday ending, wrap up and save to shared/"
✓ Terminate worker session:
  - worker_obj.terminate_session(force=force)
✓ Echo confirmation to user
```

**Wrap-up Message Details** (lines 82-106):
- Sender: Worker's manager OR CEO (if no manager) OR worker itself
- Priority: 2 (normal)
- Time sensitivity: "hours"
- Creates notification bead for the worker

**Potential Issues:**
- Wrap-up request is sent, but command doesn't wait for acknowledgment
- Worker session terminates immediately after notification created
- Worker may not have time to see/act on wrap-up message
- No verification that worker actually wrapped up before stopping session
- DESIGN ISSUE: Per user requirements, should "wait for wrap-up acknowledgement"

### 3. **Org-Wide Stop - Already Stopped Check** (stop.py:113-115)

```
if org.status == OrgStatus.STOPPED.value:
    click.echo("Organization is already stopped.")
    return
```

**Potential Issues:**
- Doesn't check if there are zombie sessions still running
- Returns without cleanup even if --cleanup is True

### 4. **Org-Wide Stop - State Validation** (stop.py:117-122)

```
if org.status != OrgStatus.RUNNING.value:
    raise click.ClickException(
        f"Cannot stop organization in '{org.status}' state.\n"
        "Organization must be 'running' to stop.\n"
        "Check current status with 'qn org status'."
    )
```

**Potential Issues:**
- Good error message
- Prevents stopping from INITIALIZED or other invalid states

### 5. **Stop All Worker Sessions** (stop.py:124-134)

```
✓ Call stop_all_sessions(db, force=force)
  - Returns SessionStopResult
  - Reports sessions_found, sessions_stopped, tmux_sessions_killed, errors
✓ Display results to user:
  - "Stopped {stopped}/{found} sessions"
  - "Tmux sessions killed: {killed}" (if any)
  - Warnings for each error
```

**stop_all_sessions() Implementation** (cli/core/sessions.py):

*Need to check this file to understand the implementation*

**Potential Issues:**
- No indication of which sessions failed to stop
- Continues with org stop even if some sessions failed
- Errors shown as warnings, not failures

### 6. **Org State Transition** (stop.py:137-143)

```
✓ Call org.stop()
  - Validates state transition
  - Updates org_status to STOPPED
  - Logs state change
✓ Catch InvalidOrgTransition with helpful error
```

**Org.stop() Implementation** (org.py:351-364):

```python
def stop(self) -> None:
    """Stop the org (pause operations).

    Transitions org to stopped state. Worker sessions should be
    stopped separately before calling this.
    """
    old_status = self.status
    self._validate_transition(OrgStatus.STOPPED.value)
    update_org_status(self.db, OrgStatus.STOPPED.value, self.ceo_worker_id)
    self._state_data = None  # Invalidate cache
    log_org_state_change(_logger, old_status, OrgStatus.STOPPED.value)
```

**Potential Issues:**
- Very simple - just updates status
- Docstring says "Worker sessions should be stopped separately before calling this"
- No validation that sessions are actually stopped
- No cleanup of worker state
- No state persistence beyond status update

### 7. **Notification Cleanup** (stop.py:148-152)

If `cleanup` is True (default):

```
✓ Call run_notification_cleanup(db, DEFAULT_NOTIFICATION_RETENTION_DAYS)
  - Returns dict with purge counts
✓ Display result if any purged:
  - "Cleanup: purged {total_purged} old notifications"
```

**Potential Issues:**
- Cleanup happens AFTER org stop
- If cleanup fails, org is already stopped (no rollback)
- No indication of what retention period is being used

---

## State After Successful Stop

- Org status: STOPPED
- Worker sessions: stopped (via stop_all_sessions)
- Worker lifecycles: unchanged (still active)
- Worker runtime states: stopped
- Notifications: old ones purged (if cleanup=True)
- Database: connection closed

**What is NOT cleaned up:**
- Worker directories (storage/workers/*)
- Worker state records in database
- Session records in database
- Beads/work items
- Channels and messages
- Budget allocations

---

## Critical Gaps Identified

### 1. **No Wait for Wrap-up Acknowledgment**
- Per user requirements: "Workday stop should wait for wrap-up acknowledgement"
- Current implementation: Sends notification, immediately terminates session
- Worker doesn't get chance to acknowledge or complete wrap-up
- **Impact:** BLOCKING - Violates design requirement

### 2. **No Session Stop Verification**
- stop_all_sessions() may fail to stop some sessions
- org.stop() proceeds anyway, updating status to STOPPED
- Zombie sessions may keep running
- **Impact:** HIGH - Inconsistent state, resource leaks

### 3. **No State Persistence**
- org.stop() only updates status, nothing else
- No worker state saved for resume
- No cleanup of runtime state
- **Impact:** HIGH - Resume may fail or be inconsistent

### 4. **No Cleanup Beyond Notifications**
- Old session records left in database
- Worker runtime states not reset
- No indication which workers had active sessions
- **Impact:** MEDIUM - Database bloat, stale data

### 5. **Graceful vs Force Behavior Unclear**
- `--force` flag passed to stop_all_sessions()
- No indication to user what "force" actually does
- No timeout for graceful shutdown
- **Impact:** MEDIUM - User doesn't know what to expect

### 6. **Error Handling**
- Session stop errors shown as warnings, not failures
- Org stop succeeds even if sessions failed to stop
- No rollback if org.stop() fails after sessions stopped
- **Impact:** MEDIUM - Silent partial failures

---

## Recommendations

### P0 - Critical Fixes
1. **Wait for Wrap-up:** Implement wrap-up acknowledgment workflow
   - Send wrap-up request
   - Wait for worker to acknowledge (or timeout)
   - Only then terminate session

2. **Verify Session Stop:** Check all sessions stopped before updating org status
   - If any fail, report error and keep org RUNNING
   - Provide `--force-org-stop` flag to proceed anyway

3. **State Persistence:** Save worker states for resume
   - Persist current task IDs
   - Save runtime metadata
   - Mark sessions as "cleanly stopped" vs "killed"

### P1 - Important Improvements
4. **Graceful Shutdown Timeout:** Add configurable timeout for graceful stop
   - Default 30 seconds for workers to wrap up
   - Show progress indicator
   - Auto-force-kill after timeout

5. **Better Error Reporting:** Show which sessions failed and why
   - List failed sessions by worker ID/name
   - Provide remediation steps
   - Offer `qn org force-stop` command for stuck cases

6. **Session Cleanup:** Clean up database session records on stop
   - Mark stopped sessions with stop reason
   - Optionally archive or delete old session records
   - Reset worker runtime states

### P2 - Nice to Have
7. **Pre-stop Validation:** Check what will be stopped before proceeding
   - List active sessions
   - Warn about work in progress
   - Require confirmation if critical work active

8. **Shutdown Hooks:** Allow workers to register shutdown handlers
   - Save work in progress
   - Commit partial results
   - Send escalations for incomplete work

9. **Status Preservation:** Track stop reason and metadata
   - User-initiated vs automated
   - Graceful vs forced
   - Timestamp and triggering user

---

## Files Involved

**Core:**
- cli/commands/org/stop.py (main command)
- cli/core/org.py (Org.stop() state machine)
- cli/core/sessions.py (stop_all_sessions())
- cli/core/worker.py (Worker.terminate_session())

**Supporting:**
- cli/core/db.py (database operations)
- cli/core/queries.py (get_worker_by_name, create_message, etc.)
- cli/core/notifications.py (run_notification_cleanup, create_notification_bead)
- shared/enums.py (OrgStatus enum)
- shared/__init__.py (ORG_TRANSITIONS, InvalidOrgTransition)

---

## Missing Implementation Details

Need to investigate:
- [ ] cli/core/sessions.py::stop_all_sessions() - How does it actually stop sessions?
- [ ] cli/core/worker.py::Worker.terminate_session() - What cleanup happens?
- [ ] Session stop verification - Is there any feedback mechanism?
- [ ] Worker wrap-up protocol - How should acknowledgment work?

---

## Test Coverage Gaps

Need integration tests for:
- [ ] Stop from RUNNING (happy path)
- [ ] Stop when already STOPPED (idempotent)
- [ ] Stop with active worker sessions
- [ ] Stop with zombie/crashed sessions
- [ ] Stop with --force flag
- [ ] Worker-specific stop with wrap-up
- [ ] Stop with notification cleanup
- [ ] Stop with notification cleanup disabled
- [ ] Stop when sessions fail to terminate
- [ ] Resume after stop (verify state preserved)

---

## Comparison with Start Sequence

**Similarities:**
- Both have worker-specific and org-wide modes
- Both validate state transitions
- Both use simple state machine (Org.start()/Org.stop())
- Both have cleanup operations (start: validation, stop: notifications)

**Differences:**
- Start spawns new resources (sessions), Stop terminates them
- Start has more complex initialization (CEO activation, briefing)
- Stop has less state management (no persistence of runtime state)
- Start waits for nothing, Stop should wait for wrap-up (not implemented)

**Asymmetry Issues:**
- Start creates sessions, but Stop doesn't fully clean them up
- Start prepares worker dirs, but Stop doesn't remove them
- Start initializes state, but Stop doesn't persist it
- Resume (start after stop) may encounter stale state from previous run
