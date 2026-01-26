# Org Start Sequence Audit - 2026-01-25

**Task:** quinnai-z3qs
**Auditor:** Claude (automated)
**Scope:** Document current 'org start' behavior and identify gaps

---

## Command Entry Point

**File:** `cli/commands/org/start.py`
**Function:** `start_cmd()`

**Arguments:**
- `--spawn-ceo/--no-spawn-ceo` (default: True) - Whether to spawn CEO session after start
- `--worker <name|id>` - Start workday for specific worker (requires org already running)
- `--provider` (default: claude_code) - Session provider for CEO
- `--command` (default: claude) - CLI command for session
- `--args` (default: --dangerously-skip-permissions) - Additional args for session command
- `--skip-config-validation` - Skip provider configuration validation

---

## Execution Flow

### 1. **Pre-flight Checks** (start.py:82-105)

```
✓ Check if quinn.db exists at org_path/live/quinn.db
✓ Validate provider configuration (unless --skip-config-validation)
  - Load org config from config/providers.yaml
  - validate_and_raise() checks provider settings
  - Fails with clear error if invalid
```

**Potential Issues:**
- Config validation happens on every start (could cache?)
- No check for org directory structure integrity

### 2. **Worker-Specific Start** (start.py:112-154)

If `--worker` flag provided:

```
✓ Check org status == RUNNING (fail if not)
✓ Get worker by name or ID
✓ Create worker directory (storage/workers/{worker_id})
✓ Load onboarding context (load_onboarding_context)
✓ Get environment variables (get_worker_env_vars)
✓ Generate returning message (generate_returning_message)
✓ Spawn worker session (spawn_worker_session)
  - Uses force_restart=True
```

**Potential Issues:**
- No validation that worker lifecycle allows session spawning
- Creates directory even if worker doesn't exist (until lookup fails)
- Hardcoded force_restart=True might forcefully kill existing sessions

### 3. **Org Start - Already Running Check** (start.py:156-158)

```
if org.status == OrgStatus.RUNNING.value:
    click.echo("Organization is already running.")
    return
```

**Potential Issues:**
- Returns silently without checking if CEO session is actually running
- User may think org is fully operational when CEO session is dead

### 4. **Org State Transition** (start.py:160-166)

```
✓ Call org.start()
  - Validates state transition
  - If INITIALIZED → RUNNING:
    * Activate CEO (start_onboarding → complete_onboarding)
    * Deliver CEO briefing if exists
  - If STOPPED → RUNNING:
    * Just update status
✓ Catch InvalidOrgTransition with helpful error
```

**Org.start() Implementation** (org.py:223-260):

**From INITIALIZED:**
1. Validate transition (initialized → running)
2. Get CEO worker
3. `ceo.start_onboarding()` - transitions CEO from pending to onboarding
4. `ceo.complete_onboarding()` - transitions CEO from onboarding to active
5. Deliver CEO briefing:
   - Check if ceo_briefing.md exists in config/
   - Create message in board-channel with briefing content
   - Create notification bead for CEO (P0)
   - Skip if already delivered (check for existing message)
6. Update org_status to RUNNING
7. Log state change

**From STOPPED:**
1. Validate transition (stopped → running)
2. Update org_status to RUNNING
3. Log state change

**Potential Issues:**
- No validation that CEO worker actually exists before accessing
- CEO lifecycle transitions happen without checking current state first
- Briefing delivery happens regardless of whether CEO session will spawn
- No rollback if CEO activation fails

### 5. **Update Org Chart** (start.py:168-169)

```
✓ update_org_chart(db, org_path)
  - Reflects lifecycle changes (CEO now active)
```

**Potential Issues:**
- Org chart update is best-effort (exceptions swallowed)
- No indication to user if org chart update fails

### 6. **CEO Session Spawning** (start.py:174-186)

If `spawn_ceo` is True:

```
✓ Call _spawn_ceo_session()
  - Get CEO worker instance
  - Prepare onboarding (prepare_worker_onboarding)
  - Get worker directory (storage/workers/{ceo_id})
  - Get environment variables
  - Generate welcome message
  - Create SessionConfig
  - Check provider exists in registry
  - Set registry on CEO worker
  - Call ceo.spawn(config)
```

**_spawn_ceo_session() Implementation** (start.py:192-256):

1. **Prepare Onboarding** (lines 218-222):
   - Opens NEW database connection
   - Calls prepare_worker_onboarding()
   - Closes database connection

2. **Setup Worker Directory** (line 225):
   - Gets worker dir: `org_path/storage/workers/{ceo_id}`

3. **Get Environment Variables** (line 228):
   - `get_worker_env_vars(onboarding_ctx, org_path)`
   - Returns dict with BRIEFING_PATH, etc.

4. **Generate Welcome Message** (line 231):
   - `generate_welcome_message(onboarding_ctx, worker_dir)`

5. **Create Session Config** (lines 234-242):
   ```python
   SessionConfig(
       worker_id=ceo.id,
       provider=provider,
       command=command,
       args=args,  # Parsed from args_str.split()
       working_directory=worker_dir,  # Worker dir, NOT org root
       env_vars=env_vars,
       welcome_message=welcome,
   )
   ```

6. **Validate Provider** (lines 245-252):
   - Get default registry
   - Check if provider exists
   - Fail with clear error + available providers list

7. **Spawn Session** (lines 255-256):
   - Set registry on CEO worker
   - Call `ceo.spawn(config)`
   - This triggers Worker.spawn() → Worker.spawn_session()

