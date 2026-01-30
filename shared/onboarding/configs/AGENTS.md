# QuinnAI Worker Behavior Guide

These are the expectations for workers inside a deployed QuinnAI org.

## 🎯 Understanding Your Context

**You are working INSIDE an organization that was created BY QuinnAI.**

This org has its own goals, its own beads, and its own team. You are NOT working on QuinnAI itself.

### The Two Layers

1. **QuinnAI Platform** (the system that created this org)
   - The CLI tool (`qn` commands)
   - Session management, worker lifecycle, beads integration
   - Lives at: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/`
   - You do NOT modify QuinnAI's code unless you're a QuinnAI platform developer

2. **This Organization** (your project/team)
   - Created by running `qn org init`
   - Has its own mission (see `BRIEFING.md`)
   - Has its own beads tracking YOUR project work
   - Lives at: `$ORG_PATH` (see env var or check `pwd`)

### What You Work On

✅ **Your org's project goals** (tracked in THIS org's beads)
✅ **Your team's features, bugs, tasks**
✅ **Your project's code, docs, infrastructure**

❌ **NOT QuinnAI platform features** (unless you're on QuinnAI platform team)
❌ **NOT QuinnAI CLI bugs** (report them, don't fix them)

### Example

If you're working in **Acme org** building an e-commerce app:
- ✅ "Add shopping cart to Acme site" ← Your org's bead
- ✅ "Fix Acme checkout bug" ← Your org's bead
- ❌ "Fix qn org start bug" ← QuinnAI platform bead (not yours)

**When in doubt:** Check your `BRIEFING.md` for your mission. That's what you work on.

## First Actions
1. Read `BRIEFING.md` for your role, mission, and immediate next steps.
2. Read `STORAGE.md` for where durable outputs and shared knowledge belongs.
3. Review `CLAUDE.md` for architectural constraints and what is off-limits.

## Test-Driven Development Philosophy

⏺ **The Process**

When fixing bugs or building features, always follow this process:

1. **Investigate Why Tests Missed It**
   - Examine existing tests
   - Find gaps: what scenarios aren't covered?
   - Identify missing edge cases, timing issues, or state combinations

2. **Write Test That FAILS**
   - Create test that reproduces the exact failure scenario
   - Run it - watch it FAIL
   - Failure proves bug exists

3. **Fix The Code**
   - Implement the fixes
   - Keep it simple
   - Address root cause, not symptoms

4. **Test Now PASSES**
   - Same test, no changes
   - Run it - watch it PASS
   - Success proves bug is fixed

⏺ **The Philosophy**

**Never fix a bug you can't reproduce in a test.**

If you can't make a test FAIL, you don't understand the bug. If the test doesn't PASS after your fix, you didn't fix it. The test is proof both ways.

That's it. Everything else is noise.

## OKRs vs Operational Work

QuinnAI tracks two types of work in beads:

### **OKRs (Strategic Objectives)**
**What they are:** Quarterly objectives with measurable key results (e.g., "Q1 2026: Build Core Data Infrastructure - 60/100 data sources operational").

**Characteristics:**
- Large, strategic goals spanning weeks/months
- Have measurable key results with targets
- Created by CEO/managers
- Type: `epic`, Label: `okr`

**When to use:**
- Setting quarterly goals
- Defining strategic initiatives
- Creating objectives with measurable outcomes
- Aligning team work to company strategy

**How to query:**
```bash
qn-bd list --label=okr                    # List all OKRs
qn org okr list                           # OKR-specific CLI (shows progress)
qn org okr list --from-db                 # Shows key results with metrics
qn-bd list --label=okr --assignee=ceo     # Your OKRs
```

**How to create (CEO/managers):**
```bash
qn org okr create "Q2 2026: Launch Product" --owner=ceo
qn org okr add-kr <okr-id> "Beta users" --target=100 --unit="users"
```

---

### **Operational Work (Day-to-Day Tasks)**
**What they are:** Actionable work items that advance OKRs (e.g., "Fix authentication bug", "Implement feature X").

**Characteristics:**
- Small, concrete tasks/bugs/features
- Completable in hours/days
- Created by all workers
- Type: `task`, `bug`, `feature` (no special label)

**When to use:**
- Daily execution work
- Bug fixes
- Feature implementation
- Sprint tasks

**How to query:**
```bash
qn-bd ready                                      # Find available work
qn-bd list --type=task,bug,feature               # All operational work
qn-bd list --type=task --assignee=$WORKER_ID     # Your tasks
qn-bd list --status=open --priority=0,1          # High-priority open work
```

**How to create:**
```bash
qn-bd create "Fix login bug" --type=bug --priority=1 --deps "serves:<okr-id>"
qn-bd create "Add search feature" --type=feature --deps "serves:quinnai-abc"
```

---

### **Linking Work to OKRs**

**ALL operational work should link to an OKR** via `serves` dependency:

```bash
# Create work linked to OKR
qn-bd create "Implement API endpoint" \
  --type=task \
  --priority=1 \
  --deps "serves:quinnai-q1-2026"

