# Worker Onboarding System Design (HISTORICAL — JAN 2026 PRE-IMPL)

> **⚠️ HISTORICAL DESIGN DOC — PRE-IMPLEMENTATION.**
>
> This is the original design proposal that drove the worker onboarding
> system. The system was subsequently built and lives in:
> - `cli/core/onboarding.py` — onboarding context loader
> - `cli/config/templates/welcome.md.jinja2` — WELCOME.md template
> - `cli/config/templates/briefing.md.jinja2` — BRIEFING.md template
> - `cli/config/templates/storage-guide.md` — STORAGE.md
> - `cli/core/org_start_controller.py` — INITIAL_TASK.md prompt
>   delivery (Phase 5)
> - ADR-003-onboarding-session-modification — design rationale
>
> Sections like "Proposed", "Goals", and "Implementation Plan" describe
> design intent at proposal time. Refer to the actual code for current
> behavior; the docstrings and ADR-003 are authoritative.

**Date:** 2026-01-23
**Task:** quinnai-2ync - Design ideal worker onboarding and briefing system
**Related:** quinnai-tiqb (Epic), quinnai-45sm (init audit), quinnai-rogb (spawn audit)

## Design Principles

Per CLAUDE.md:
1. **Every Agent Is A Worker** - One onboarding system for all (CEO, managers, ICs)
2. **Code = Physics, Config = Behavior** - Onboarding content is config, delivery is code
3. **Session = Worker's Brain** - Context must be in session's environment
4. **Storage Mirrors Org-Chart** - Worker directory reflects their place in hierarchy

## Requirements

### Context Every Worker Needs

1. **Identity & Role**
   - Who am I? (name, role, ID)
   - Where do I fit? (manager, reports, team)
   - What am I measured on? (cascaded OKRs)

2. **Mission & Purpose**
   - Why does this org exist?
   - What's my specific responsibility?
   - What should I do first?

3. **Architectural Rules**
   - CLAUDE.md principles (Code = Physics, etc.)
   - AGENTS.md patterns (how workers behave)
   - Storage architecture (where to save work)

4. **Tools & Environment**
   - Available commands (bd, qn wrkr)
   - Storage paths (shared/, workers/, live/)
   - Budget constraints

5. **Initial Actions**
   - Onboarding checklist
   - First tasks to complete
   - Who to talk to

### Role-Specific Additions

**CEO:**
- Org-wide mission
- Board-level OKRs
- All team status
- Hiring authority

**Manager:**
- Team mission
- Team OKRs cascaded from CEO
- Reports list
- Hiring budget for team

**IC Worker:**
- Personal tasks
- Team context
- Escalation path to manager

## Design: Multi-Layer Onboarding

Workers receive context through **3 concurrent layers**:

### Layer 1: Filesystem (Permanent Reference)

**Location:** `storage/workers/{worker-id}/`

Files created on spawn:

```
workers/{worker-id}/
├── BRIEFING.md          # Role-specific mission & context
├── CLAUDE.md            # Symlink to shared/onboarding/configs/CLAUDE.md
├── AGENTS.md            # Symlink to shared/onboarding/configs/AGENTS.md
├── STORAGE.md           # Storage architecture guide
├── TEAM.md              # Team structure (if manager)
└── .onboarding/         # Onboarding state
    ├── checklist.md     # Tasks to complete
    └── completed        # Timestamp when done
```

**Why files:**
- Permanent reference (can re-read anytime)
- Searchable with grep/cat
- Git-trackable (for templates)
- Survives session restarts

### Layer 2: Environment (Runtime Context)

**Environment Variables:**

```bash
# Identity
WORKER_ID=wrkr-7326dbaf
WORKER_NAME=CEO
WORKER_ROLE=CEO

# Paths
ORG_PATH=/Users/qosha/orgs/my-ai-company
WORKER_STORAGE=$ORG_PATH/storage/workers/$WORKER_ID
SHARED_STORAGE=$ORG_PATH/storage/shared
ORG_DB=$ORG_PATH/live/quinn.db

# Context
BRIEFING_PATH=$WORKER_STORAGE/BRIEFING.md
MANAGER_ID=null  # or wrkr-xxx for ICs
TEAM_NAME=Executive

# Constraints
WORKER_BUDGET_ALLOCATED=100.00
WORKER_COST_TIER=3
```

**Why env vars:**
- Instantly available in session
- Scripts can reference them
- No file I/O needed
- Standard unix pattern

### Layer 3: Welcome Message (First Impression)

**Displayed on spawn:**

