# QuinnAI

**RollerCoaster Tycoon, but for organizations.**

Design an org. Hire AI workers. Set goals. Watch it run. Intervene only when it's going off the rails.

## Try It Now

```bash
# 1. Go to examples
cd example_orgs/hello-world

# 2. Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. Run it
./setup.sh    # Initialize org
./run.sh      # Start org
./observe.sh  # Watch the CEO
```

See [example_orgs/](./example_orgs/) for more examples:
- **hello-world** - Basic org lifecycle (5 min)
- **startup-team** - CEO hires and delegates (10 min)
- **okr-driven** - Strategic goals cascade through org (15 min)

## The Idea

You know how in RollerCoaster Tycoon you design a park, hire staff, set prices, and then watch guests walk around having fun (or vomiting)?

QuinnAI is that, but for AI organizations:

1. **Set goals** - Define OKRs as the board, grant budget to CEO
2. **Watch it grow** - CEO hires based on goals, delegates to managers, org grows organically
3. **Watch it run** - Workers wake, work, communicate, complete. Goals cascade down.
4. **Be the board** - Review org-chart, nudge CEO if off-track. Gutterguards, not micromanagers.

## Core Concepts

### Sessions = Brains
Every worker has exactly one session. Session ON = worker awake. Session OFF = asleep. This is unbreakable.

### Workers = Everyone
CEO is a worker. Manager is a worker. Junior dev is a worker. Same base unit, different role/team/authority.

### Skills & Cost = Relative Scores
Workers have skills (0-100) and cost (0-100):
- **Skills**: `coding`, `reasoning`, `research`, `management`, `strategy`
- **Cost**: 25 = cheap models, 75 = mid-tier, 100 = best available

High skill unlocks capabilities. Cost determines model quality. System maps to providers automatically.

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

### Lifecycles = State Determines Behavior
Everything has state. State determines what happens next.
- **Org:** uninitialized → initialized → running → stopped
- **Worker:** pending → onboarding → active → offboarding → terminated
- **Work:** draft → open → in_progress → review → closed

### Organic Growth = CEO-Driven, Not Config-Driven
Orgs grow like companies:
- Board sets goals + budget → CEO plans hiring → CEO hires reports
- Managers delegate authority + budget to their reports
- Reports hire within their scope
- Tree grows from decisions, not from config files

**Org-chart is OUTPUT** - reflects who's been hired, git-tracked for board oversight.

## How It Should Feel

### 1. Org Structure

One folder = one org:

```
~/orgs/my-startup/
├── .git/                   # Org-wide version control
├── config/                 # ORG CONFIG (pulled on init, customizable)
│   ├── providers.yaml      # Authorized CLIs/APIs
│   └── worker-templates.yaml  # Skills/cost profiles
├── org-chart/              # OUTPUT (git-tracked, board oversight)
│   └── current.yaml        # Current state - updated by hiring decisions
├── live/                   # RUNTIME STATE
│   ├── quinn.db            # Central SQLite (org, beads, messages - everything)
│   └── workers/            # Per-worker session state
│       ├── ceo/
│       ├── eng-lead/
│       └── dev-1/
└── storage/                # ABSTRACTED STORAGE
    ├── shared/             # Org lifetime, topic/team organized
    │   ├── engineering/
    │   ├── legal/ip/
    │   └── company/
    └── workers/            # Worker lifetime, mirrors org-chart
        ├── ceo/
        └── team/
            ├── lead-{president-id}/
            └── engineering/
                ├── lead-{eng-vp-id}/
                └── frontend/
                    ├── lead-{fe-lead-id}/
                    └── {dev-id}/
```

**State flow:** Hiring decisions → SQLite (source of truth) → org-chart/ (git-tracked snapshot for board visibility)

**Config on init:** Templates pulled into `config/` on org init. Sensible defaults, user can customize:
- `providers.yaml` - which CLIs/APIs are authorized
- `worker-templates.yaml` - skills/cost profiles for roles

**OKRs:** Beads-based tracking in central `quinn.db`. Git tracks org-chart changes for board visibility.