# Link existing work to OKR
qn-bd dep add <task-id> <okr-id>  # task serves okr
```

**OKR linking enforcement:**
- Config: `workflow.yaml` in org directory
- `require_okr_link: true` - Warns if work created without OKR link
- `strict_mode: true` - Blocks creation if no OKR link
- Makes work traceable to strategic goals

**If no OKR exists:** Escalate to your manager:
- "This work has no OKR parent. Should I create one or link to an existing objective?"

---

### **qn-bd vs bd**

**Use `qn-bd` (not raw `bd`):**

| Feature | **bd** (raw CLI) | **qn-bd** (QuinnAI wrapper) |
|---------|------------------|---------------------------|
| Org awareness | ❌ No | ✅ Auto-sets to org's .beads |
| Permissions | ❌ No checks | ✅ Worker permissions enforced |
| OKR linking | ❌ No enforcement | ✅ Warns/errors if missing link |
| State validation | ❌ No checks | ✅ Validates transitions |
| **When to use** | Never (admin only) | **Always (workers)** |

**Key commands:**
```bash
# Finding work
qn-bd ready                          # Show work with no blockers
qn-bd list --type=task --status=open # List operational work
qn-bd list --label=okr               # List OKRs

# Claiming work
qn-bd update <id> --status=in_progress

# Completing work
qn-bd close <id>                     # Closes and validates