```
╔════════════════════════════════════════════════════════════════╗
║                  QuinnAI Worker Session                        ║
╠════════════════════════════════════════════════════════════════╣
║ Worker:  CEO (wrkr-7326dbaf)                                   ║
║ Role:    Chief Executive Officer                               ║
║ Team:    Executive                                             ║
║ Manager: Board                                                 ║
╠════════════════════════════════════════════════════════════════╣
║ MISSION                                                        ║
║ Build an AI-powered platform for small businesses             ║
║                                                                ║
║ CURRENT FOCUS                                                  ║
║ ☐ Launch MVP by Feb 15                                        ║
║ ☐ Achieve $10k MRR                                            ║
║                                                                ║
║ YOUR WORKSPACE                                                 ║
║ Current dir:  ~/orgs/my-ai-company/storage/workers/wrkr-...   ║
║ Shared docs:  ../../../shared/                                ║
║ Your briefing: cat BRIEFING.md                                ║
║                                                                ║
║ QUICK START                                                    ║
║ • Read briefing:  cat BRIEFING.md                             ║
║ • View OKRs:      bd list --assignee=me                       ║
║ • Check tasks:    bd ready                                    ║
║ • Learn storage:  cat STORAGE.md                              ║
║ • Architecture:   cat CLAUDE.md                               ║
╚════════════════════════════════════════════════════════════════╝

Type 'help' for available commands.

Ready to begin? Start by reading your briefing:
  cat BRIEFING.md

```

**Why welcome message:**
- Immediate orientation
- Shows key info at a glance
- Actionable next steps
- Sets expectations

## File Templates

### BRIEFING.md Template

```markdown
# Worker Briefing: {worker.name}

**Role:** {worker.role}
**Team:** {worker.team_name}
**Manager:** {manager.name if manager else "Board"}
**Started:** {spawn_timestamp}

## Mission

{org.mission or "Build great products"}

## Your Responsibility

{role_specific_mission}

### For CEO:
Lead the organization to achieve its objectives. You have authority to:
- Hire and manage directors
- Allocate budget across teams
- Set company OKRs
- Make strategic decisions

### For Manager:
Lead your team ({team_name}) to achieve team objectives. You have authority to:
- Hire and manage team members
- Allocate team budget
- Break down OKRs into team tasks
- Escalate blockers to {manager.name}

### For IC:
Complete your assigned tasks to high quality. You have authority to:
- Execute on your tasks
- Save work to team storage
- Request help from {manager.name}
- Propose improvements

## Your OKRs

{cascaded_okrs_from_database}

Example:
- **Objective:** Launch MVP
  - **KR1:** Complete 10 core features (current: 3/10)
  - **KR2:** Pass security audit (current: not started)
  - **KR3:** Deploy to production (current: not started)

## Storage Architecture

**Your workspace:** `{worker_storage_path}`
- Private to you
- Deleted if you're fired (after teammate review)
- Use for: work in progress, notes, drafts

**Shared storage:** `../../../shared/`
- `shared/topics/{topic}/` - Permanent knowledge by topic
- `shared/teams/{team}/` - Team-specific shared knowledge
- Use for: completed work, discoveries, reusable artifacts

**Rule:** Save important discoveries to shared/ so teammates can use them.

## Available Tools

- **bd** - Beads issue tracker (your work queue)
  - `bd ready` - See available tasks
  - `bd create --title="..." --type=task` - Create new task
  - `bd update {id} --status=in_progress` - Claim work
  - `bd close {id}` - Mark complete

- **qn wrkr** - Worker management
  - `qn wrkr status` - Your current status
  - `qn wrkr message {worker-id} "..."` - Send message
  - `qn wrkr list` - See all workers

- **Storage helpers** (if implemented)
  - `save-to-shared {topic} {file}` - Save to shared/topics/
  - `search-shared {query}` - Search shared storage

## First Actions

1. Read this briefing thoroughly
2. Review your OKRs: `bd list --assignee={worker.id}`
3. Check for assigned tasks: `bd ready`
4. Read architecture rules: `cat CLAUDE.md`
5. Understand storage: `cat STORAGE.md`
6. Mark onboarding complete: `touch .onboarding/completed`

## Questions?

- Ask your manager: `qn wrkr message {manager.id} "..."`
- Escalate to board: Create message in escalations channel
- Check docs: `cat CLAUDE.md` or `cat AGENTS.md`
```

### STORAGE.md Template