**Storage abstraction:**
- **shared/**: Org lifetime. Topic/team organized (`/engineering/`, `/legal/ip/`). Survives everything.
- **workers/**: Worker lifetime. Mirrors org-chart structure. `lead-{id}/` for team leads, `{id}/` for ICs.

**On worker termination (fired):**
1. Folder frozen (read-only)
2. System creates `ask` bead: "Offboard storage review: {worker-id}"
3. Assigned teammate reviews, moves useful → `shared/`, deletes rest
4. On ask completion, system deletes worker folder

### 2. Start the Org

1. Board sets OKRs + grants budget
2. CEO spawns (the one guaranteed worker)
3. CEO reads goals, plans hiring
4. CEO hires first reports within budget
5. Managers hire their reports
6. Org grows organically based on work + constraints

**Constraints on hiring:**
- Resources (AI credits, compute budget)
- Onboarding capacity (can't absorb everyone at once)
- Work volume (no point hiring without work)

### 3. Be the Board

**The oversight loop:**
```
Set goals → Watch org grow → Review org-chart → Nudge if off-track → (repeat)
```

**Intervention levels:**
- Soft: Add OKR ("Establish sales function by Q2")
- Medium: Direct feedback to CEO ("Rebalance eng/sales ratio")
- Hard: Fire CEO (nuclear option)

---

## CLI

Two actors, two command namespaces:

```
qn org <command>     # WE run (humans/system managing the org)
qn wrkr <command>    # WORKERS run (from within their sessions)
```

**Org commands:**
```bash
qn org init <path>     # Initialize org folder
qn org start           # Start the org
qn org stop            # Stop the org
qn org status          # Check org state
```

**Worker commands:**
```bash
qn wrkr get-work <id>    # Get my assigned beads
qn wrkr inbox <id>       # Get my messages
qn wrkr send <to> <msg>  # Send message
qn wrkr status <id>      # My current state
```

Workers use `qn-bd` (bundled beads CLI) for work manipulation (create, update, close beads).

---

## What Needs Building

### Decided
- **Single central DB**: `quinn.db` - org state, beads, messages all in one SQLite
- **Org-chart**: Output of hiring decisions, git-tracked for board oversight
- **OKR tracking**: beads + git
- **Storage model**: shared/ (org lifetime) + workers/ (worker lifetime, mirrors org-chart)
- **Lifecycle model**: State determines behavior (org, worker, work all have states)
- **Growth model**: Organic, CEO-driven. Hiring authority cascades down.
- **Worker skills/cost**: Relative scores (0-100). System maps to providers automatically.
- **Config on init**: Templates pulled into `config/`, user can customize if needed.
- **Messages**: Permanent conversation history (Slack-like). Searchable, referenceable forever.
- **Notifications**: Ephemeral work units (beads) pointing to messages. Cleaned up after actioned.
- **CLI structure**: Two namespaces - `qn org` (we run) vs `qn wrkr` (workers run from sessions).
- **Worker runtime**: Each worker = independent process. Workers use `qn wrkr` + `qn-bd` commands.
- **Installation**: Shell script or pip. Bundles Go beads binary with Python package.
- **Beads command**: `qn-bd` (bundled Go binary from beads-org submodule).

### Beads Extensions (in beads-org)

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

**P0 - Core to MVP:**
| Question | Notes |
|----------|-------|
| Budget tracking | How is spend tracked/enforced per worker/team? |

**P1 - Required for real usage:**
| Question | Notes |
|----------|-------|
| Session abstraction | How connect to ANY CLI? (Claude, Codex, Gemini) |
| Permission enforcement | Where does auth check happen? |
| Provider mapping | How does cost→model selection actually work? |

**P2 - Important but not blocking:**
| Question | Notes |
|----------|-------|
| Init flow | Exact steps from `init` to CEO running |
| Board interface | CLI? Web dashboard? Both? |

These drive what we build.

## Prerequisites

**Required:**
- **Python 3.11+** - Core runtime for QuinnAI CLI
- **tmux** - Worker session management (each worker runs in a tmux session)
- **API Key** - At least one provider API key (see below)

**API Keys (set one or more):**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Required for Claude-based workers
export OPENAI_API_KEY="sk-..."          # Optional, for OpenAI provider
```

**Verify prerequisites:**
```bash
cd example_orgs && ./common/check-env.sh
```

## Installation

**Shell (recommended):**
```bash
curl -fsSL https://quinnai.dev/install.sh | bash
```

**pip:**
```bash
pip install quinnai
```

Installs both `qn` and `qn-bd` commands.

## Project Structure

```
quinnai/
├── cli/              # THE CLI (current focus)
│   ├── src/quinnai/
│   │   ├── cli/      # qn commands + qn-bd wrapper
│   │   ├── core/     # Worker, org, provider abstractions
│   │   ├── providers/# Claude, OpenAI, etc.
│   │   └── bin/      # Bundled Go binaries (qn-bd)
│   ├── beads-org/    # Git submodule (Go beads fork)
│   ├── config/       # Default templates
│   ├── scripts/      # Build scripts
│   └── tests/
├── backend/          # Django API (future)
├── app/              # Dashboard UI (future)
├── landing/          # Marketing site (future)
├── openspec/         # Project specs
└── CLAUDE.md
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
