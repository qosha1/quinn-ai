# Worker Spawn Flow Audit

**Date:** 2026-01-23
**Task:** quinnai-rogb - Audit what happens during worker spawn
**Related:** quinnai-tiqb (Epic: Worker onboarding system missing)

## Executive Summary

**Workers spawn with ZERO onboarding context**. They receive no briefing, no docs, no storage guidance, no OKRs, no welcome message. Just a bare claude CLI session.

## Complete Spawn Flow

### 1. User Runs `qn org start`

**File:** `cli/commands/org/start.py:54-131`

```python
org = Org.load(db)
org.start()  # Transitions INITIALIZED → RUNNING

if spawn_ceo:
    _spawn_ceo_session(org.ceo, org_path, provider, command, args)
```

**What happens:**
- Loads Org object from database
- Calls `org.start()` (state transition)
- Calls `_spawn_ceo_session()` for CEO (first worker)

### 2. CEO Session Spawn

**File:** `cli/commands/org/start.py:136-176`

```python
def _spawn_ceo_session(ceo, org_path, provider, command, args_str):
    config = SessionConfig(
        worker_id=ceo.id,
        provider=provider,  # "claude_code"
        command=command,    # "claude"
        args=args,          # ["--dangerously-skip-permissions"]
        working_directory=org_path,  # ~/orgs/my-ai-company
    )

    ceo.spawn(config)
```

**Problem:** `working_directory=org_path`
- Worker spawns in **org root**, not in `workers/{id}/`
- No access to worker-specific context directory
- Shared with all workers (wrong)

### 3. Worker.spawn() Execution

**File:** `cli/core/worker.py:1427-1479`

```python
def spawn(self, config: SessionConfig) -> SessionInterface:
    # Get registry
    registry = self._session_registry or get_default_registry()

    # Create session via registry
    session = registry.create(config.provider, config)

    # Delegate to spawn_session
    self.spawn_session(session)

    return session
```

**What it does:**
1. Gets session registry (maps provider names to implementations)
2. Creates session instance (ClaudeCodeSession for "claude_code")
3. Calls `spawn_session()` for budget/attach/start

### 4. Worker.spawn_session() - Budget & Start

**File:** `cli/core/worker.py:1163-1192`

```python
def spawn_session(self, session: SessionInterface) -> None:
    # Phase 1: Validate (no active session exists)
    self._validate_spawn_preconditions(session)

    # Phase 2: Budget enforcement
    budget_check = self._enforce_spawn_budget(session)

    # Phase 3: Attach and start session
    self._start_session(session)

    # Phase 4: Record spend and persist
    self._finalize_spawn(session, budget_check)
```

**Budget check:**
- Estimates cost: ~$0.20 (default spawn tokens)
- Checks worker has budget
- Raises if insufficient

**No onboarding here** - just budget checks

### 5. Session Start

**File:** `cli/core/worker.py:1260-1279`

```python
def _start_session(self, session: SessionInterface) -> None:
    self.attach_session(session)

    try:
        session.start()  # Spawns the actual process
    except Exception:
        self._session = None
        raise
```

**Calls:** `session.start()` on ClaudeCodeSession

### 6. ClaudeCodeSession._spawn_process()

**File:** `cli/core/sessions/claude_code.py:91-125`

```python
def _spawn_process(self) -> None:
    # Create AgentSession config
    agent_config = AgentSessionConfig.create(
        worker_id=self._config.worker_id,
        provider="claude_code",
        db_path=self._config.transcript_db_path,
        session_name=f"{TMUX_SESSION_PREFIX}{self._config.worker_id}",
        pyterm_config=self._pyterm_config,
    )

    # Create and start agent session
    self._agent_session = AgentSession(agent_config)

    # Start with session config
    session_config = PytermSessionConfig(
        shell=self._config.command,      # "claude"
        args=self._config.args,          # ["--dangerously-skip-permissions"]
        cwd=str(self._config.working_directory),  # org root
        env=self._config.env_vars,       # empty dict
        cols=120,
        rows=40,
    )
    self._agent_session.start(session_config)
```

**What gets passed:**
- `shell`: "claude"
- `args`: ["--dangerously-skip-permissions"]
- `cwd`: `~/orgs/my-ai-company` (org root, not worker dir)
- `env`: {} (empty - no WORKER_ID, no BRIEFING_PATH, nothing)