**Worker.spawn() Flow** (worker.py:1437-1481):
1. `_ensure_onboarding(config)` - Prepare onboarding artifacts if needed
2. Get session registry (instance or default)
3. `registry.create(config.provider, config)` - Create session via registry
4. `spawn_session(session)` - Delegate to existing spawn logic
5. Return session instance

**Worker.spawn_session() Flow** (worker.py:1163-1192):
1. **Phase 1: Validate Preconditions** (1194-1227):
   - Check no existing active session (raises ActiveSessionExistsError)
   - Ensure worker_state row exists (creates if missing)

2. **Phase 2: Budget Enforcement** (1229-1258):
   - Estimate session spawn cost based on worker cost tier
   - Check budget allocation (raises BudgetExhaustedError or NoBudgetAllocationError)

3. **Phase 3: Attach and Start** (1260-1280):
   - Attach session to worker
   - Start session (state callbacks update worker runtime status)
   - Detach on failure

4. **Phase 4: Finalize** (1282-1364):
   - Record spend against budget
   - Create session record in database
   - Update PID if available
   - Log successful spawn
   - Handle race conditions (another session created concurrently)

**Potential Issues:**
- NEW database connection opened and closed just for onboarding prep (lines 218-222)
- No verification that CEO worker lifecycle is in correct state for spawning
- No check if CEO session is already running before attempting spawn
- No rollback if session spawn fails after org status updated to RUNNING
- User only sees "CEO session spawned (provider: {provider})" - no indication if it failed
- Exceptions from spawn() may not be caught, leaving org in inconsistent state

---

## State After Successful Start

**From INITIALIZED:**
- Org status: RUNNING
- CEO lifecycle: active
- CEO session: starting/running (if spawn_ceo=True)
- CEO has notification bead with briefing (if briefing exists)
- Org chart updated

**From STOPPED:**
- Org status: RUNNING
- CEO lifecycle: unchanged (already active)
- CEO session: NOT spawned (spawn_ceo only happens from INITIALIZED)
- Org chart unchanged

---

## Critical Gaps Identified

### 1. **Inconsistent Resume Behavior**
- Starting from STOPPED does NOT spawn CEO session (spawn_ceo logic only in INITIALIZED path)
- User expects `qn org start` to have same result regardless of previous state
- **Impact:** BLOCKING - CEO session not running after resume

### 2. **No Session State Verification**
- Org status can be RUNNING while CEO session is dead/crashed
- `qn org start` returns "already running" without checking session health
- **Impact:** BLOCKING - False positive on org readiness

### 3. **No Rollback on Partial Failure**
- If CEO session spawn fails, org status is still RUNNING
- No cleanup or state rollback
- **Impact:** HIGH - Inconsistent state after failures

### 4. **Poor Error Handling**
- Session spawn exceptions may propagate to CLI without cleanup
- User sees Python traceback instead of helpful error
- **Impact:** MEDIUM - Poor UX, hard to debug

### 5. **No Readiness Signal**
- Command exits after calling spawn(), doesn't wait for session ready
- User doesn't know when CEO is actually accepting work
- **Impact:** MEDIUM - Race conditions in automation

### 6. **Missing Validation**
- No check that CEO worker exists before accessing
- No check that worker lifecycle allows session spawning
- **Impact:** LOW - Will fail anyway, but with confusing error

---

## Recommendations

### P0 - Critical Fixes
1. **Unified Start Behavior:** Make `spawn_ceo` work from both INITIALIZED and STOPPED
2. **Session Health Check:** Verify CEO session is actually running before returning
3. **Rollback on Failure:** Revert org status if CEO activation/spawn fails

### P1 - Important Improvements
4. **Readiness Wait:** Add `--wait` flag to wait for CEO session ready state
5. **Better Error Handling:** Catch spawn exceptions, clean up state, show helpful errors
6. **Worker State Validation:** Check CEO lifecycle before attempting spawn

### P2 - Nice to Have
7. **Config Caching:** Cache provider validation to speed up start
8. **Org Structure Check:** Validate org directory structure integrity on start
9. **Status Command Integration:** `qn org status --wait-ready` to poll until operational

---

## Files Involved

**Core:**
- cli/commands/org/start.py (main command)
- cli/core/org.py (Org.start() state machine)
- cli/core/worker.py (Worker.spawn(), Worker.spawn_session())
- cli/core/onboarding.py (onboarding preparation)

**Supporting:**
- cli/core/config.py (provider validation)
- cli/core/db.py (database operations)
- cli/core/org_chart.py (org chart updates)
- cli/core/sessions/registry.py (session creation)
- cli/core/budget.py (budget enforcement)
- shared/enums.py (OrgStatus enum)
- shared/__init__.py (ORG_TRANSITIONS, InvalidOrgTransition)

---

## Test Coverage Gaps

Need integration tests for:
- [ ] Start from INITIALIZED with spawn_ceo=True (happy path)
- [ ] Start from INITIALIZED with spawn_ceo=False
- [ ] Start from STOPPED (resume)
- [ ] Start when already RUNNING (idempotent)
- [ ] Start with invalid provider config
- [ ] Start when CEO session spawn fails (budget, provider error, etc)
- [ ] Start with missing ceo_briefing.md (should not fail)
- [ ] Start with corrupted org database
- [ ] Worker-specific start with invalid worker ID
- [ ] Worker-specific start when org not running