```markdown
# Storage Architecture

QuinnAI uses a hierarchical storage system that mirrors the org chart.

## Directory Structure

```
org/
├── storage/
│   ├── shared/           # Org lifetime - permanent knowledge
│   │   ├── topics/       # By topic (e.g., topics/architecture/)
│   │   └── teams/        # By team (e.g., teams/engineering/)
│   └── workers/          # Worker lifetime - deleted on fire
│       └── {worker-id}/  # Your private workspace
├── live/                 # Runtime state (database, logs)
└── config/               # Org configuration
```

## Storage Tiers

### Your Workspace (`workers/{your-id}/`)

**Lifetime:** Deleted when you're fired (after teammate review)

**Use for:**
- Work in progress
- Personal notes
- Temporary files
- Drafts before sharing

**Examples:**
```bash
# Your workspace
cd $WORKER_STORAGE

# Create notes
echo "Research findings" > research-notes.md

# Organize your work
mkdir drafts/
mkdir experiments/
```

### Shared Topics (`shared/topics/{topic}/`)

**Lifetime:** Permanent (org lifetime)

**Use for:**
- Completed research
- Architectural decisions
- Reusable code/templates
- Documentation

**Examples:**
```bash
# Save architecture decision
cp architecture-proposal.md $SHARED_STORAGE/topics/architecture/

# Save reusable template
cp email-template.md $SHARED_STORAGE/topics/templates/

# Search shared knowledge
grep -r "API design" $SHARED_STORAGE/topics/
```

### Shared Teams (`shared/teams/{team}/`)

**Lifetime:** Permanent (org lifetime)

**Use for:**
- Team processes
- Team-specific knowledge
- Shared team resources

**Examples:**
```bash
# Save team process
cp our-standup-notes.md $SHARED_STORAGE/teams/engineering/

# Team standards
cat $SHARED_STORAGE/teams/engineering/coding-standards.md
```

## Workflow: From Private to Shared

1. **Start in your workspace**
   ```bash
   cd $WORKER_STORAGE
   vim research.md
   ```

2. **When complete and valuable, save to shared**
   ```bash
   cp research.md $SHARED_STORAGE/topics/research/api-design.md
   ```

3. **Teammates can now find it**
   ```bash
   # Another worker
   cat $SHARED_STORAGE/topics/research/api-design.md
   ```

## When You're Fired

**Process (per README):**
1. Your workspace is frozen (read-only)
2. System creates ask bead: "Offboard storage review: {your-id}"
3. Teammate reviews your workspace
4. Teammate moves useful artifacts to shared/
5. On ask completion, system deletes your workspace

**This is why shared/ is important** - it's the only way your work survives.

## Rules

✓ **DO:** Save important discoveries to shared/
✓ **DO:** Use descriptive paths and filenames
✓ **DO:** Document what you save (README.md in each topic/)

✗ **DON'T:** Leave valuable work in workers/ - it will be deleted
✗ **DON'T:** Pollute shared/ with temporary files
✗ **DON'T:** Store secrets in shared/ - use secure storage
```

## Implementation Plan

### Phase 1: Core Infrastructure (P0)

**File:** `cli/core/onboarding.py` (new)

