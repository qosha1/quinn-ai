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

**Quality standards nudge:**

If you notice work being closed without measurable results:
```bash
# Check OKRs have key results defined
qn org okr progress <okr-id>

# If no key results: message CEO
qn org message ceo "OKR 'Launch MVP' has no measurable key results. Add KRs like:
- Lighthouse score > 90
- Load time < 2s
- Core flows have tests"
```

Workers verify their work against key results before closing. If CEO hasn't set KRs, quality is undefined and workers can't self-verify. Nudge the CEO to add measurable targets.

---

## CLI

Two actors, two command namespaces:

```
qn org <command>     # WE run (humans/system managing the org)
qn wrkr <command>    # WORKERS run (from within their sessions)
```

### Command Map

| Command | Target | Action | Notes |
| --- | --- | --- | --- |
| `qn org init` | Org | Initialize org | Creates org structure + CEO |
| `qn org start` | Org | Start org | Spawns CEO session by default |
| `qn org start --worker <name>` | Worker | Start workday | Fresh session + wakeup nudge |
| `qn org stop` | Org | Stop org | Stops all worker sessions |
| `qn org stop --worker <name>` | Worker | Stop workday | Request wrap-up then close session |
| `qn org status` | Org | Show org status | Lifecycle + workers/sessions |
| `qn org hire` | Worker | Hire worker | Hire == spawn + start + onboard |
| `qn org fire` | Worker | Terminate worker | Stops session + offboarding |
| `qn org observe` | Worker | Attach/stream session | tmux-based |
| `qn org logs` | Worker | View session scrollback | tmux capture |
| `qn org cleanup` | Org | Cleanup sessions/notifications | Orphans + stale |
| `qn org chart show` | Org | Show org chart | Tree view |
| `qn org chart diff` | Org | Chart git diff | Requires git |
| `qn org chart history` | Org | Chart git history | Requires git |
| `qn org chart export` | Org | Export chart | yaml/json |
| `qn org budget status` | Org | Budget summary | Pools + CEO balance |
| `qn org budget tree` | Org | Budget cascade | From CEO or worker |
| `qn org budget allocate` | Worker | Delegate budget | Manager -> report |
| `qn org budget transactions` | Worker | Spend history | Optional filters |
| `qn org okr list` | Org | List OKRs | beads or db |
| `qn org okr show` | OKR | Show OKR details | beads/db |
| `qn org okr add` | OKR | Add OKR | creates new |
| `qn org okr set` | OKR | Update OKR | edit metadata |
| `qn org okr cascade` | OKR | Cascade from root | |
| `qn org okr progress` | OKR | Show progress | |
| `qn org okr update-kr` | KR | Update KR metric | |
| `qn org okr link` | Work/OKR | Link work to OKR | serves |
| `qn wrkr status` | Self | Show worker status | lifecycle + runtime |
| `qn wrkr get-work` | Work queue | Pull next work | requires `--worker-id` or `QUINN_WORKER_ID` |
| `qn wrkr report` | Work | Post status update | requires `--worker-id` or `QUINN_WORKER_ID` |
| `qn wrkr inbox` | Messages | View notifications | requires `--worker-id` or `QUINN_WORKER_ID` |
| `qn wrkr send` | Channel | Send message | requires `--worker-id` or `QUINN_WORKER_ID` |
| `qn wrkr search` | Messages | Search history | requires `--worker-id` or `QUINN_WORKER_ID` |
| `qn wrkr delegate` | Worker | Delegate hiring authority | requires `--worker-id` or `QUINN_WORKER_ID` |

### Notes and Clarifications

- Hire means start: `qn org hire` immediately spawns a session and runs onboarding.
- Workday start means new session: `qn org start --worker <name>` always creates a fresh session and provides a quick wakeup nudge.
- Workday stop requests wrap-up: `qn org stop --worker <name>` sends a wrap-up request, then closes the session.
- Worker commands require identity: use `qn wrkr --worker-id <id> ...` or set `QUINN_WORKER_ID`. Each new worker session (via `qn org hire` or `qn org start --worker`) seeds that environment variable so commands like `qn wrkr get-work` know who is asking. 

### Worker & Org Action Matrix

| Action | Actor | Command | Effect | Notes (future beads) |
| --- | --- | --- | --- | --- |
| Initialize QuinnAI org | Board | `qn org init` | Create org structure, shared storage folders, CEO worker placeholder and provisioning scripts | Base action; no beads yet |
| Start org / spawn CEO session | Board | `qn org start` | Ensures CEO has a fresh session, onboarding nudges, and CLAUDE/AGENTS guidance loaded into shared storage | Related to onboarding epic `quinnai-tiqb` |
| Hire worker (spawn + start + onboarding) | Board / delegated manager | `qn org hire --name <name> --role <role> --manager <manager>` | Worker record created, workspace bootstrapped, session spawned, and onboarding docs delivered | Doc alignment bead: `quinnai-17ms` ensures we keep deployed AGENTS/CLAUDE guidance in `shared/onboarding/configs` |
| Start workday (fresh session) | Org controller | `qn org start --worker <name>` | Always spawns a new session, issues a fresh wakeup nudge, and sets `QUINN_WORKER_ID` for that terminal | Reinforces quick nudge described in onboarding epic `quinnai-tiqb` |
| Stop workday (wrap-up + shutdown) | Org controller | `qn org stop --worker <name>` | Requests worker to wrap up, closes tmux/session, and records end-of-day state | Ensures sessions close cleanly; document session/terminal teardown expectations |
| Observe session | Org controller | `qn org observe --worker <name>` | Attach to the worker's tmux view for real-time oversight | |
| Pull next assigned work | Worker | `qn wrkr get-work [--worker-id <id>]` | Query assigned beads, ordered by priority; uses `--worker-id` or `QUINN_WORKER_ID` to know which worker is asking | Worker identity setup is critical; ensure onboarding seeds `QUINN_WORKER_ID` (see above) |
| Report progress | Worker | `qn wrkr report [--worker-id <id>]` | Post status updates / blockers to the board and bead log | |
| Document deployed org onboarding rules | Maintainer | n/a (documentation) | Clarify which instructions belong to repo vs deployed org and point to `shared/onboarding/configs` for worker-facing docs | Bookmarked by `quinnai-17ms`, also tracks how we present OKRs |
| Feed onboarding briefings with OKRs | Maintainer | n/a | Populate `_load_worker_okrs` so the briefing template shows measurable goals | `quinnai-kdn2` |
| Prevent firing mid-critical work | Maintainer | n/a | Authorization check must flag critical work in progress before allowing a fire | `quinnai-ji0h` |
| Track cumulative hiring cost | Maintainer | n/a | Record every hire cost and compare to available budget before approving another hire | `quinnai-3s49` |

### Worker Command Guidelines

- `qn wrkr get-work`, `qn wrkr report`, `qn wrkr inbox`, `qn wrkr send`, `qn wrkr search`, and similar worker commands all require a worker identity. Use `--worker-id <id>` or rely on the `QUINN_WORKER_ID` environment variable that onboarding/worker-start scripts populate.
- Every worker session begins with a quick wakeup nudge (e.g., “you are an engineer in QuinnAI’s org”) so they know the current priorities. The nudge happens every `qn org start --worker` call and does not replay the full onboarding package.
- To stop working, the org-level controllers (`qn org stop --worker`) ask the worker to wrap up, then shut down the underlying terminal (tmux/session). Workers should close any terminals they manually opened.
- Workers use `qn-bd` (bundled beads CLI) to create/update/close work.

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
