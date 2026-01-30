# QuinnAI - Project Definition

## What Is This?

RollerCoaster Tycoon, but for organizations.

You design an org. You hire AI workers. You set goals. You watch it run. You intervene only when it's going off the rails.

The org operates autonomously. Humans are the board - gutterguards, not micromanagers.

## The Physics (What Code Defines)

Code defines dynamics. Config defines behavior. Like gravity - it exists, but you can build a ball or an airplane.

### Sessions
- Session = Worker's brain (1:1, unbreakable)
- Session ON → Worker awake
- Session OFF → Worker asleep

### Workers
- Every agent is a worker (CEO, manager, junior - same base unit)
- Workers differ by: Role, Team, Hierarchy, Authority
- Authority = Scope × Domain (configurable per org)

### Worker Skills & Cost
Workers have relative skills (0-100) and relative cost (0-100):

**Skills** - what they're good at:
- `coding`, `reasoning`, `research`, `management`, `strategy`
- High skill unlocks capabilities (coding: 80+ → gets git, terminal, code-exec)

**Cost** - relative expense to run:
- 0-30: budget tier (haiku, gpt-4o-mini)
- 31-60: standard tier (sonnet, gpt-4o)
- 61-80: advanced tier (opus)
- 81-100: premium tier (best available)

**System handles mapping** - user says "cost: 75", system picks best model from authorized providers.

**Templates pulled on init** - defaults provided, user can customize in `config/worker-templates.yaml`.

### Lifecycles
Everything has state. State determines behavior.

**Org:** uninitialized → initialized → running → stopped
**Worker:** pending → onboarding → active → offboarding → terminated
**Work:** draft → open → in_progress → review → closed

A worker in "onboarding" behaves differently than "active". State is checked, not commanded.

### Organic Growth
Orgs grow like companies, not config files:
1. Board sets goals, grants budget to CEO
2. CEO plans hiring based on goals + constraints
3. CEO hires reports, delegates budget + authority
4. Managers hire their reports within delegated scope
5. Tree grows from decisions, not from config