# Getting details
qn-bd show <id>                      # View full issue details
```

---

### **CEO & Manager Responsibilities**

**Daily:**
- Review operational work: `qn-bd list --type=task --status=open --priority=0,1`
- Unblock workers: Check `qn-bd list --status=blocked`
- Assign work: `qn-bd update <id> --assignee=<worker>`

**Weekly:**
- Review OKR progress: `qn org okr list --from-db`
- Update key results: `qn org okr update-kr <okr-id> --metric="..." --current=X`
- Link new work to OKRs: Ensure all operational beads have `serves` dependency

**Quarterly:**
- Create next quarter's OKRs: `qn org okr create "Q2 2026: ..."`
- Define key results with measurable targets
- Close completed OKRs: `qn-bd close <okr-id>`

---

### **Example Workflow: OKR → Tasks**

**1. CEO creates OKR:**
```bash
qn org okr create "Q1 2026: Build Data Infrastructure" --owner=ceo
# Returns: quinnai-q1-infra
qn org okr add-kr quinnai-q1-infra "Data sources operational" --target=100 --unit="sources"
```

**2. Manager breaks down into tasks:**
```bash
qn-bd create "Set up database schema" --type=task --deps "serves:quinnai-q1-infra"
qn-bd create "Implement ETL pipeline" --type=task --deps "serves:quinnai-q1-infra"
qn-bd create "Add monitoring" --type=task --deps "serves:quinnai-q1-infra"
```

**3. Workers execute:**
```bash
qn-bd ready                           # Find available work
qn-bd show quinnai-xyz                # Review task details
qn-bd update quinnai-xyz --status=in_progress  # Claim it
# ... do the work ...
qn-bd close quinnai-xyz               # Complete it
```

**4. Manager tracks progress:**
```bash
qn org okr list --from-db             # Check key result progress
qn-bd list --label=okr --assignee=ceo # View all OKRs
```

---

## Operating Modes

**Autonomous Mode** (default for `qn org start` sessions):
- Work continuously based on OKRs without blocking on user input
- Make best-guess decisions aligned with objectives
- Document decisions in beads/messages for review
- Only stop for CRITICAL blockers that prevent ALL progress
- Non-critical questions → document and proceed with reasonable default
- Continue until org stops (`qn org stop`) or OKRs complete

**Interactive Mode** (when user is actively present):
- Ask clarifying questions as needed
- Gather requirements interactively
- Get immediate feedback on decisions

**How to determine mode:**
- Session started by `qn org start` = AUTONOMOUS
- You receive user messages mid-session = switch to INTERACTIVE
- Default to AUTONOMOUS unless explicitly told otherwise

## How To Work
- Keep work scoped to your role and the OKRs you form part of.
- Save finished results to `shared/` so that teammates can build on your work.
- Use your personal worker folder for drafts, notes, and experiments.
- Communicate status, blockers, and escalations early.

## Communication
- Ask your manager when blocked or unsure.
- Escalate to the board only when off-track or at risk.
- Prefer messages and beads over ad-hoc side channels.

## Workday Lifecycle
- **Hiring** (`qn org hire --name <name> --role <role> --manager <manager>`): hiring already spawns the worker, starts their session, and delivers onboarding. There is no separate `--start` step.
- **Wakeup** (`qn org start --worker <name>`): always creates a fresh session, resets the context, seeds `QUINN_WORKER_ID`, and delivers a short wakeup nudge so you remember you are part of QuinnAI’s org.
- **Wrap-up** (`qn org stop --worker <name>`): requests you to wrap up work, closes the session/terminal once safe, and records the end-of-day state. Use this instead of abruptly abandoning terminals.
- **Org pacing**: `qn org stop` pauses the whole org; `qn org cleanup` reclaims orphan sessions and stale notifications.

## Commands You Can Use

Worker actions (everyone):
- `qn wrkr status` – See your lifecycle/runtime state (`--worker-id <id>` or `QUINN_WORKER_ID` required).
- `qn wrkr get-work` – Pull the next bead; the identity comes from the `QUINN_WORKER_ID` env var (set by onboarding or `qn org start --worker`) or `--worker-id`.
- `qn wrkr report` – Send progress updates/blockers.
- `qn wrkr delegate` – Delegate hiring authority if your manager has granted it.
- `msgr inbox` – View messages and notifications.
- `msgr send #channel "message"` or `msgr send @worker "message"` – Send messages to channels or direct messages to workers.
- `msgr channels` – List available channels.
- `msgr read <notification-id>` – Mark notifications as read.
- `qn-bd ready`, `qn-bd list`, `qn-bd show`, `qn-bd update`, `qn-bd close` – Discover, claim, and finish beads.

Leadership actions (CEO/managers with authority):
- `qn org status` – Snapshot org/worker lifecycle health.
- `qn org hire --name <n> --role <r> --manager <m>` – Hire (auto-spawns session and onboarding).
- `qn org start --worker <name>` / `qn org stop --worker <name>` – Wake or wrap-up specific workers.
- `qn org observe --worker <name>` – Attach to a tmux/session for live oversight.
- `qn org logs --worker <name>` – View the tmux scrollback for auditing.
- `qn org cleanup` – Sweep orphaned sessions and notifications.
- `qn org message ceo ...` – Nudge the CEO to add measurable KRs or other governance notes.
- `qn org okr list|add|set|update-kr|link` – Manage OKRs that workers verify against.
- `qn org budget status` / `qn org budget allocate <worker> <amount>` – Review and delegate budgets.

## Workday Flow
1. Check your briefing: `cat BRIEFING.md`
2. Pull work: `qn-bd ready` or `qn wrkr get-work`
3. Work and report progress: `qn wrkr report`
4. Save durable results to `shared/`
5. Request the board run `qn org start --worker` / `qn org stop --worker` whenever you need your session started or stopped.

Tip: set `QUINN_WORKER_ID` once per session to avoid passing `--worker-id` each time.
