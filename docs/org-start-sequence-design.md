# Org Start Sequence Design

**Task:** quinnai-cjd5
**Author:** Claude (design review)
**Date:** 2026-01-26
**Status:** Proposed

---

## Overview

This document defines the complete and reliable `qn org start` sequence that addresses all gaps identified in the org-start-audit-2026-01-25.md.

**Design Goals:**
1. **Unified behavior** - Same result whether starting from INITIALIZED or STOPPED
2. **Reliability** - Proper error handling with rollback on failures
3. **Visibility** - Clear feedback on org readiness
4. **Idempotency** - Safe to run multiple times
5. **Validation** - Catch configuration errors early

---

## State Machine

### Org States

```
INITIALIZED → RUNNING → STOPPED
     ↓          ↑          ↓
     └──────────┴──────────┘
```

**Valid Transitions:**
- `INITIALIZED → RUNNING` - First start (activates CEO)
- `STOPPED → RUNNING` - Resume (CEO already active)
- `RUNNING → RUNNING` - Idempotent (no-op or health check)

**Invalid:**
- Any other transition should fail with `InvalidOrgTransition`

### CEO Lifecycle States

```
pending → onboarding → active
                         ↓
                    offboarding → terminated
```

**During Start:**
- INITIALIZED: CEO goes `pending → onboarding → active`
- STOPPED: CEO remains `active` (already went through onboarding)

---

## Sequence Design

### Phase 1: Pre-Flight Validation (MUST complete before state changes)

**Purpose:** Catch errors early, before mutating state

**Steps:**
1. **Validate org exists**
   ```python
   db_path = get_org_db_path(org_path)
   if not db_path.exists():
       raise OrgNotFoundError(org_path)
   ```

2. **Validate provider configuration** (unless --skip-config-validation)
   ```python
   config_path = get_org_config_path(org_path)
   org_config = load_org_config(config_path)
   validate_and_raise(org_config)
   ```

3. **Validate org directory structure**
   ```python
   required_dirs = ["config", "live", "storage/shared", "storage/workers"]
   for dir_name in required_dirs:
       dir_path = org_path / dir_name
       if not dir_path.exists():
           raise OrgStructureError(f"Missing directory: {dir_name}")
   ```

4. **Load org and check CEO exists**
   ```python
   org = Org.load(db)
   if not org.ceo:
       raise OrgConfigError("Organization has no CEO")
   ```

5. **Determine start mode**
   ```python
   current_status = org.status
   if current_status == OrgStatus.RUNNING:
       start_mode = StartMode.ALREADY_RUNNING
   elif current_status == OrgStatus.INITIALIZED:
       start_mode = StartMode.FIRST_START
   elif current_status == OrgStatus.STOPPED:
       start_mode = StartMode.RESUME
   else:
       raise InvalidOrgTransition(f"Cannot start from {current_status}")
   ```

**Exit Criteria:**
- All validations pass → continue to Phase 2
- Any validation fails → Exit with clear error, no state changes

---

### Phase 2: Org State Transition

**Purpose:** Update org and CEO state consistently

**Mode: FIRST_START (INITIALIZED → RUNNING)**