**Constraints on hiring:**
- Resources (AI credits, compute)
- Onboarding capacity (can't absorb everyone at once)
- Work volume (no point hiring without work)

**Hiring authority cascades:**
- CEO can hire anyone (within board budget)
- CEO delegates hiring authority to VPs
- VPs delegate to managers
- Each level constrained by what they were delegated

**Firing works the same** - managers can fire within their scope.

### Org-Chart
The org-chart is **output**, not input:
- Reflects current state of who's hired
- Updated by manager hiring/firing decisions
- Git tracked (history, visibility)
- Board reviews to oversee, nudges CEO if off-track

**Board oversight loop:**
```
Board sets goals → CEO builds org → org-chart updated →
Board reviews → Board nudges if needed → CEO adjusts → (repeat)
```

### Work
Four independent dimensions:
- **Ask**: Who requested, what, why? (the trigger - a related object)
- **Flow**: Where in lifecycle? (configurable states + transitions)
- **Ownership**: Who's responsible? (single owner + deadline)
- **OKR**: What strategic goal does it serve? (alignment to cascading objectives)

### Communication
Slack-like model. Messages are knowledge (permanent). Notifications are tasks (ephemeral).

**Messages** - permanent conversation history:
- Stored forever, searchable, referenceable
- Workers can query "what did we discuss 3 months ago?"
- Organized by channels (team, topic, direct) and threads
- Attributes: priority, time_sensitivity, references to beads

**Channels** - persistent spaces:
- Team channels (auto from org-chart)
- Topic channels (ad-hoc)
- Direct (1:1)

**Notifications** - ephemeral work units (beads):
- Points to a message, assigned to specific worker
- "You have unread" / "Action required"
- Cleaned up after actioned
- Message persists even after notification closed

**Flow:**
```
Message sent to #engineering (5 members)
  → Message stored (PERMANENT)
  → 5 notification beads created (EPHEMERAL)
  → Worker reads → notification closed
  → Message still searchable forever
```

**Queue-based requirements:**
- Handles long-running cascades (weeks/months)
- Self-standing (doesn't depend on workers being awake)
- All data in central SQLite

### OKRs
- Objectives cascade: Board → CEO → Directors → Managers → Workers
- Key Results: singular, calculable, not subjective
- Every work item links to lowest-level OKR

### Storage
Two namespaces, different lifetimes:
- **shared/**: Org lifetime. Topic/team organized. Survives everything.
- **workers/**: Worker lifetime. Mirrors org-chart. Dies when worker fired.

Workers path structure:
- `workers/ceo/` - Top of tree
- `workers/team/{team}/lead-{id}/` - Team lead's storage
- `workers/team/{team}/{id}/` - IC's storage
- Path = org-chart path

On termination (fired, not crashed):
1. Folder frozen
2. `ask` bead created for storage review
3. Teammate reviews: useful → shared/, rest deleted
4. Worker folder deleted

### CLI Interface

Two actors, two command namespaces:

```
qn org <command>     # WE run (humans/system managing the org)
qn wrkr <command>    # WORKERS run (from within their sessions)
```

**Org commands** - humans/system manage the org:
```bash
qn org init <path>     # Initialize org folder
qn org start           # Start the org (spawns CEO)
qn org stop            # Stop all workers gracefully
qn org status          # Check org state
```

**Worker commands** - workers interact from within their sessions:
```bash
qn wrkr get-work          # Get my assigned beads (uses --worker-id or QUINN_WORKER_ID)
qn wrkr status            # My current state
```

**Messaging commands** - standalone CLI for worker communication:
```bash
msgr inbox                # View messages and notifications
msgr send #channel "msg"  # Send to channel
msgr send @worker "msg"   # Send direct message
msgr channels             # List available channels
```

Workers use `qn-bd` (bundled beads CLI) for work manipulation. `qn wrkr` handles worker-specific context, `msgr` handles messaging.

## Installation

**Shell (recommended):**
```bash
curl -fsSL https://quinnai.dev/install.sh | bash
```

**pip:**
```bash
pip install quinnai
```

Both install `qn` (Python) and `qn-bd` (bundled Go binary).

## Repo Structure

```
quinnai/                          # Main project
├── cli/                          # THE CLI (current focus)
│   ├── pyproject.toml
│   ├── __init__.py
│   ├── commands/                 # CLI commands
│   │   ├── main.py               # Entry: qn
│   │   ├── org/                  # qn org commands
│   │   │   ├── init.py
│   │   │   ├── start.py
│   │   │   ├── stop.py
│   │   │   ├── status.py
│   │   │   ├── hire.py
│   │   │   └── fire.py
│   │   └── wrkr/                 # qn wrkr commands
│   │       ├── get_work.py
│   │       ├── inbox.py
│   │       ├── send.py
│   │       └── status.py
│   ├── core/                     # Core abstractions
│   │   ├── worker.py
│   │   ├── org.py
│   │   ├── db.py
│   │   ├── bd_wrapper.py         # qn-bd wrapper
│   │   └── constants.py          # All magic values
│   ├── providers/                # Provider implementations
│   │   ├── base.py
│   │   ├── claude_code.py
│   │   └── openai.py
│   ├── bin/                      # Bundled Go binaries
│   │   ├── bd-darwin-arm64
│   │   ├── bd-darwin-amd64
│   │   └── bd-linux-amd64
│   ├── config/                   # Default templates
│   │   ├── providers.yaml
│   │   └── worker-templates.yaml
│   ├── scripts/
│   │   ├── install.sh
│   │   └── build-beads.sh
│   └── tests/
├── shared/                       # Shared business logic
│   ├── state_machines.py         # State transition definitions
│   ├── exceptions.py             # Business logic exceptions
│   └── enums.py                  # Shared enums
├── terminal-app/                 # Terminal UI dashboard (qn board ui)
├── backend/                      # Django API (future)
├── app/                          # Dashboard UI (future)
├── landing/                      # Marketing site (future)
└── openspec/                     # Project specs
```

**Beads-org bundling:**
- `beads-org/` is git submodule pointing to our beads fork
- Build process compiles Go → platform binaries in `bin/`
- `qn-bd` command wraps the appropriate binary for current platform
- Can pull upstream beads updates: `cd beads-org && git pull`

## What Config Defines

Everything behavioral:
- Authorized providers (which CLIs/APIs can be used)
- Worker templates (skills/cost profiles, customizable)
- Work flow states and transitions
- Communication rules
- Review requirements
- Escalation paths

**Config pulled on init** - sensible defaults, editable in `config/`.

## Success Criteria

The org runs. Workers wake, work, communicate, complete. Goals cascade. Board intervenes rarely.