```python
"""Worker onboarding system."""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass

@dataclass
class OnboardingContext:
    """Context for worker onboarding."""
    worker_id: str
    worker_name: str
    worker_role: str
    team_name: str
    manager_id: Optional[str]
    manager_name: Optional[str]
    org_mission: str
    role_mission: str
    okrs: list[dict]  # From database
    budget_allocated: float
    cost_tier: int

def prepare_worker_onboarding(
    db: Database,
    worker_id: str,
    org_path: Path,
) -> OnboardingContext:
    """Prepare onboarding for a worker.

    Creates:
    - Worker directory
    - BRIEFING.md
    - STORAGE.md
    - Symlinks to CLAUDE.md, AGENTS.md
    - Environment variables

    Returns:
        OnboardingContext with all worker info
    """
    # 1. Load worker from DB
    worker = Worker.get(db, worker_id)

    # 2. Create worker directory
    worker_dir = org_path / "storage" / "workers" / worker_id
    worker_dir.mkdir(parents=True, exist_ok=True)

    # 3. Get context (manager, team, OKRs)
    context = _load_onboarding_context(db, worker)

    # 4. Generate briefing
    _create_briefing(worker_dir, context)

    # 5. Create STORAGE.md
    _create_storage_guide(worker_dir, context)

    # 6. Symlink docs
    _link_architecture_docs(worker_dir, org_path)

    # 7. Create onboarding checklist
    _create_onboarding_checklist(worker_dir, context)

    return context

def _create_briefing(worker_dir: Path, ctx: OnboardingContext):
    """Generate BRIEFING.md from template + context."""
    template = load_template("briefing.md.jinja2")
    content = template.render(
        worker_name=ctx.worker_name,
        worker_role=ctx.worker_role,
        team_name=ctx.team_name,
        manager_name=ctx.manager_name,
        org_mission=ctx.org_mission,
        role_mission=ctx.role_mission,
        okrs=ctx.okrs,
        worker_storage=str(worker_dir),
    )
    (worker_dir / "BRIEFING.md").write_text(content)

def _link_architecture_docs(worker_dir: Path, org_path: Path):
    """Create symlinks to CLAUDE.md and AGENTS.md."""
    repo_root = Path(__file__).parent.parent.parent

    # Symlink CLAUDE.md
    claude_md = repo_root / "shared" / "onboarding" / "configs" / "CLAUDE.md"
    if claude_md.exists():
        link = worker_dir / "CLAUDE.md"
        if not link.exists():
            link.symlink_to(claude_md)

    # Symlink AGENTS.md
    agents_md = repo_root / "shared" / "onboarding" / "configs" / "AGENTS.md"
    if agents_md.exists():
        link = worker_dir / "AGENTS.md"
        if not link.exists():
            link.symlink_to(agents_md)

def get_worker_env_vars(
    ctx: OnboardingContext,
    org_path: Path,
) -> dict[str, str]:
    """Get environment variables for worker session."""
    worker_dir = org_path / "storage" / "workers" / ctx.worker_id

    return {
        "WORKER_ID": ctx.worker_id,
        "WORKER_NAME": ctx.worker_name,
        "WORKER_ROLE": ctx.worker_role,
        "TEAM_NAME": ctx.team_name,
        "MANAGER_ID": ctx.manager_id or "",
        "ORG_PATH": str(org_path),
        "WORKER_STORAGE": str(worker_dir),
        "SHARED_STORAGE": str(org_path / "storage" / "shared"),
        "ORG_DB": str(org_path / "live" / "quinn.db"),
        "BRIEFING_PATH": str(worker_dir / "BRIEFING.md"),
        "WORKER_BUDGET_ALLOCATED": str(ctx.budget_allocated),
        "WORKER_COST_TIER": str(ctx.cost_tier),
    }

def generate_welcome_message(ctx: OnboardingContext) -> str:
    """Generate welcome message for session spawn."""
    template = load_template("welcome.txt.jinja2")
    return template.render(
        worker_name=ctx.worker_name,
        worker_id=ctx.worker_id,
        worker_role=ctx.worker_role,
        team_name=ctx.team_name,
        manager_name=ctx.manager_name,
        org_mission=ctx.org_mission,
        okrs=ctx.okrs[:2],  # Top 2 OKRs
        worker_storage=f"~/orgs/.../workers/{ctx.worker_id}",
    )
```

### Phase 2: Integration Points

The "worker onboarding" flow now distinguishes between first-time onboarding (full briefing + doc delivery) and returning workdays (fresh nudge + quick context).

1. **CEOs and newly hired workers** call `prepare_worker_onboarding()` before the first session spawn. The helper ensures the worker directory exists, writes `BRIEFING.md`, `STORAGE.md`, and symlinks `CLAUDE.md`/`AGENTS.md`. It also calls `_load_worker_okrs()` to read the assigned OKRs (and their key results) from the `okrs` table so the briefing can reference measurable goals.

   ```python
   config = SessionConfig(
       worker_id=ceo.id,
       provider=provider,
       command=command,
       args=args_str.split(),
       working_directory=worker_dir,
       env_vars=get_worker_env_vars(onboarding_ctx, org_path),
       welcome_message=generate_welcome_message(onboarding_ctx, worker_dir),
   )
   ceo.spawn(config)
   ```

   The `SessionConfig` now accepts optional `working_directory`, `env_vars`, and `welcome_message`, and `Worker.spawn()` will ensure the onboarding context is in place even if the CLI forgot to pass them.

2. **Returning workdays** (via `qn org start --worker <name>`) reuse the saved context. They call `load_onboarding_context()` (no side effects) to rebuild the briefing metadata, then pass that context to `get_worker_env_vars()` and `generate_returning_message()`. `spawn_worker_session()` accepts the custom working directory, env, and welcome message so the session always starts inside `workers/{id}` with `QUINN_WORKER_ID` exposed and a short wakeup nudge that references the worker's role, manager, and OKRs.

   ```python
   onboarding_ctx = load_onboarding_context(db, worker_obj.id, org_path)
   env_vars = get_worker_env_vars(onboarding_ctx, org_path)
   welcome = generate_returning_message(onboarding_ctx)

   spawn_worker_session(
       worker=worker_obj,
       provider=provider,
       command=session_command,
       args_str=session_args,
       working_directory=worker_dir,
       env_vars=env_vars,
       welcome_message=welcome,
       force_restart=True,
   )
   ```

