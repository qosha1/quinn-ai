# QuinnAI

**RollerCoaster Tycoon, but for organizations.**

Design an org. Hire AI workers. Set goals. Watch it run. Intervene only when it's going off the rails.

## The Idea

You know how in RollerCoaster Tycoon you design a park, hire staff, set prices, and then watch guests walk around having fun (or vomiting)?

QuinnAI is that, but for AI organizations:

1. **Design your org** - Define teams, roles, hierarchy, authority levels
2. **Hire workers** - Spin up AI agents with specific roles and capabilities
3. **Set goals** - Define OKRs that cascade from board level down to individual workers
4. **Watch it run** - The org operates autonomously, workers communicate, work flows
5. **Be the board** - Intervene only when needed, like gutterguards in bowling

## Core Concepts

### Sessions = Brains
Every worker has exactly one session. Session ON = worker awake. Session OFF = asleep. This is unbreakable.

### Workers = Everyone
CEO is a worker. Manager is a worker. Junior dev is a worker. Same base unit, different role/team/authority.

### Work = Four Dimensions
- **Ask**: Who requested this, what did they request, why? (the trigger)
- **Flow**: Where is it in lifecycle?
- **Ownership**: Who's responsible right now?
- **OKR**: What strategic goal does it serve? (alignment)

### OKRs = Cascading Goals
```
Board: "Establish market presence"
  └── CEO: "Create base strategy"
        └── Product Director: "Design 3-month roadmap"
              └── PM: "Define feature specs for Q1"
                    └── [work items link here]
```

### Board = Gutterguards
The ball keeps rolling. You only bump it back when it's heading for the gutter.

## How It Should Feel

### 1. Define Your Org

One folder = one org. Config separate from live state:

```
~/orgs/my-startup/
├── .git/                   # Org-wide version control
├── org-chart/              # STATIC CONFIG (version controlled)
│   ├── structure.yaml      # Hierarchy, teams - human editable
│   ├── roles/              # Role definitions
│   └── teams/              # Team definitions
├── okrs/                   # GOALS (beads-powered, git-tracked)
│   └── .beads/             # SQLite-based OKR tracking
├── live/                   # RUNTIME STATE
│   ├── org.db              # SQLite - queryable from anywhere in org
│   └── workers/            # Per-worker state
│       ├── ceo/
│       ├── eng-lead/
│       └── dev-1/
└── storage/                # ABSTRACTED STORAGE
    ├── permanent/          # Outlives workers (company knowledge)
    └── temporary/          # Worker lifetime (not just session)
```

**Config flow:** YAML → SQLite (YAML inits/overrides, SQLite is source of truth, checks for updates)

**OKRs:** Use [beads](https://github.com/steveyegge/beads) for tracking. Git for version control. Queryable from anywhere.

**Storage abstraction:**
- **Permanent**: Survives worker death. Company knowledge. Like shared Google Drive.
- **Temporary**: Lives as long as worker lives (across sessions). Dies when worker is removed.

### 2. Start the Org

Workers wake based on org-chart. State lives in SQLite. OKRs drive priorities via beads.

### 3. Be the Board

Query OKRs from anywhere. Watch progress. Intervene when off-track.

---

## What Needs Building

### Decided
- **State persistence**: SQLite (queryable from anywhere in org)
- **Config format**: YAML inits/overrides → SQLite is source of truth
- **OKR tracking**: beads + git
- **Storage model**: Permanent (outlives workers) vs Temporary (worker lifetime)

### Beads Extensions (in beads-fork)

We're extending beads to support org-aware work tracking:

**New bead types:**
- `ask` - The request (who, what, why) that spawns work
- `okr` - Objectives and key results (hierarchical)

**New dependency types:**
- `spawned-from` - Work → Ask
- `serves` - Work → OKR

**Lifecycle states (nested in status):**
```
status: in_progress
  └── lifecycle-state: investigation → planning → requirements → implementation → review

status: closed
  └── lifecycle-state: done | rejected | abandoned
```
- Configurable per org (states, transitions, terminal states)
- Enforced: can't close without reaching terminal state
- Actionable errors: "Cannot close: in 'review' state. Complete review first."

**Team ownership & permissions:**
```
teams (id, name, parent_team_id)
team_members (team_id, worker_id, role)
permissions (issue_id, grantee_type, grantee_id, level)
```
- Levels: none → read → comment → write → approve → admin
- Enforced: marketing can't modify engineering beads
- Inherited from org-chart hierarchy

### Still figuring out
- **Installation**: How does QuinnAI get on your machine?
- **Worker runtime**: What runs when a worker "wakes up"? Process? Container?
- **Session abstraction**: How do we connect to ANY terminal/CLI?
- **Communication protocol**: How do workers talk?
- **Board interface**: CLI? Web dashboard? Both?

These drive what we build.

## Project Structure

```
quinnai/
├── backend/          # Django API (org state, work tracking)
├── app/              # Dashboard UI (board interface)
├── landing/          # Marketing site
├── openspec/         # Project specs and proposals
│   ├── project.md    # Core concepts
│   └── AGENTS.md     # Agent guidelines
├── CLAUDE.md         # Development principles
└── org.yaml          # Your org definition
```

## Development

```bash
# Run tests (required before any code change)
systemeval test

# Start services
make up

# View logs
make logs

# Stop services
make down
```

## Philosophy

**Code = Physics.** We define dynamics (gravity exists). Config defines behavior (build a ball or airplane).

**No provider lock-in.** We define interfaces. Providers implement our contracts. Swap Claude for GPT via config.

**No magic.** All values in config. Explicit initialization. No discovery.

**Interface-first.** Design for 10 providers even if you have 1.

See `CLAUDE.md` for full architectural principles.

## Status

Early development. Core concepts defined. Implementation in progress.
