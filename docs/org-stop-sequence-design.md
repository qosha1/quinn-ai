# Org Stop Sequence Design

**Task:** quinnai-hcks
**Author:** Claude (design review)
**Date:** 2026-01-26
**Status:** Proposed

---

## Overview

This document defines the complete and reliable `qn org stop` sequence that addresses all gaps identified in the org-stop-audit-2026-01-25.md.

**Design Goals:**
1. **Graceful shutdown** - Workers get time to wrap up and save work
2. **State preservation** - Worker state persists for clean resume
3. **Reliability** - Verify sessions actually stopped
4. **Idempotency** - Safe to run multiple times
5. **Clear feedback** - User knows what's happening at each step

---

## State Machine

### Org States

```
INITIALIZED → RUNNING → STOPPED
                ↑          ↓
                └──────────┘
```

**Valid Transitions:**
- `RUNNING → STOPPED` - Normal stop (saves state for resume)
- `STOPPED → STOPPED` - Idempotent (no-op)

**Invalid:**
- Cannot stop from INITIALIZED (nothing to stop)

### Worker Lifecycle States

```
active → (session running) → (session stopped) → active
  ↓
offboarding → terminated
```

**During Stop:**
- Worker lifecycle remains `active` (org stop doesn't fire workers)
- Worker session transitions: `running → stopping → stopped`
- Runtime status: `ready/working → wrapping_up → stopped`

---

## Sequence Design

### Phase 1: Pre-Stop Validation

**Purpose:** Validate org can be stopped safely

**Steps:**

1. **Validate org exists and is stoppable**
   ```python
   db_path = get_org_db_path(org_path)
   if not db_path.exists():
       raise OrgNotFoundError(org_path)

   org = Org.load(db)
   if org.status == OrgStatus.STOPPED:
       if force:
           # Check for zombie sessions and clean up
           _cleanup_zombie_sessions(db)
       click.echo("Organization is already stopped.")
       return

   if org.status != OrgStatus.RUNNING:
       raise InvalidOrgTransition(
           f"Cannot stop from '{org.status}' state. "
           "Organization must be 'running' to stop."
       )
   ```

2. **Enumerate active sessions**
   ```python
   active_sessions = get_active_sessions(db)
   if not active_sessions and not force:
       click.echo("No active sessions to stop.")
       # Continue to update org status anyway
   ```

3. **Warn about work in progress** (optional, P2)
   ```python
   if active_sessions and not force and not yes:
       click.echo(f"Found {len(active_sessions)} active worker sessions:")
       for session in active_sessions:
           worker = Worker.get(db, session.worker_id)
           click.echo(f"  - {worker.name} ({worker.runtime_status})")

       if not click.confirm("Stop all workers and terminate sessions?"):
           click.echo("Cancelled.")
           return
   ```

**Exit Criteria:**
- Org is in RUNNING state → Continue
- Org is in STOPPED state + no zombie sessions → Exit with success
- Org is in other state → Fail with error

---

### Phase 2: Worker Wrap-Up (Graceful Shutdown)

**Purpose:** Give workers time to save work and clean up

**P0 Requirement:** "Workday stop should wait for wrap-up acknowledgement"

**Steps:**

1. **Send wrap-up notifications**
   ```python
   for session in active_sessions:
       worker = Worker.get(db, session.worker_id)
       _send_wrap_up_notification(db, org_path, worker, timeout=graceful_timeout)
   ```

2. **Wait for acknowledgments** (with timeout)
   ```python
   timeout = graceful_timeout or 30  # seconds
   start_time = time.time()

   pending_workers = set(s.worker_id for s in active_sessions)
   acknowledged_workers = set()

   while time.time() - start_time < timeout and pending_workers:
       # Poll for wrap-up acknowledgments
       for worker_id in list(pending_workers):
           if _check_wrap_up_acknowledgment(db, worker_id):
               acknowledged_workers.add(worker_id)
               pending_workers.remove(worker_id)
               click.echo(f"  ✓ {Worker.get(db, worker_id).name} wrapped up")

       if pending_workers:
           time.sleep(1)  # Poll every second

   # Show progress
   total = len(active_sessions)
   acked = len(acknowledged_workers)
   click.echo(f"Workers wrapped up: {acked}/{total}")
   ```

3. **Handle timeout**
   ```python
   if pending_workers and not force:
       click.echo(f"Warning: {len(pending_workers)} workers did not acknowledge wrap-up:")
       for worker_id in pending_workers:
           worker = Worker.get(db, worker_id)
           click.echo(f"  - {worker.name}")

       if not click.confirm("Force terminate unresponsive workers?"):
           raise StopTimeout(f"Workers did not wrap up within {timeout}s")

       force = True  # Continue with forced termination
   ```

**Wrap-Up Notification:**

Message sent to each worker:
```
Subject: Workday ending - wrap up your work
Priority: P1 (high)
Time Sensitivity: minutes

Please wrap up your current work:
1. Save any work in progress to shared/
2. Document incomplete work in beads
3. Commit any changes
4. Reply to this message when done

Timeout: {timeout} seconds
After timeout, your session will be force-terminated.
```

**Acknowledgment Protocol:**

Worker acknowledges by:
1. Creating a reply message in the channel
2. OR updating their runtime status to "wrapping_up"
3. OR creating a "wrap-up complete" bead

System checks all three mechanisms during polling.

---

### Phase 3: Session Termination

**Purpose:** Stop all worker sessions cleanly

**Steps:**

1. **Graceful termination first** (if not forced)
   ```python
   graceful_results = []
   for session in active_sessions:
       worker = Worker.get(db, session.worker_id)
       try:
           result = worker.terminate_session(force=False, timeout=5)
           graceful_results.append((worker, result, None))
       except Exception as e:
           graceful_results.append((worker, None, e))
   ```

2. **Check termination success**
   ```python
   failed_workers = []
   for worker, result, error in graceful_results:
       if error or not worker.is_session_stopped:
           failed_workers.append((worker, error))
       else:
           click.echo(f"  ✓ Stopped {worker.name}")
   ```

3. **Force termination for failed workers**
   ```python
   if failed_workers:
       if not force:
           click.echo(f"Warning: {len(failed_workers)} sessions failed to stop gracefully:")
           for worker, error in failed_workers:
               click.echo(f"  - {worker.name}: {error or 'unresponsive'}")

           if not click.confirm("Force kill remaining sessions?"):
               raise SessionStopError("Some sessions failed to stop")
           force = True

       for worker, _ in failed_workers:
           try:
               worker.terminate_session(force=True, timeout=0)
               click.echo(f"  ⚠ Force-killed {worker.name}")
           except Exception as e:
               click.echo(f"  ✗ Failed to kill {worker.name}: {e}")
   ```

4. **Verify all sessions stopped**
   ```python
   still_active = get_active_sessions(db)
   if still_active and not force:
       worker_names = [Worker.get(db, s.worker_id).name for s in still_active]
       raise SessionStopError(
           f"{len(still_active)} sessions still active: {', '.join(worker_names)}\n"
           "Use --force to kill zombie sessions"
       )
   ```

**Session Termination Details:**

Worker.terminate_session() behavior:
- **Graceful (force=False):**
  - Send SIGTERM to process
  - Wait for process exit (up to timeout)
  - Clean up tmux session
  - Update worker runtime status
  - Return success/failure

- **Forced (force=True):**
  - Send SIGKILL to process
  - Kill tmux session immediately
  - Clean up database records
  - Update worker runtime status
  - Always succeeds (or raises if process unkillable)

---

### Phase 4: State Persistence

**Purpose:** Save worker state for clean resume

**Steps:**

1. **Persist worker runtime state**
   ```python
   for session in all_sessions_that_were_active:
       worker = Worker.get(db, session.worker_id)
       _save_worker_resume_state(db, worker)
   ```

2. **Update session records**
   ```python
   _mark_sessions_stopped(
       db,
       session_ids=[s.id for s in active_sessions],
       stop_reason="org_stop",
       graceful=not force,
   )
   ```

3. **Save org stop metadata**
   ```python
   _record_org_stop_event(
       db,
       stopped_by=current_user,
       graceful=not force,
       sessions_stopped=len(active_sessions),
       timestamp=datetime.now(),
   )
   ```

**Worker Resume State:**

Saved for each worker:
```python
{
    "worker_id": "wrkr-abc",
    "last_runtime_status": "working",  # Before stop
    "last_active_task": "task-123",
    "last_session_id": "sess-xyz",
    "stop_reason": "org_stop",
    "graceful_stop": True,
    "stopped_at": "2026-01-26T12:00:00Z",
}
```

This enables resume to:
- Restore worker to working on the same task
- Show "You were working on: {task}" in welcome message
- Resume with context about what was happening

---

### Phase 5: Org State Transition

**Purpose:** Mark org as stopped

**Steps:**

1. **Update org status**
   ```python
   org.stop()  # RUNNING → STOPPED
   ```

2. **Update org-chart** (optional)
   ```python
   update_org_chart(db, org_path, stopped=True)
   ```

3. **Log stop event**
   ```python
   _logger.info(
       f"Org stopped: {len(active_sessions)} sessions terminated",
       extra={
           "org_path": str(org_path),
           "graceful": not force,
           "sessions_stopped": len(active_sessions),
       }
   )
   ```

---

### Phase 6: Cleanup

**Purpose:** Clean up temporary state and old data

**Steps:**

1. **Clean up notification beads** (if --cleanup, default True)
   ```python
   if cleanup:
       result = run_notification_cleanup(db, retention_days=7)
       if result["total_purged"] > 0:
           click.echo(f"Cleanup: purged {result['total_purged']} old notifications")
   ```

2. **Close communication channels** (optional, P2)
   ```python
   _close_ephemeral_channels(db)
   ```

3. **Reset worker runtime states**
   ```python
   for session in active_sessions:
       worker = Worker.get(db, session.worker_id)
       worker.update_runtime_status("stopped")
   ```

4. **Clean up lock files** (if any)
   ```python
   _remove_lock_files(org_path)
   ```

---

## CLI Interface

### Command Signature

```bash
qn org stop [OPTIONS]
```

### Options

**Existing:**
- `--cleanup / --no-cleanup` (default: True)
  - Run notification cleanup on stop
  - Purges old notifications based on retention policy

- `--worker TEXT`
  - Stop workday for specific worker (org must be running)
  - Sends wrap-up notification and terminates worker session only

- `--force`
  - Force kill sessions without waiting for graceful shutdown
  - Skip wrap-up acknowledgment wait
  - Kill unresponsive processes immediately

**New (proposed):**

- `--graceful-timeout INTEGER` (default: 30)
  - Seconds to wait for worker wrap-up acknowledgments
  - After timeout, prompts to force-kill or abort

- `--yes / -y`
  - Skip confirmation prompts
  - Useful for automation/scripts

- `--save-state / --no-save-state` (default: True)
  - Save worker state for resume
  - Disable for clean stop without resume capability

---

## Implementation Strategy

### Changes Required

**1. cli/commands/org/stop.py**

Restructure into phases:
```python
def stop_cmd(ctx, cleanup, worker, force, graceful_timeout, yes, save_state):
    # Phase 1: Pre-stop validation
    org = _validate_org_stoppable(org_path, force)
    active_sessions = _get_active_sessions(db)
    if active_sessions and not yes:
        _confirm_stop(active_sessions)

    # Phase 2: Worker wrap-up (graceful shutdown)
    if not force and active_sessions:
        acknowledged = _send_wrap_up_and_wait(
            db, org_path, active_sessions, graceful_timeout
        )
        if len(acknowledged) < len(active_sessions):
            # Handle timeout
            force = _prompt_force_terminate()

    # Phase 3: Session termination
    _terminate_all_sessions(db, active_sessions, force)
    _verify_all_stopped(db, force)

    # Phase 4: State persistence
    if save_state:
        _save_worker_states(db, active_sessions)

    # Phase 5: Org state transition
    org.stop()
    update_org_chart(db, org_path)

    # Phase 6: Cleanup
    if cleanup:
        run_notification_cleanup(db)
    _reset_runtime_states(db, active_sessions)
```

**2. Worker wrap-up system (new)**

Create `cli/core/wrapup.py`:
```python
def send_wrap_up_notification(
    db: Database,
    org_path: Path,
    worker: Worker,
    timeout: int,
) -> str:
    """Send wrap-up notification to worker.

    Returns notification_id for tracking acknowledgment.
    """
    pass

def check_wrap_up_acknowledgment(
    db: Database,
    worker_id: str,
    notification_id: str,
) -> bool:
    """Check if worker acknowledged wrap-up.

    Checks:
    1. Reply message in channel
    2. Runtime status = "wrapping_up"
    3. "Wrap-up complete" bead created
    """
    pass

def wait_for_wrap_up_acknowledgments(
    db: Database,
    worker_notifications: dict[str, str],  # worker_id -> notification_id
    timeout: int,
) -> set[str]:
    """Wait for workers to acknowledge wrap-up.

    Returns set of worker_ids that acknowledged.
    """
    pass
```

**3. State persistence (new)**

Create `cli/core/resume_state.py`:
```python
@dataclass
class WorkerResumeState:
    """State saved for worker resume."""
    worker_id: str
    last_runtime_status: str
    last_active_task: Optional[str]
    last_session_id: str
    stop_reason: str
    graceful_stop: bool
    stopped_at: datetime

def save_worker_resume_state(db: Database, worker: Worker) -> None:
    """Save worker state for resume."""
    pass

def load_worker_resume_state(db: Database, worker_id: str) -> Optional[WorkerResumeState]:
    """Load saved worker state."""
    pass

def clear_worker_resume_state(db: Database, worker_id: str) -> None:
    """Clear saved state after successful resume."""
    pass
```

**4. Database schema (new tables)**

Add to schema:
```sql
CREATE TABLE worker_resume_states (
    worker_id TEXT PRIMARY KEY,
    last_runtime_status TEXT NOT NULL,
    last_active_task TEXT,
    last_session_id TEXT,
    stop_reason TEXT NOT NULL,
    graceful_stop INTEGER NOT NULL DEFAULT 1,
    stopped_at TIMESTAMP NOT NULL,
    FOREIGN KEY (worker_id) REFERENCES workers(id)
);

CREATE TABLE org_stop_events (
    id TEXT PRIMARY KEY,
    stopped_by TEXT,
    graceful INTEGER NOT NULL DEFAULT 1,
    sessions_stopped INTEGER NOT NULL DEFAULT 0,
    stopped_at TIMESTAMP NOT NULL
);
```

**5. Worker.terminate_session() improvements**

Update `cli/core/worker.py`:
```python
def terminate_session(
    self,
    force: bool = False,
    timeout: int = 5,
    reason: str = "manual",
) -> SessionStopResult:
    """Terminate worker session.

    Args:
        force: If True, use SIGKILL. If False, use SIGTERM and wait.
        timeout: Seconds to wait for graceful termination.
        reason: Reason for termination (logged).

    Returns:
        SessionStopResult with success status and details.
    """
    pass
```

---

## Sequence Diagrams

### Graceful Stop (Happy Path)

```
User         CLI           Org         Worker1      Worker2
 |            |             |             |            |
 |─stop───────>|             |             |            |
 |            |─validate────>|             |            |
 |            |<──ok────────|             |            |
 |            |                           |            |
 |            |─wrap-up──────────────────>|            |
 |            |─wrap-up──────────────────────────────>|
 |            |                           |            |
 |            |<─ack────────────────────|            |
 |            |<─ack────────────────────────────────|
 |            |                           |            |
 |            |─terminate────────────────>|            |
 |            |─terminate────────────────────────────>|
 |            |<─stopped─────────────────|            |
 |            |<─stopped─────────────────────────────|
 |            |                           |            |
 |            |─stop()───────>|             |            |
 |            |<─STOPPED─────|             |            |
 |<─success───|             |             |            |
```

### Graceful Stop with Timeout

```
User         CLI           Org         Worker1      Worker2
 |            |             |             |            |
 |─stop───────>|             |             |            |
 |            |─wrap-up──────────────────>|            |
 |            |─wrap-up──────────────────────────────>|
 |            |                           |            |
 |            |<─ack────────────────────|            |
 |            |  (waiting...)            X no ack    |
 |            |  (timeout)               |            |
 |            |                           |            |
 |<─confirm───| "Force-kill Worker2?"    |            |
 | force?     |                           |            |
 |─yes────────>|                           |            |
 |            |─force-kill───────────────────────────>|
 |            |<─killed──────────────────────────────|
 |            |                           |            |
 |            |─stop()───────>|             |            |
 |<─success───|             |             |            |
```

### Force Stop (No Wrap-Up)

```
User            CLI           Org         Workers
 |               |             |             |
 |─stop --force─>|             |             |
 |               |─kill────────────────────>|
 |               |<─killed──────────────────|
 |               |                           |
 |               |─stop()───────>|             |
 |               |<─STOPPED─────|             |
 |<─success──────|             |             |
```

### Worker-Specific Stop

```
User         CLI           Worker       Session
 |            |              |             |
 |─stop       |              |             |
  --worker─────>|              |             |
 |            |─wrap-up──────>|             |
 |            |<─ack─────────|             |
 |            |                            |
 |            |─terminate─────────────────>|
 |            |<─stopped───────────────────|
 |            |                            |
 |<─success───|              |             |
```

---

## Test Scenarios

### P0 - Must Have

1. **Graceful stop (all workers acknowledge)**
   - Send wrap-up to all workers
   - All acknowledge within timeout
   - All sessions terminate gracefully
   - Org status → STOPPED
   - State saved for resume

2. **Graceful stop with timeout**
   - Some workers don't acknowledge
   - Timeout reached
   - Prompt user to force-kill
   - Force-kill unresponsive workers
   - Org stops successfully

3. **Force stop (skip wrap-up)**
   - --force flag set
   - No wrap-up sent
   - Sessions killed immediately
   - Org status → STOPPED

4. **Already stopped (idempotent)**
   - Org status already STOPPED
   - No sessions active
   - Returns success immediately
   - Optional: Clean up zombie sessions with --force

5. **Worker-specific stop**
   - Org remains RUNNING
   - Only target worker gets wrap-up
   - Only target worker session terminates
   - Other workers unaffected

### P1 - Important

6. **Stop with zombie sessions**
   - Some session records exist but processes dead
   - Clean up stale records
   - Org stops successfully

7. **Stop with failed termination**
   - Some sessions fail to terminate gracefully
   - Prompt for force-kill
   - Force-kill or abort

8. **Resume after stop**
   - Stop org with state save
   - Start org again
   - Workers restore last task context
   - Welcome message shows "You were working on..."

9. **Stop without state save**
   - --no-save-state flag
   - Sessions terminate
   - No resume state saved
   - Clean stop

### P2 - Nice to Have

10. **Stop with work in progress warning**
    - Active sessions detected
    - Show what each worker is doing
    - Confirm before stopping
    - Can cancel

11. **Stop with notification cleanup**
    - Old notifications purged
    - Active notifications preserved
    - Report purge counts

12. **Concurrent stop attempts**
    - First stop in progress
    - Second stop detects and waits
    - No race conditions

---

## Success Criteria

Stop sequence is complete when:

1. ✅ **Wrap-up workflow**: Workers get notification and time to acknowledge
2. ✅ **Graceful shutdown**: Timeout with force-kill option
3. ✅ **Session verification**: All sessions confirmed stopped before org status update
4. ✅ **State persistence**: Worker state saved for resume
5. ✅ **Idempotent**: Safe to run when already stopped
6. ✅ **Clear feedback**: User knows what's happening at each step
7. ✅ **All tests pass**: Coverage for all P0 scenarios

---

## Open Questions

1. **Wrap-up acknowledgment timeout?**
   - Default: 30 seconds
   - Configurable: --graceful-timeout
   - **Recommendation**: 30s default, make it configurable

2. **Should we auto-save worker beads on wrap-up?**
   - Trigger "bd sync" in worker session before stopping
   - **Recommendation**: P2 enhancement, document in wrap-up message for now

3. **What if worker session is crashed/dead?**
   - No acknowledgment possible
   - Treat as timeout, force-kill
   - **Recommendation**: Check session health before sending wrap-up

4. **Resume state retention?**
   - How long to keep worker_resume_states?
   - Clear on successful resume or keep for audit?
   - **Recommendation**: Clear on successful start, 7-day retention for orphans

---

## Implementation Priority

### Phase 1 (P0)
- Implement wrap-up notification system
- Add graceful timeout with acknowledgment polling
- Verify all sessions stopped before org status update
- Add worker resume state persistence

### Phase 2 (P1)
- Add --graceful-timeout flag
- Improve error messages for failed terminations
- Add resume state restore on org start
- Write integration tests

### Phase 3 (P2)
- Add work-in-progress warnings
- Implement shutdown hooks for workers
- Add stop reason tracking
- Extended test coverage

---

## Related Docs

- org-stop-audit-2026-01-25.md (current behavior analysis)
- org-start-sequence-design.md (companion design)
- worker-onboarding-design.md (worker context system)