1. Begin transaction (conceptually - we'll use try/except for rollback)
2. Transition CEO lifecycle: `pending → onboarding → active`
   ```python
   ceo.start_onboarding()  # pending → onboarding
   ceo.complete_onboarding()  # onboarding → active
   ```
3. Deliver CEO briefing (if exists)
   ```python
   briefing_path = org_path / "config" / "ceo_briefing.md"
   if briefing_path.exists():
       deliver_ceo_briefing(db, ceo.id, briefing_path)
   ```
4. Update org status: `INITIALIZED → RUNNING`
   ```python
   org.start()  # Handles state transition
   ```
5. Update org-chart
   ```python
   update_org_chart(db, org_path)
   ```

**Mode: RESUME (STOPPED → RUNNING)**

1. Update org status: `STOPPED → RUNNING`
   ```python
   org.start()  # Handles state transition
   ```
2. CEO lifecycle remains `active` (no changes)

**Mode: ALREADY_RUNNING**

1. Check CEO session health
   ```python
   if org.ceo.is_session_active:
       if spawn_ceo:
           print("CEO session already running")
       return  # Nothing to do
   else:
       print("Warning: Org is RUNNING but CEO session is not active")
       # Continue to spawn CEO session
   ```

**Rollback on Failure:**
If any step fails:
- Revert CEO lifecycle changes (active → previous state)
- Revert org status (RUNNING → previous state)
- Re-raise exception with context

---

### Phase 3: CEO Session Spawning (if spawn_ceo=True)

**Purpose:** Start CEO's AI session with full context

**Decision:** Spawn CEO session if:
- `spawn_ceo=True` (flag set)
- AND CEO session is not already active
- AND org is in RUNNING state

**Steps:**

1. **Check if CEO session already active**
   ```python
   if ceo.is_session_active:
       click.echo("CEO session already running")
       return  # Skip spawn
   ```

2. **Prepare onboarding materials**
   ```python
   onboarding_ctx = prepare_worker_onboarding(db, ceo.id, org_path)
   ```
   - Creates worker directory (hierarchical path)
   - Writes BRIEFING.md, STORAGE.md, WELCOME.md
   - Symlinks CLAUDE.md, AGENTS.md
   - Returns OnboardingContext with worker metadata

3. **Get worker directory and env vars**
   ```python
   storage = StorageManager(org_path, db)
   worker_dir = storage.get_worker_path(ceo.id)
   env_vars = get_worker_env_vars(onboarding_ctx, org_path, db)
   ```

4. **Create session configuration**
   ```python
   config = SessionConfig(
       worker_id=ceo.id,
       provider=provider,
       command=command,
       args=args,
       working_directory=worker_dir,
       env_vars=env_vars,
   )
   ```

5. **Validate provider availability**
   ```python
   registry = get_default_registry()
   if not registry.has(provider):
       available = registry.list_adapters()
       raise SessionProviderNotFound(provider, available)
   ```

6. **Spawn session**
   ```python
   ceo.set_registry(registry)
   session = ceo.spawn(config)
   ```
   - Worker.spawn() handles:
     - Budget validation
     - Session creation via registry
     - Runtime status tracking
     - Error handling

7. **Wait for session ready** (optional, with --wait flag)
   ```python
   if wait_ready:
       timeout = wait_timeout or 60  # seconds
       start_time = time.time()
       while time.time() - start_time < timeout:
           if ceo.runtime_status == RuntimeStatus.READY:
               break
           time.sleep(1)
       else:
           raise SessionStartTimeout(ceo.id, timeout)
   ```

**Error Handling:**

If CEO session spawn fails:
1. Log error with full context
2. DO NOT rollback org state (org is still RUNNING, just CEO session failed)
3. Show helpful error message:
   ```
   Error: Failed to spawn CEO session
   Reason: {error_message}

   Organization is RUNNING but CEO session is not active.

   To retry:
     qn org start --spawn-ceo

   To debug:
     qn org status
     qn wrkr logs ceo
   ```

**Why not rollback org state?**
- Org infrastructure is valid (db, directories, etc)
- Other workers could be spawned independently
- User can fix session issue and retry without full org restart
- Separates org lifecycle from session lifecycle

---

### Phase 4: Readiness Verification (if --wait flag)

**Purpose:** Confirm org is operational before returning

**Steps:**

1. **Check org status**
   ```python
   assert org.status == OrgStatus.RUNNING
   ```

2. **Check CEO session status** (if spawn_ceo=True)
   ```python
   if spawn_ceo:
       assert ceo.is_session_active
       if wait_ready:
           assert ceo.runtime_status == RuntimeStatus.READY
   ```

3. **Report readiness**
   ```python
   click.echo("Organization is ready")
   click.echo(f"  Status: {org.status}")
   click.echo(f"  CEO: {ceo.name} - {ceo.runtime_status}")
   ```

---

## CLI Interface

### Command Signature

```bash
qn org start [OPTIONS]
```

### Options

**Existing:**
- `--spawn-ceo / --no-spawn-ceo` (default: True)
  - Whether to spawn CEO session after org state transition
  - Use --no-spawn-ceo if you want to start org infrastructure without spawning sessions

- `--provider TEXT` (default: claude_code)
  - Session provider for CEO

- `--command TEXT` (default: claude)
  - CLI command for session

- `--args TEXT` (default: --dangerously-skip-permissions)
  - Additional args for session command

- `--skip-config-validation`
  - Skip provider configuration validation (for testing)

- `--worker TEXT`
  - Start workday for specific worker (org must already be RUNNING)

**New (proposed):**

- `--wait / --no-wait` (default: False)
  - Wait for CEO session to reach READY state before returning
  - Useful for automation/scripts

- `--wait-timeout INTEGER` (default: 60)
  - Seconds to wait for session ready (requires --wait)

- `--force`
  - Force restart CEO session even if already active
  - Terminates existing session first, then spawns new one

---

## Implementation Strategy

### Changes Required

**1. cli/commands/org/start.py**

Restructure into phases:
```python
def start_cmd(...):
    # Phase 1: Pre-flight validation
    _validate_org_structure(org_path)
    _validate_provider_config(org_path, skip_validation)
    org = _load_and_validate_org(db, org_path)
    start_mode = _determine_start_mode(org)

    # Phase 2: Org state transition
    try:
        _transition_org_state(org, db, org_path, start_mode)
    except Exception as e:
        _rollback_org_state(org, db, start_mode)
        raise OrgStartError(f"State transition failed: {e}")

    # Phase 3: CEO session spawning
    if spawn_ceo and not org.ceo.is_session_active:
        try:
            _spawn_ceo_session(org.ceo, org_path, db, provider, ...)
        except Exception as e:
            # Don't rollback org state - just report error
            raise SessionSpawnError(f"CEO session spawn failed: {e}")

    # Phase 4: Readiness verification
    if wait:
        _wait_for_ready(org.ceo, wait_timeout)
```

**2. cli/core/org.py**

Add rollback support to Org.start():
```python
def start(self) -> tuple[str, str]:  # Returns (old_status, new_status)
    """Start org with rollback support."""
    old_status = self.status
    # ... existing logic ...
    new_status = self.status
    return (old_status, new_status)

def rollback_to_status(self, target_status: str) -> None:
    """Rollback org to previous status (for error recovery)."""
    update_org_status(self.db, target_status)
    self._org_data = None  # Invalidate cache
```

**3. cli/core/worker.py**

Add session health check:
```python
@property
def is_session_healthy(self) -> bool:
    """Check if session is active and responding."""
    if not self.is_session_active:
        return False
    # Could add ping/health check here
    return True
```

**4. Error Classes (shared/exceptions.py)**

Add specific exceptions:
```python
class OrgStartError(Exception):
    """Base error for org start failures."""
    pass

class OrgStructureError(OrgStartError):
    """Org directory structure is invalid."""
    pass

class SessionSpawnError(OrgStartError):
    """Session spawn failed."""
    pass

class SessionStartTimeout(OrgStartError):
    """Session did not reach ready state within timeout."""
    pass
```

---

## Sequence Diagrams

### First Start (INITIALIZED → RUNNING)

```
User           CLI              Org            CEO Worker     Session
 |              |                |                |             |
 |─start────────>|                |                |             |
 |              |─validate────────>|                |             |
 |              |<────ok──────────|                |             |
 |              |                |                |             |
 |              |─start()─────────>|                |             |
 |              |                |─onboarding()───>|             |
 |              |                |<───active──────|             |
 |              |<─RUNNING───────|                |             |
 |              |                |                |             |
 |              |─spawn()────────────────────────>|             |
 |              |                |                |─create()───>|
 |              |                |                |<─starting──|
 |              |<────ok────────────────────────|             |
 |<─success────|                |                |             |
```

### Resume (STOPPED → RUNNING)

```
User           CLI              Org            CEO Worker     Session
 |              |                |                |             |
 |─start────────>|                |                |             |
 |              |─validate────────>|                |             |
 |              |<────ok──────────|                |             |
 |              |                |                |             |
 |              |─start()─────────>|                |             |
 |              |<─RUNNING───────|                |             |
 |              |                |                |             |
 |              |─spawn()────────────────────────>|             |
 |              |                |                |─create()───>|
 |              |                |                |<─starting──|
 |              |<────ok────────────────────────|             |
 |<─success────|                |                |             |
```

### Already Running (Idempotent)

```
User           CLI              Org            CEO Worker
 |              |                |                |
 |─start────────>|                |                |
 |              |─status()───────>|                |
 |              |<─RUNNING───────|                |
 |              |                |                |
 |              |─session?───────────────────────>|
 |              |<─active────────────────────────|
 |              |                |                |
 |<─already────|                |                |
    running     |                |                |
```

### Failure with Rollback

```
User           CLI              Org            CEO Worker
 |              |                |                |
 |─start────────>|                |                |
 |              |─start()─────────>|                |
 |              |                |─onboarding()───>|
 |              |                |    X error     |
 |              |                |                |
 |              |─rollback()──────>|                |
 |              |<─INITIALIZED────|                |
 |              |                |                |
 |<─error──────|                |                |
```

---

## Test Scenarios

### P0 - Must Have

1. **First start (happy path)**
   - INITIALIZED → RUNNING
   - CEO pending → active
   - CEO session spawns
   - All artifacts created

2. **Resume (happy path)**
   - STOPPED → RUNNING
   - CEO remains active
   - CEO session spawns
   - No duplicate artifacts

3. **Idempotent (already running)**
   - Status remains RUNNING
   - CEO session already active
   - No changes made
   - Returns success immediately

4. **Rollback on CEO activation failure**
   - CEO lifecycle fails (e.g., db constraint)
   - Org status reverts to INITIALIZED
   - Clear error message
   - Can retry start

5. **Session spawn failure (no rollback)**
   - Org state succeeds (RUNNING)
   - CEO activation succeeds (active)
   - Session spawn fails (budget, provider, etc.)
   - Org remains RUNNING
   - Can retry session spawn

### P1 - Important

6. **Invalid provider config**
   - Validation catches before state changes
   - Clear error message
   - No state changes

7. **Missing org structure**
   - Validation catches missing directories
   - Clear error message
   - No state changes

8. **Wait for ready (--wait)**
   - Session spawns
   - Command waits for READY status
   - Returns when CEO is ready
   - Timeout if not ready in time

9. **Worker-specific start**
   - Org must be RUNNING
   - Worker session spawns
   - Uses onboarding system
   - Independent of CEO session

### P2 - Nice to Have

10. **Force restart (--force)**
    - Terminates existing CEO session
    - Spawns new session
    - Clean state reset

11. **Missing CEO briefing**
    - Start succeeds without briefing
    - No error or warning
    - CEO spawns normally

12. **Concurrent start attempts**
    - First start succeeds
    - Second start sees "already running"
    - No race conditions

---

## Success Criteria

Start sequence is complete when:

1. ✅ **Unified behavior**: Same result from INITIALIZED and STOPPED
2. ✅ **Proper rollback**: State reverts on CEO activation failures
3. ✅ **No rollback on session spawn**: Org stays RUNNING if only session fails
4. ✅ **Idempotent**: Safe to run when already running
5. ✅ **Clear errors**: Helpful messages for all failure modes
6. ✅ **Readiness wait**: --wait flag blocks until CEO ready
7. ✅ **All tests pass**: Coverage for all P0 scenarios

---

## Open Questions

1. **Should --wait be default?**
   - Pro: Users know when org is ready
   - Con: Slower UX, fails if session doesn't reach ready
   - **Recommendation**: Default False, explicit --wait for automation

2. **Should we support spawning multiple workers at once?**
   - `qn org start --workers ceo,director-x,engineer-y`
   - **Recommendation**: Future feature, start with CEO only

3. **Should we add health checks to "already running" path?**
   - Verify CEO session is responsive, not just active
   - **Recommendation**: P2 enhancement, basic check sufficient for now

4. **What timeout for --wait?**
   - Default: 60 seconds
   - Configurable: --wait-timeout
   - **Recommendation**: Start with 60s default, make it configurable

---

## Implementation Priority

### Phase 1 (P0)
- Restructure start_cmd into phases
- Add rollback support to Org.start()
- Fix resume path to spawn CEO session
- Add idempotent "already running" check

### Phase 2 (P1)
- Add --wait and --wait-timeout flags
- Improve error messages
- Add session health check
- Write integration tests

### Phase 3 (P2)
- Add --force flag
- Cache provider validation
- Performance optimization
- Extended test coverage

---

## Related Docs

- org-start-audit-2026-01-25.md (current behavior analysis)
- org-stop-sequence-design.md (companion design)
- worker-onboarding-design.md (onboarding system)
- architecture-decisions/003-onboarding-session-modification.md (onboarding principles)