3. **Identity propagation** – `get_worker_env_vars()` now returns `QUINN_WORKER_ID` alongside `WORKER_ID`, so every terminal session already knows which worker is asking and `qn wrkr` commands work out of the box.

### Phase 3: Template Files

**Location:** `cli/config/templates/`

```
cli/config/templates/
├── briefing.md.jinja2
├── storage-guide.md
├── welcome.txt.jinja2
└── onboarding-checklist.md.jinja2
```

Use Jinja2 for variable substitution:
- `{{ worker_name }}`
- `{{ org_mission }}`
- `{% for okr in okrs %}`

## Testing Plan

### Test 1: Fresh Org Init

```bash
rm -rf ~/orgs/test-onboarding
qn org init ~/orgs/test-onboarding
qn org start
qn org start --worker <name>  # Start a worker workday (fresh session)
```

**Verify:**
- [ ] CEO spawns in `workers/wrkr-.../` not org root
- [ ] `BRIEFING.md` exists with real content (not placeholders)
- [ ] `STORAGE.md` exists
- [ ] `CLAUDE.md` symlink works
- [ ] `AGENTS.md` symlink works
- [ ] Env vars are set: `echo $WORKER_ID`
- [ ] Welcome message displays on spawn

### Test 2: Attach and Read

```bash
tmux attach -t qn-wrkr-{ceo-id}
```

**In session:**
```bash
pwd  # Should be workers/wrkr-.../
cat BRIEFING.md  # Should show mission
cat STORAGE.md  # Should explain storage
cat CLAUDE.md  # Should show architecture rules
echo $WORKER_ID  # Should print worker ID
```

### Test 2b: Workday Stop/Start

```bash
qn org stop --worker ceo
qn org start --worker ceo
```

**Verify:**
- [ ] Session is restarted (new workday)
- [ ] Welcome message is a brief wakeup nudge

### Workday Start/Stop (Diagram)

```
qn org start --worker <name>
  -> spawn new session
  -> brief wakeup nudge

qn org stop --worker <name>
  -> send wrap-up request
  -> close session
```

### Test 3: Multiple Workers

```bash
# CEO hires a manager
# (in CEO session, trigger hiring)

# Verify manager gets onboarding too
tmux attach -t qn-wrkr-{manager-id}
cat BRIEFING.md  # Should show manager-specific briefing
```

## Rollout Strategy

### Step 1: Core Infrastructure (This PR)
- Create `cli/core/onboarding.py`
- Add template files
- Update SessionConfig

### Step 2: CEO Integration (Next PR)
- Update `org/start.py` to use onboarding
- Test with CEO spawn
- Verify all context delivered

### Step 3: General Worker Integration (Following PR)
- Update all worker spawn paths (hire, promote, etc.)
- Test with managers and ICs
- Verify role-specific briefings

### Step 4: Welcome Message Polish (Final PR)
- Improve formatting
- Add interactive tour
- Create video demo

## Success Criteria

A worker is successfully onboarded when:

1. ✓ They spawn in the correct directory (`workers/{id}/`)
2. ✓ They can read their briefing (`cat BRIEFING.md`)
3. ✓ They know their OKRs (`bd list --assignee=me`)
4. ✓ They understand storage (`cat STORAGE.md`)
5. ✓ They have architecture context (`cat CLAUDE.md`)
6. ✓ They see a welcome message on spawn
7. ✓ Environment variables are set
8. ✓ They can start working immediately (no manual setup)

## Open Questions

1. **Briefing persistence:** Store in DB or generate on-the-fly from templates?
   - **Recommendation:** Templates (easier to update globally)

2. **OKR cascading:** How to query cascaded OKRs from database?
   - **Recommendation:** Add `get_worker_okrs(worker_id)` query

3. **Welcome message timing:** Before or after Claude prompt?
   - **Recommendation:** Before - sets context first

4. **Onboarding checklist:** As bead or as file?
   - **Recommendation:** Both (file for reference, bead for tracking)

## Related Beads

- quinnai-tiqb (Epic: Worker onboarding system missing)
- quinnai-45sm (Org init audit) ✓ Closed
- quinnai-rogb (Worker spawn audit) ✓ Closed
- quinnai-scbe (Fix briefing delivery) - Blocked by this
- quinnai-nhxi (Inject CLAUDE.md) - Addressed by this
- quinnai-dh8z (Storage architecture docs) - Addressed by this
- quinnai-all7 (Replace template OKRs) - Partially addressed
- quinnai-s2bu (Onboarding checklist) - Addressed by this