**No onboarding context whatsoever**

### 7. AgentSession.start() → Tmux Spawn

**File:** `shared/pyterm/agent_session.py` (via TmuxSpawner)

**File:** `cli/core/sessions/tmux_spawner.py:86-160`

```bash
tmux new-session \
  -d \
  -s qn-wrkr-7326dbaf \
  -x 120 \
  -y 40 \
  -c ~/orgs/my-ai-company \
  claude --dangerously-skip-permissions
```

**Result:**
- Tmux session `qn-wrkr-7326dbaf` created
- Working directory: `~/orgs/my-ai-company` (ORG ROOT)
- Command: `claude --dangerously-skip-permissions`
- No environment variables
- No initial message
- No context files
- **Worker is completely blind**

## What's Missing (Onboarding Gaps)

### 1. Worker Context Directory Not Used ❌

**Expected:** `~/orgs/my-ai-company/storage/workers/{worker-id}/`

**Actual:** `~/orgs/my-ai-company/` (org root)

**Impact:**
- Worker has no private workspace
- All workers share same directory
- Violates storage architecture

### 2. No Briefing Delivered ❌

**Code exists:** `cli/core/org.py:268-299` (`_deliver_ceo_briefing`)

**Problem:**
- Only called during `org.start()` for CEO
- Requires `board-channel` (doesn't exist)
- Delivers as message (worker can't see)
- No file copy to worker directory

**Worker never receives:**
- Org mission
- Their role/responsibilities
- What they're supposed to do

### 3. No Architecture Docs ❌

**Missing in worker context:**
- `CLAUDE.md` - Architectural rules ("Code = Physics, Config = Behavior")
- `AGENTS.md` - Worker patterns and examples
- `STORAGE.md` - Where to save work (shared/ vs workers/)

**Workers don't know:**
- How to structure their work
- When to use shared storage
- Beads workflow
- Available tools

### 4. No OKRs Accessible ❌

**Database has:** Template OKRs in `config/initial_okrs.json`

**Worker can't access:**
- No query run on spawn
- No env var pointing to OKRs
- No bd command to view them
- No cascaded objectives

### 5. No Environment Context ❌

**No env vars set:**
```bash
WORKER_ID=wrkr-7326dbaf
ORG_PATH=~/orgs/my-ai-company
BRIEFING_PATH=~/orgs/.../config/ceo_briefing.md
STORAGE_ROOT=~/orgs/.../storage
WORKER_STORAGE=~/orgs/.../storage/workers/wrkr-7326dbaf
```

**Workers have to discover everything manually**

### 6. No Welcome Message ❌

**Expected on spawn:**
```
╔════════════════════════════════════════╗
║   Welcome, CEO!                        ║
╠════════════════════════════════════════╣
║ Organization: My AI Company            ║
║ Role: Chief Executive Officer          ║
║ Mission: [from briefing]               ║
║                                        ║
║ Your onboarding checklist:             ║
║  ☐ Read briefing (cat BRIEFING.md)    ║
║  ☐ Review OKRs (bd list --assignee=me)║
║  ☐ Check team (qn wrkr list)          ║
║  ☐ Learn storage (cat STORAGE.md)     ║
║  ☐ Review rules (cat CLAUDE.md)       ║
╚════════════════════════════════════════╝

Type 'help' for available commands.
```

**Actual:** Just bare claude prompt with no context

### 7. No Onboarding Checklist ❌

**No bead created with:**
- [ ] Read your briefing
- [ ] Review your OKRs
- [ ] Understand storage architecture
- [ ] Check team structure
- [ ] Review CLAUDE.md rules
- [ ] Explore available tools

## Working Directory Problem

**Current:** All workers spawn in **org root** (`~/orgs/my-ai-company/`)

**Should be:** Each worker in `~/orgs/my-ai-company/storage/workers/{worker-id}/`

**Why this matters:**
- Workers need private workspace
- Prevents file conflicts between workers
- Enables worker-specific context files
- Aligns with storage architecture

**Where to fix:** `cli/commands/org/start.py:156-162`

```python
# WRONG:
config = SessionConfig(
    worker_id=ceo.id,
    working_directory=org_path,  # ← All workers share org root
)

# RIGHT:
worker_dir = org_path / "storage" / "workers" / ceo.id
worker_dir.mkdir(parents=True, exist_ok=True)
config = SessionConfig(
    worker_id=ceo.id,
    working_directory=worker_dir,  # ← Each worker gets own dir
)
```

## What SHOULD Happen (Ideal Flow)

### Pre-Spawn Setup

1. **Create worker directory**
   ```bash
   mkdir -p ~/orgs/my-ai-company/storage/workers/{worker-id}/
   cd ~/orgs/my-ai-company/storage/workers/{worker-id}/
   ```

2. **Copy/Link documentation**
   ```bash
   ln -s ../../../../CLAUDE.md CLAUDE.md
   ln -s ../../../../backend/AGENTS.md AGENTS.md
   ```

3. **Create worker briefing**
   ```bash
   # workers/{id}/BRIEFING.md
   # Role: CEO
   # Mission: [from config/ceo_briefing.md or DB]
   # OKRs: [cascaded from board]
   # Team: [reports list]
   ```

4. **Create STORAGE.md guide**
   ```bash
   # Explain: shared/topics/, shared/teams/, workers/{id}/, live/
   ```

5. **Create onboarding checklist**
   ```bash
   bd create --title="Onboarding: {worker.name}" \
     --body="Read BRIEFING.md, Review OKRs..."
   ```

### Spawn with Context

```python
config = SessionConfig(
    worker_id=worker.id,
    provider=provider,
    command=command,
    args=args,
    working_directory=worker_dir,  # Worker-specific dir
    env_vars={
        "WORKER_ID": worker.id,
        "WORKER_ROLE": worker.role,
        "ORG_PATH": str(org_path),
        "WORKER_STORAGE": str(worker_dir),
        "SHARED_STORAGE": str(org_path / "storage" / "shared"),
    },
)
```

### Welcome Message

**Inject into session on start:**
```bash
# Run after session spawns, before worker gets control
cat BRIEFING.md
echo ""
echo "Your onboarding checklist:"
bd list --assignee={worker.id} --status=open
echo ""
echo "Type 'help' for available tools."
```

## Recommended Fixes

### P0 - Critical

1. **Fix working directory** - Workers spawn in `workers/{id}/`, not org root
2. **Create briefing delivery** - Copy briefing to `workers/{id}/BRIEFING.md`
3. **Add env vars** - WORKER_ID, ORG_PATH, WORKER_STORAGE

### P1 - Important

4. **Copy architecture docs** - Symlink CLAUDE.md, AGENTS.md to worker dir
5. **Create STORAGE.md guide** - Explain storage hierarchy
6. **Generate role-specific briefing** - From template + DB data

### P2 - Nice to Have

7. **Welcome message** - Print briefing on spawn
8. **Onboarding checklist bead** - Create first-actions todo
9. **Interactive tour** - "Type 'tour' to learn the system"

## Code Changes Required

### 1. Update `_spawn_ceo_session()` in `cli/commands/org/start.py`

Change working directory from org root to worker directory.

### 2. Add `prepare_worker_onboarding()` in `cli/core/worker.py`

Called before spawn to:
- Create worker directory
- Copy docs
- Create briefing
- Set up env vars

### 3. Update `SessionConfig` to include `onboarding_message`

Optional message to display on spawn.

### 4. Modify tmux_spawner to inject welcome message

Send initial text to session after spawn.

## Testing Plan

1. **Create fresh org**
   ```bash
   rm -rf ~/orgs/test-onboarding
   qn org init ~/orgs/test-onboarding
   qn org start
   ```

2. **Attach to CEO session**
   ```bash
   tmux attach -t qn-wrkr-{ceo-id}
   ```

3. **Verify onboarding**
   - [ ] Working directory is `workers/{id}/`
   - [ ] BRIEFING.md exists and has real content
   - [ ] CLAUDE.md is accessible
   - [ ] AGENTS.md is accessible
   - [ ] STORAGE.md exists
   - [ ] Env vars are set (echo $WORKER_ID)
   - [ ] Welcome message displayed
   - [ ] Onboarding checklist bead exists

## Conclusion

Workers currently spawn **completely blind** with:
- No briefing
- No docs
- No storage guidance
- No OKRs
- No env context
- Wrong working directory

This affects **ALL workers** (CEO, managers, ICs), not just CEO.

The spawn code is there, but **zero onboarding infrastructure exists**.

Next step: Design the onboarding system (quinnai-2ync).
