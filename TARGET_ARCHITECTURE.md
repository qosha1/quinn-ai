# QuinnAI Target Architecture

> **Purpose**: This document defines what QuinnAI SHOULD look like, not what it currently is. Use this as the north star for all architectural decisions.
>
> **Source of Truth**: This document derives from and must align with:
> - `CLAUDE.md` - Core principles and anti-patterns
> - `openspec/project.md` - Detailed specifications
> - `openspec/AGENTS.md` - Agent behavior guidelines

---

## Vision

**RollerCoaster Tycoon for Organizations.** Design an org, hire AI workers, set goals, watch it run. Intervene only when off-rails.

---

## The Physics (Immutable Laws)

These principles are the physics of the system. They cannot be changed through configuration.

### 1. Code = Physics, Config = Behavior

Code defines **dynamics** (gravity exists). Config defines **how orgs play** within those dynamics (build a ball or airplane). Never hardcode behavioral decisions.

```
┌─────────────────────────────────────────────────────────────┐
│ CODE (Immutable Physics)                                    │
│ - State machines: lifecycle transitions                     │
│ - Interfaces: Provider, Session, Queue, Memory              │
│ - Validation: can_transition(), is_valid_state()            │
│ - Constraints: 1:1 session-worker, OKR cascade structure    │
├─────────────────────────────────────────────────────────────┤
│ CONFIG (Tunable Behavior)                                   │
│ - providers.yaml: authorized providers, cost thresholds     │
│ - worker-templates.yaml: role definitions, skill profiles   │
│ - workflow.yaml: per-org work states and transitions        │
│ - escalation.yaml: escalation paths and retry policies      │
└─────────────────────────────────────────────────────────────┘
```

### 2. Session = Worker's Brain (Sacred 1:1)

One session, one worker. Unbreakable binding. This abstraction is **sacred**.

```
Session ON  → Worker awake (can process work)
Session OFF → Worker asleep (dormant, no processing)

Runtime State Machine:
STARTING → RUNNING ↔ IDLE → STOPPED
              ↓              ↑
           CRASHED ──────────┘
```

### 3. Every Agent Is A Worker

CEO, manager, junior dev = same base unit (`Worker` class). Differ only by:
- **Role**: ceo, director, manager, lead, engineer, analyst, researcher
- **Team**: engineering, sales, product, operations
- **Hierarchy**: reports_to relationship
- **Authority**: hiring scope, budget delegation, decision domains

No special classes for "important" agents. No `CEOAgent` or `ManagerAgent`.

### 4. One Protocol For Everything

All communication through the same interface. Single central SQLite database (`quinn.db`).

```
Messages      → Permanent knowledge (searchable forever via FTS5)
Notifications → Ephemeral beads (cleaned after actioned, message persists)
Workers       → All agents (CEO to junior, same table)
Teams         → Hierarchical structure
Budget        → Per-worker/team allocations
Sessions      → Runtime state (1:1 with workers)
Events        → Audit trail (all state changes logged)
```

### 5. Work Has Four Independent Dimensions

```
┌─────────────────────────────────────────────────────────────┐
│ ASK        │ Who requested? What? Why? (trigger object)     │
│ FLOW       │ Lifecycle state (draft → open → closed)        │
│ OWNERSHIP  │ Single owner + deadline                        │
│ OKR        │ Strategic goal alignment (via 'serves' link)   │
└─────────────────────────────────────────────────────────────┘
```

All independent. All configurable. All tracked. A work item can change owner without changing flow state.

### 6. OKRs Cascade Hierarchically

```
Board: "Establish market presence"
  └── CEO: "Create base strategy"
        └── Director: "Design 3-month roadmap"
              └── Manager: "Define specs for Q1"
                    └── Worker: [work items link here via 'serves']
```

- Every work item traces to strategic objective
- Key Results are **singular and calculable** (not subjective)
- Progress rolls up from work completion

### 7. Board = Gutterguards

Humans intervene only when org goes off-track. Not required for daily operation.

```
Intervention Levels:
  SOFT   → Add OKR to CEO (gentle nudge)
  MEDIUM → Direct feedback bead (priority escalation)
  HARD   → Fire CEO (nuclear option, requires replacement)

Board Oversight Loop:
  Board sets goals → CEO builds org → org-chart updated →
  Board reviews → Board nudges if needed → CEO adjusts → (repeat)
```

### 8. Lifecycles = State Determines Behavior

State determines what actions are valid, not commands. Check state, act accordingly.

```
Org Lifecycle:
  uninitialized → initialized → running ↔ stopped

Worker Lifecycle (HR/org-chart):
  pending → onboarding → active → offboarding → terminated

Worker Runtime (session/process):
  starting → running ↔ idle → stopped | crashed

Work Lifecycle (configurable per-org):
  draft → open → in_progress → review → closed
```

### 9. Organic Growth (CEO-Driven)

Orgs grow from CEO decisions, not config files.

```
Board sets goals + grants budget to CEO
  → CEO plans hiring based on goals/constraints
  → CEO hires reports within authority
  → CEO delegates budget + authority to managers
  → Managers hire within delegated scope
  → Tree grows from decisions

Constraints on Hiring:
  - Resources (AI credits, compute budget)
  - Onboarding capacity
  - Work volume (need for capacity)

Org-chart is OUTPUT (git-tracked), not INPUT
```

### 10. Skills & Cost Are Relative (0-100)

**Skills** unlock capabilities:
```yaml
coding: 80+     → git access, terminal, code execution
reasoning: 60+  → multi-step planning, complex analysis
research: 80+   → web search, document retrieval
management: 70+ → hire reports, delegate work, review
strategy: 90+   → set OKRs, org design, board communication
creative: 70+   → content creation, brainstorming
```

**Cost** maps to model tier:
```yaml
0-30:   budget   (haiku, gpt-4o-mini)
31-60:  standard (sonnet, gpt-4o)
61-80:  advanced (opus, gpt-4-turbo)
81-100: premium  (best available)
```

User controls **authorized providers**, not model selection. System maps cost to best available model.

### 11. CLI = Two Actors

```bash
qn org <cmd>   # WE run (humans/board managing org)
qn wrkr <cmd>  # WORKERS run (from their sessions)
bd <cmd>       # WORKERS use for beads/work operations
```

---

## Architectural Laws (Anti-Patterns to Avoid)

These laws prevent the mistakes made in dev-hq and bottas.

### No Provider Lock-in
```
Our Interface → Provider Adapter → [OpenAI, Anthropic, etc.]
                                   ↑ swappable via config
```
We define interfaces. Providers implement our contracts. Never reverse.

### No Magic Values
Zero literals in function bodies. All values in `constants.py` or config files.
```python
# WRONG
if worker.cost > 80:  # magic number

# RIGHT
if worker.cost > COST_TIER_PREMIUM:  # from constants.py
```

### No Config Discovery
Configuration passed explicitly at startup. No searching cwd, no env var magic.
```python
# WRONG
config = load_config()  # searches for files

# RIGHT
config = OrgConfig.from_path(explicit_config_path)
```

### No Module Side Effects
Nothing runs at import except definitions. Explicit `initialize()` calls required.
```python
# WRONG (runs at import)
db = sqlite3.connect("quinn.db")

# RIGHT (explicit initialization)
def initialize(db_path: Path) -> Database:
    return Database(db_path)
```

### No String Dispatch
Provider classes implement interface. Registry returns instance. Zero `if provider == "x"`.
```python
# WRONG
if provider_name == "anthropic":
    return ClaudeProvider()

# RIGHT
return registry.get_provider(provider_name)  # polymorphic
```

### Interface-First Design
Design interface as true contract. Even with one provider, build for 10.

### Storage Mirrors Org-Chart
```
shared/  = org lifetime (topics/teams, survives workers)
workers/ = worker lifetime (path mirrors org-chart hierarchy)

On termination: freeze → ask bead for review →
                teammate saves useful to shared/ → delete worker folder
```

---

## Configuration Formats

### providers.yaml
```yaml
# Authorized providers for this organization
version: 1

authorized_providers:
  - anthropic
  - openai

# Cost tier thresholds (override defaults)
cost_tiers:
  budget: {max: 30}      # haiku, gpt-4o-mini
  standard: {max: 60}    # sonnet, gpt-4o
  advanced: {max: 80}    # opus, gpt-4-turbo
  premium: {max: 100}    # best available

# Skill thresholds for capabilities
skill_thresholds:
  coding: 80       # Required for git/terminal access
  reasoning: 60    # Required for multi-step planning
  research: 80     # Required for web search
  management: 70   # Required for hiring
  strategy: 90     # Required for OKR setting

# Provider-specific settings
providers:
  anthropic:
    models:
      - {name: claude-3-haiku, tier: budget, capabilities: [reasoning]}
      - {name: claude-sonnet-4, tier: standard, capabilities: [coding, reasoning, research]}
      - {name: claude-opus-4, tier: premium, capabilities: [coding, reasoning, research, strategy]}
  openai:
    models:
      - {name: gpt-4o-mini, tier: budget, capabilities: [reasoning]}
      - {name: gpt-4o, tier: standard, capabilities: [coding, reasoning]}
      - {name: gpt-5, tier: premium, capabilities: [coding, reasoning, strategy], temperature: 1.0}

# Fallback behavior
fallback:
  strategy: next_tier_down  # Try next cheaper tier if preferred unavailable
  max_retries: 3
```

### worker-templates.yaml
```yaml
# Default worker templates pulled on org init
version: 1

templates:
  ceo:
    cost: 90
    skills:
      strategy: 95
      management: 90
      reasoning: 85
      coding: 40
      research: 70
      creative: 60
    authority:
      can_hire: [director, manager, lead, engineer, analyst, researcher]
      max_reports: 10
      budget_delegate: true

  director:
    cost: 80
    skills:
      strategy: 80
      management: 85
      reasoning: 80
      coding: 50
      research: 75
      creative: 55
    authority:
      can_hire: [manager, lead, engineer, analyst]
      max_reports: 8
      budget_delegate: true

  manager:
    cost: 70
    skills:
      management: 80
      reasoning: 75
      coding: 60
      research: 70
      creative: 50
      strategy: 60
    authority:
      can_hire: [lead, engineer, analyst]
      max_reports: 6
      budget_delegate: true

  lead:
    cost: 65
    skills:
      coding: 85
      management: 70
      reasoning: 80
      research: 65
      creative: 45
      strategy: 50
    authority:
      can_hire: [engineer, analyst]
      max_reports: 4
      budget_delegate: false

  engineer:
    cost: 50
    skills:
      coding: 80
      reasoning: 75
      research: 60
      management: 30
      creative: 40
      strategy: 30
    authority:
      can_hire: []
      max_reports: 0
      budget_delegate: false

  junior_engineer:
    cost: 30
    skills:
      coding: 60
      reasoning: 60
      research: 50
      management: 20
      creative: 35
      strategy: 20
    authority:
      can_hire: []
      max_reports: 0
      budget_delegate: false

  analyst:
    cost: 45
    skills:
      research: 80
      reasoning: 75
      coding: 40
      management: 30
      creative: 50
      strategy: 40
    authority:
      can_hire: []
      max_reports: 0
      budget_delegate: false

  researcher:
    cost: 55
    skills:
      research: 90
      reasoning: 80
      coding: 30
      management: 25
      creative: 60
      strategy: 45
    authority:
      can_hire: []
      max_reports: 0
      budget_delegate: false
```

### workflow.yaml
```yaml
# Work lifecycle states (per-org customizable)
version: 1

work_states:
  - draft
  - open
  - in_progress
  - review
  - blocked
  - closed

transitions:
  draft: [open, closed]
  open: [in_progress, blocked, closed]
  in_progress: [review, blocked, closed]
  review: [in_progress, closed]
  blocked: [open, in_progress, closed]
  closed: []  # terminal

terminal_states: [closed]

# OKR linking requirement
require_okr_link: true  # work must link to OKR via 'serves'

# Auto-assignment rules
auto_assign:
  enabled: true
  strategy: least_loaded  # or: round_robin, skill_match
```

### escalation.yaml
```yaml
# Escalation paths and retry policies
version: 1

escalation_paths:
  default:
    - level: 1
      to: direct_manager
      after_hours: 4
      priority_bump: 1
    - level: 2
      to: skip_level_manager
      after_hours: 8
      priority_bump: 1
    - level: 3
      to: ceo
      after_hours: 24
      priority_bump: 2

  critical:
    - level: 1
      to: direct_manager
      after_hours: 1
      priority_bump: 2
    - level: 2
      to: ceo
      after_hours: 2
      priority_bump: 2

retry_policy:
  max_retries: 3
  backoff: exponential  # linear, exponential, fixed
  base_delay_minutes: 15

notification_rules:
  escalation:
    notify_original_assignee: true
    notify_escalation_target: true
    create_bead: true
```

---

## Target Folder Structure

### Org Folder (Runtime)

```
~/orgs/my-startup/
├── .git/                       # Org-wide version control
├── config/                     # ORG CONFIGURATION
│   ├── providers.yaml          # Authorized providers + thresholds
│   ├── worker-templates.yaml   # Role skill/cost profiles
│   ├── workflow.yaml           # Per-org work states
│   └── escalation.yaml         # Escalation paths
├── org-chart/                  # OUTPUT (git-tracked, board oversight)
│   ├── current.yaml           # Current state
│   └── history/               # Historical snapshots
│       └── 2026-01-21.yaml
├── live/                       # RUNTIME STATE
│   ├── quinn.db               # Central SQLite (all data)
│   └── sessions/              # Per-worker session state
│       ├── ceo/
│       │   ├── session.pid
│       │   └── context.json
│       └── {worker-id}/
└── storage/                   # WORKER KNOWLEDGE
    ├── shared/               # Org lifetime (survives workers)
    │   ├── engineering/
    │   ├── legal/
    │   ├── company/
    │   └── topics/
    └── workers/              # Worker lifetime (mirrors org-chart)
        ├── ceo/
        │   └── notes/
        └── team/
            └── engineering/
                ├── lead-{id}/
                └── {worker-id}/
```

### Org-Chart Format (current.yaml)
```yaml
# Auto-generated - DO NOT EDIT MANUALLY
# Updated by hiring/firing events
version: 1
generated_at: "2026-01-21T20:30:00Z"

org:
  name: my-startup
  status: running
  created_at: "2026-01-15T10:00:00Z"

workers:
  wrkr-ceo-abc123:
    name: Alice
    role: ceo
    lifecycle: active
    runtime: running
    reports_to: null
    team: executive
    hired_at: "2026-01-15T10:00:00Z"

  wrkr-eng-def456:
    name: Bob
    role: lead
    lifecycle: active
    runtime: idle
    reports_to: wrkr-ceo-abc123
    team: engineering
    hired_at: "2026-01-16T14:00:00Z"

teams:
  executive:
    lead: wrkr-ceo-abc123
    members: [wrkr-ceo-abc123]
    channel: "#executive"

  engineering:
    lead: wrkr-eng-def456
    members: [wrkr-eng-def456]
    channel: "#engineering"
    parent: executive

hierarchy:
  - wrkr-ceo-abc123:
      - wrkr-eng-def456
```

### Codebase Structure (Source)

```
quinnai/
├── cli/                        # CLI APPLICATION
│   ├── commands/
│   │   ├── main.py            # Entry: qn
│   │   ├── context.py         # Request context (DI container)
│   │   ├── org/               # qn org commands
│   │   │   ├── init.py        # Initialize org
│   │   │   ├── start.py       # Start org (spawns CEO)
│   │   │   ├── stop.py        # Graceful shutdown
│   │   │   ├── status.py      # Org health
│   │   │   ├── okr.py         # OKR management
│   │   │   ├── intervene.py   # Board intervention
│   │   │   ├── observe.py     # Watch activity
│   │   │   ├── logs.py        # Tail logs
│   │   │   └── cleanup.py     # Maintenance
│   │   └── wrkr/              # qn wrkr commands
│   │       ├── get_work.py    # Fetch assigned beads
│   │       ├── inbox.py       # Read messages
│   │       ├── send.py        # Send messages
│   │       ├── search.py      # Search message history
│   │       └── status.py      # Worker state
│   ├── core/                   # CORE ABSTRACTIONS
│   │   ├── db.py              # SQLite schema + operations
│   │   ├── queries.py         # Query builders
│   │   ├── worker.py          # Worker state machine
│   │   ├── org.py             # Org state machine
│   │   ├── session.py         # Session interface
│   │   ├── sessions/          # Session implementations
│   │   │   ├── registry.py    # Type → impl mapping (no string dispatch)
│   │   │   ├── claude_code.py # Claude Code adapter
│   │   │   └── generic.py     # Generic CLI adapter
│   │   ├── provider.py        # Provider selection (polymorphic)
│   │   ├── budget.py          # Budget enforcement
│   │   ├── permissions.py     # Authorization (who can do what)
│   │   ├── lifecycle.py       # State validation
│   │   ├── storage.py         # Storage abstraction (mirrors org-chart)
│   │   ├── org_chart.py       # Org-chart generation
│   │   ├── events.py          # Event bus (pub/sub)
│   │   ├── escalation.py      # Escalation routing
│   │   ├── notifications.py   # Message/notification mgmt
│   │   ├── bd_wrapper.py      # Beads CLI wrapper
│   │   ├── constants.py       # All magic values (no literals in code)
│   │   └── config.py          # Config loading (explicit injection)
│   ├── providers/             # PROVIDER IMPLEMENTATIONS
│   │   ├── base.py            # Provider interface (ABC)
│   │   ├── anthropic.py       # Claude provider
│   │   └── openai.py          # OpenAI provider
│   ├── config/                # DEFAULT TEMPLATES
│   │   ├── providers.yaml
│   │   ├── worker-templates.yaml
│   │   ├── workflow.yaml
│   │   └── escalation.yaml
│   └── bin/                   # BUNDLED BINARIES
│       └── bd                 # Beads CLI (Go binary)
├── shared/                     # SHARED BUSINESS LOGIC (provider-agnostic)
│   ├── __init__.py            # Exports
│   ├── state_machines.py      # Lifecycle definitions (immutable physics)
│   ├── exceptions.py          # Business exceptions
│   ├── provider_types.py      # Provider interfaces
│   ├── bd/                    # Beads client (CANONICAL location)
│   │   ├── client.py          # BdClient
│   │   └── types.py           # Type constants
│   ├── wrkr/                  # Worker abstractions
│   │   ├── core/              # BaseWorker + state
│   │   ├── comms/             # Messaging (inbox/outbox)
│   │   ├── work/              # Queue, memory, OKR links
│   │   ├── escalation/        # Escalation routing
│   │   └── org/               # Org-chart topology
│   └── pyterm/                # Terminal session management
├── backend/                    # DJANGO API (future)
├── app/                        # DASHBOARD UI (future)
├── landing/                    # MARKETING SITE (future)
├── example_orgs/               # READY-TO-RUN EXAMPLES
│   ├── hello-world/
│   ├── startup-team/
│   └── okr-driven/
├── openspec/                   # SPECIFICATIONS (source of truth)
│   ├── project.md
│   ├── AGENTS.md
│   └── specs/
└── tests/                      # INTEGRATION TESTS
```

---

## Target Database Schema

```sql
-- Schema version 6 (target)
-- All data in single quinn.db file

-- Org state (singleton)
CREATE TABLE org_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- singleton
    status TEXT NOT NULL,        -- uninitialized|initialized|running|stopped
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workers (all agents - CEO to junior)
CREATE TABLE workers (
    id TEXT PRIMARY KEY,         -- wrkr-{role}-{nanoid}
    name TEXT NOT NULL,
    role TEXT NOT NULL,          -- ceo|director|manager|lead|engineer|analyst|researcher
    team_id TEXT REFERENCES teams(id),
    reports_to TEXT REFERENCES workers(id),

    -- Skills (0-100, from worker-templates.yaml)
    skill_coding INTEGER DEFAULT 50,
    skill_reasoning INTEGER DEFAULT 50,
    skill_research INTEGER DEFAULT 50,
    skill_management INTEGER DEFAULT 50,
    skill_strategy INTEGER DEFAULT 50,
    skill_creative INTEGER DEFAULT 50,

    -- Cost & Authority
    cost INTEGER DEFAULT 50,     -- 0-100 relative cost
    hiring_authority_scope TEXT, -- JSON: {can_hire: [], max_reports: N}
    delegated_budget INTEGER DEFAULT 0,
    max_reports INTEGER DEFAULT 0,

    -- State (dual: lifecycle + runtime)
    lifecycle_status TEXT NOT NULL DEFAULT 'pending',
        -- pending|onboarding|active|offboarding|terminated
    runtime_status TEXT,
        -- starting|running|idle|stopped|crashed

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Teams (hierarchical)
CREATE TABLE teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES teams(id),
    lead_id TEXT REFERENCES workers(id),
    channel_id TEXT REFERENCES channels(id),  -- auto-created
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Channels (communication)
CREATE TABLE channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,   -- #engineering, #general, @alice-bob
    type TEXT NOT NULL,          -- team|topic|direct
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Channel members (many-to-many)
CREATE TABLE channel_members (
    channel_id TEXT REFERENCES channels(id) ON DELETE CASCADE,
    worker_id TEXT REFERENCES workers(id) ON DELETE CASCADE,
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id, worker_id)
);

-- Messages (permanent, searchable)
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(id),
    sender_id TEXT NOT NULL REFERENCES workers(id),
    content TEXT NOT NULL,
    thread_id TEXT REFERENCES messages(id),  -- for threading
    references_bead TEXT,        -- optional bead reference
    priority TEXT DEFAULT 'normal',  -- low|normal|high|urgent
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Full-text search on messages
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='rowid'
);

-- Triggers for FTS sync
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (NEW.rowid, NEW.content);
END;
CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', OLD.rowid, OLD.content);
END;
CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', OLD.rowid, OLD.content);
    INSERT INTO messages_fts(rowid, content) VALUES (NEW.rowid, NEW.content);
END;

-- Notifications (ephemeral, cleaned after action)
CREATE TABLE notifications (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL REFERENCES workers(id),
    message_id TEXT REFERENCES messages(id),
    bead_id TEXT,                -- optional bead reference
    type TEXT NOT NULL,          -- message|mention|assignment|escalation
    status TEXT DEFAULT 'unread',-- unread|read|actioned
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actioned_at TIMESTAMP
);

-- Notification cleanup rules:
-- actioned: delete after 7 days
-- read: delete after 30 days
-- unread: never auto-delete (escalate instead)

-- OKRs (hierarchical, cascading)
CREATE TABLE okrs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    owner_id TEXT NOT NULL REFERENCES workers(id),
    parent_id TEXT REFERENCES okrs(id),  -- cascade hierarchy
    status TEXT DEFAULT 'active',        -- active|completed|cancelled
    key_results TEXT,            -- JSON array: [{metric, target, current, unit}]
    due_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Work-OKR links (beads 'serves' OKRs)
CREATE TABLE work_okr_links (
    bead_id TEXT NOT NULL,
    okr_id TEXT NOT NULL REFERENCES okrs(id),
    link_type TEXT DEFAULT 'serves',  -- serves|contributes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bead_id, okr_id)
);

-- Budget allocations
CREATE TABLE budget_allocations (
    id TEXT PRIMARY KEY,
    worker_id TEXT REFERENCES workers(id),
    team_id TEXT REFERENCES teams(id),
    amount INTEGER NOT NULL,     -- in org's budget units
    period TEXT NOT NULL,        -- monthly|quarterly
    used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (worker_id IS NOT NULL OR team_id IS NOT NULL)
);

-- Sessions (runtime, 1:1 with workers)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL UNIQUE REFERENCES workers(id),
    provider TEXT NOT NULL,      -- anthropic|openai
    model TEXT NOT NULL,         -- claude-sonnet-4, gpt-4o, etc.
    tmux_session TEXT,           -- tmux session name: qn-{worker-id}
    status TEXT NOT NULL,        -- starting|running|idle|stopped|crashed
    pid INTEGER,
    started_at TIMESTAMP,
    last_activity TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Events (audit trail, all state changes)
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,    -- worker.hired|worker.fired|okr.created|message.sent|...
    entity_type TEXT NOT NULL,   -- worker|team|okr|message|session|org
    entity_id TEXT NOT NULL,
    payload TEXT,                -- JSON event data
    actor_id TEXT,               -- who triggered (worker_id or 'system' or 'board')
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for event replay
CREATE INDEX idx_events_type_time ON events(event_type, created_at);
CREATE INDEX idx_events_entity ON events(entity_type, entity_id);

-- Escalations (in-flight)
CREATE TABLE escalations (
    id TEXT PRIMARY KEY,
    original_bead_id TEXT NOT NULL,
    current_level INTEGER DEFAULT 1,
    escalation_path TEXT NOT NULL,  -- from escalation.yaml
    escalated_to TEXT REFERENCES workers(id),
    status TEXT DEFAULT 'active',   -- active|resolved|cancelled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);
```

---

## Target Event System

```python
# cli/core/events.py

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterator, Any

class EventType(Enum):
    # Org events
    ORG_INITIALIZED = "org.initialized"
    ORG_STARTED = "org.started"
    ORG_STOPPED = "org.stopped"

    # Worker events
    WORKER_HIRED = "worker.hired"
    WORKER_FIRED = "worker.fired"
    WORKER_PROMOTED = "worker.promoted"
    WORKER_LIFECYCLE_CHANGED = "worker.lifecycle_changed"
    WORKER_RUNTIME_CHANGED = "worker.runtime_changed"

    # Session events
    SESSION_STARTED = "session.started"
    SESSION_STOPPED = "session.stopped"
    SESSION_CRASHED = "session.crashed"

    # Team events
    TEAM_CREATED = "team.created"
    TEAM_DELETED = "team.deleted"
    TEAM_MEMBER_ADDED = "team.member_added"
    TEAM_MEMBER_REMOVED = "team.member_removed"

    # Message events
    MESSAGE_SENT = "message.sent"
    MESSAGE_THREAD_STARTED = "message.thread_started"

    # Work events
    WORK_CREATED = "work.created"
    WORK_ASSIGNED = "work.assigned"
    WORK_STATUS_CHANGED = "work.status_changed"
    WORK_COMPLETED = "work.completed"
    WORK_ESCALATED = "work.escalated"

    # OKR events
    OKR_CREATED = "okr.created"
    OKR_UPDATED = "okr.updated"
    OKR_COMPLETED = "okr.completed"
    OKR_CASCADED = "okr.cascaded"

@dataclass
class Event:
    type: EventType
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    actor_id: str
    timestamp: datetime

class EventBus:
    """Central event bus for system-wide events."""

    def __init__(self, db: Database):
        self._db = db
        self._handlers: dict[EventType, list[Callable]] = {}

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Subscribe to events of a specific type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers and persist to DB."""
        # Persist to events table
        self._db.insert_event(event)

        # Notify subscribers
        for handler in self._handlers.get(event.type, []):
            handler(event)

    def replay(self, since: datetime) -> Iterator[Event]:
        """Replay events since a timestamp (for recovery)."""
        return self._db.query_events(since=since)
```

### Auto-Triggered Behaviors

| Event | Auto-Trigger |
|-------|-------------|
| `ORG_INITIALIZED` | Create CEO worker in pending state |
| `ORG_STARTED` | Spawn CEO session, transition to running |
| `TEAM_CREATED` | Create #team-{name} channel, subscribe lead |
| `TEAM_MEMBER_ADDED` | Subscribe to team channel |
| `TEAM_MEMBER_REMOVED` | Unsubscribe from team channel |
| `WORKER_HIRED` | Update org-chart, create storage folder, emit welcome message |
| `WORKER_FIRED` | Freeze storage, create review bead, update org-chart |
| `MESSAGE_SENT` | Create notifications for channel members (except sender) |
| `WORK_ASSIGNED` | Create notification for assignee |
| `WORK_ESCALATED` | Create escalation record, notify escalation target |
| `OKR_CREATED` | Cascade to direct reports if owner has reports |
| `SESSION_CRASHED` | Update runtime state, attempt restart, escalate if persistent |

---

## Target Escalation System

```python
# cli/core/escalation.py

@dataclass
class EscalationPath:
    name: str
    levels: list[EscalationLevel]

@dataclass
class EscalationLevel:
    level: int
    target: str  # "direct_manager" | "skip_level_manager" | "ceo" | specific worker_id
    after_hours: int
    priority_bump: int

class EscalationManager:
    """Manages work item escalation based on config."""

    def __init__(self, config: EscalationConfig, event_bus: EventBus):
        self._config = config
        self._event_bus = event_bus

    def check_escalations(self) -> list[Escalation]:
        """Check for work items that need escalation."""
        # Called periodically by scheduler

    def escalate(self, bead_id: str, reason: str) -> Escalation:
        """Escalate a work item to next level."""

    def resolve(self, escalation_id: str) -> None:
        """Mark escalation as resolved."""

    def get_escalation_target(self, worker: Worker, level: EscalationLevel) -> Worker:
        """Resolve escalation target based on org-chart."""
        if level.target == "direct_manager":
            return self._get_manager(worker)
        elif level.target == "skip_level_manager":
            manager = self._get_manager(worker)
            return self._get_manager(manager) if manager else self._get_ceo()
        elif level.target == "ceo":
            return self._get_ceo()
        else:
            return self._get_worker(level.target)
```

---

## Target Provider System

```python
# cli/core/provider.py

from abc import ABC, abstractmethod

class Provider(ABC):
    """Abstract provider interface. All providers implement this."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (anthropic, openai, etc.)."""

    @abstractmethod
    def get_models(self) -> list[ModelInfo]:
        """Get available models for this provider."""

    @abstractmethod
    def get_model_for_tier(self, tier: CostTier, capabilities: set[str]) -> ModelInfo | None:
        """Get best model for given tier and required capabilities."""

class ProviderRegistry:
    """Registry of available providers. No string dispatch."""

    _providers: dict[str, Type[Provider]]

    def __init__(self):
        self._providers = {}

    def register(self, provider_class: Type[Provider]) -> None:
        """Register a provider class."""
        instance = provider_class()
        self._providers[instance.name] = provider_class

    def get(self, name: str) -> Provider:
        """Get provider instance by name."""
        if name not in self._providers:
            raise ProviderNotFoundError(f"Unknown provider: {name}")
        return self._providers[name]()

    def select_for_worker(
        self,
        worker_cost: int,
        worker_skills: dict[str, int],
        authorized_providers: list[str],
        skill_thresholds: dict[str, int],
    ) -> ProviderSelection:
        """
        Select optimal provider for worker.

        Algorithm:
        1. Map cost to tier (0-30=budget, 31-60=standard, etc.)
        2. Derive required capabilities from skills vs thresholds
        3. Filter to authorized providers
        4. Find provider + model satisfying all requirements
        5. Build fallback chain for resilience
        """
        tier = self._cost_to_tier(worker_cost)
        capabilities = self._derive_capabilities(worker_skills, skill_thresholds)

        for provider_name in authorized_providers:
            provider = self.get(provider_name)
            model = provider.get_model_for_tier(tier, capabilities)
            if model:
                return ProviderSelection(
                    provider=provider,
                    model=model,
                    cost_tier=tier,
                    capabilities=capabilities,
                    fallback_chain=self._build_fallback_chain(
                        provider, tier, capabilities, authorized_providers
                    ),
                )

        raise ProviderSelectionError(
            f"No provider found for tier={tier}, capabilities={capabilities}"
        )
```

---

## Target Session System

```python
# cli/core/session.py

from abc import ABC, abstractmethod

class SessionInterface(ABC):
    """Universal AI session abstraction. Sacred 1:1 with worker."""

    @property
    @abstractmethod
    def worker_id(self) -> str:
        """The worker this session belongs to."""

    @property
    @abstractmethod
    def status(self) -> SessionState:
        """Current session state."""

    @abstractmethod
    async def start(self) -> None:
        """Start the session (spawn tmux + CLI process)."""

    @abstractmethod
    async def send(self, message: str) -> str:
        """Send message and get response."""

    @abstractmethod
    async def get_status(self) -> SessionState:
        """Get current session state."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop session."""

class SessionRegistry:
    """Maps provider → session implementation. No string dispatch."""

    _implementations: dict[str, Type[SessionInterface]]

    def register(self, provider: str, impl: Type[SessionInterface]) -> None:
        """Register session implementation for provider."""
        self._implementations[provider] = impl

    def create_for_worker(
        self,
        worker: Worker,
        provider_selection: ProviderSelection,
        working_directory: Path,
    ) -> SessionInterface:
        """Create appropriate session for worker."""
        impl_class = self._implementations.get(provider_selection.provider.name)
        if not impl_class:
            raise SessionCreationError(
                f"No session implementation for provider: {provider_selection.provider.name}"
            )

        return impl_class(
            worker_id=worker.id,
            provider=provider_selection.provider,
            model=provider_selection.model,
            working_directory=working_directory,
        )
```

---

## Target Storage System

```python
# cli/core/storage.py

class StorageManager:
    """
    Manages worker and shared storage.

    Storage mirrors org-chart:
    - shared/ = org lifetime (topics/teams)
    - workers/ = worker lifetime (mirrors hierarchy)
    """

    def __init__(self, org_path: Path):
        self._org_path = org_path
        self._shared_path = org_path / "storage" / "shared"
        self._workers_path = org_path / "storage" / "workers"

    def get_worker_path(self, worker: Worker) -> Path:
        """
        Get storage path for worker (mirrors org-chart).

        Example:
          CEO reports to nobody -> storage/workers/ceo/
          Lead reports to CEO, team=engineering -> storage/workers/team/engineering/lead-{id}/
          Dev reports to Lead -> storage/workers/team/engineering/{id}/
        """
        if worker.reports_to is None:
            return self._workers_path / worker.role

        # Build path based on org-chart hierarchy
        team = worker.team_id or "general"
        return self._workers_path / "team" / team / worker.id

    def get_shared_path(self, topic: str) -> Path:
        """Get shared storage path for topic."""
        return self._shared_path / topic

    def create_worker_storage(self, worker: Worker) -> Path:
        """Create storage folder for new worker."""
        path = self.get_worker_path(worker)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def freeze_worker(self, worker_id: str) -> None:
        """Freeze worker storage on termination (read-only marker)."""
        path = self.get_worker_path_by_id(worker_id)
        (path / ".frozen").touch()

    def is_frozen(self, worker_id: str) -> bool:
        """Check if worker storage is frozen."""
        path = self.get_worker_path_by_id(worker_id)
        return (path / ".frozen").exists()

    def cleanup_worker(
        self,
        worker_id: str,
        useful_files: list[Path],
        target_topic: str = "archived",
    ) -> None:
        """
        Move useful files to shared, delete worker folder.

        Called after review bead is closed.
        """
        worker_path = self.get_worker_path_by_id(worker_id)
        shared_path = self.get_shared_path(target_topic) / worker_id

        # Move useful files
        shared_path.mkdir(parents=True, exist_ok=True)
        for file in useful_files:
            if file.exists():
                shutil.move(str(file), str(shared_path / file.name))

        # Delete worker folder
        shutil.rmtree(worker_path)
```

---

## Target Authorization System

```python
# cli/core/permissions.py

class Permission(Enum):
    # Worker permissions
    HIRE = "hire"
    FIRE = "fire"
    PROMOTE = "promote"
    DELEGATE_BUDGET = "delegate_budget"

    # Work permissions
    ASSIGN_WORK = "assign_work"
    CLOSE_WORK = "close_work"
    ESCALATE = "escalate"

    # OKR permissions
    CREATE_OKR = "create_okr"
    UPDATE_OKR = "update_okr"

    # Message permissions
    SEND_TO_CHANNEL = "send_to_channel"
    CREATE_CHANNEL = "create_channel"

class AuthorizationManager:
    """Manages who can do what based on role, hierarchy, and team."""

    def can(self, actor: Worker, permission: Permission, target: Any = None) -> tuple[bool, str]:
        """
        Check if actor can perform permission on target.

        Returns (allowed, reason).
        """
        if permission == Permission.HIRE:
            return self._can_hire(actor, target)
        elif permission == Permission.FIRE:
            return self._can_fire(actor, target)
        # ... etc

    def _can_hire(self, actor: Worker, role: str) -> tuple[bool, str]:
        """Check hiring authority."""
        scope = actor.hiring_authority_scope
        if not scope:
            return False, "No hiring authority"
        if role not in scope.get("can_hire", []):
            return False, f"Cannot hire role: {role}"
        if self._count_reports(actor) >= actor.max_reports:
            return False, "Max reports reached"
        return True, "Authorized"

    def _can_fire(self, actor: Worker, target: Worker) -> tuple[bool, str]:
        """Check if actor can fire target."""
        # Can only fire direct reports
        if target.reports_to != actor.id:
            return False, "Can only fire direct reports"
        # CEO can only be fired by board
        if target.role == "ceo":
            return False, "CEO can only be fired by board intervention"
        return True, "Authorized"
```

---

## Target Dependency Injection Pattern

```python
# cli/commands/context.py

from dataclasses import dataclass
from pathlib import Path

@dataclass
class OrgContext:
    """
    Dependency injection container for org operations.

    All dependencies explicitly injected, never discovered.
    """
    org_path: Path
    db: Database
    event_bus: EventBus
    provider_registry: ProviderRegistry
    session_registry: SessionRegistry
    storage_manager: StorageManager
    escalation_manager: EscalationManager
    authorization_manager: AuthorizationManager
    config: OrgConfig

def create_context(org_path: Path) -> OrgContext:
    """
    Create fully-initialized context for org operations.

    This is the ONLY place where components are instantiated.
    Everything else receives dependencies via this context.
    """
    # Explicit config loading (no discovery)
    config = OrgConfig.from_path(org_path / "config")

    # Database initialization
    db = Database(org_path / "live" / "quinn.db")

    # Event bus (central pub/sub)
    event_bus = EventBus(db)

    # Provider registry (polymorphic, no string dispatch)
    provider_registry = ProviderRegistry()
    for provider_class in get_provider_classes():
        provider_registry.register(provider_class)

    # Session registry
    session_registry = SessionRegistry()
    session_registry.register("anthropic", ClaudeCodeSession)
    session_registry.register("openai", GenericSession)

    # Storage manager
    storage_manager = StorageManager(org_path)

    # Escalation manager
    escalation_manager = EscalationManager(config.escalation, event_bus)

    # Authorization manager
    authorization_manager = AuthorizationManager(db)

    return OrgContext(
        org_path=org_path,
        db=db,
        event_bus=event_bus,
        provider_registry=provider_registry,
        session_registry=session_registry,
        storage_manager=storage_manager,
        escalation_manager=escalation_manager,
        authorization_manager=authorization_manager,
        config=config,
    )
```

---

## Installation

```bash
# Shell (recommended)
curl -fsSL https://quinnai.dev/install.sh | bash

# pip
pip install quinnai
```

Installs:
- `qn` - Python CLI
- `qn-bd` / `bd` - Bundled Go binary (beads CLI)

---

## Migration Path

### Phase 1: Foundation (Blocking)
1. Event system (`cli/core/events.py`)
2. Hiring authority cascade in Worker
3. Storage abstraction (`cli/core/storage.py`)
4. CEO auto-spawn on `qn org start`
5. Dependency injection container

### Phase 2: Core Functionality
6. Work lifecycle enforcement
7. Message full-text search
8. OKR cascade with work linking
9. Team channel auto-creation
10. Escalation system

### Phase 3: Board Controls
11. Board intervention commands
12. Org-chart tracking on hire/fire
13. Worker termination cleanup workflow
14. Authorization enforcement

### Phase 4: Consolidation
15. Consolidate BdClient to `shared/bd/`
16. Remove all string dispatch
17. Explicit config injection everywhere
18. Full test coverage via systemeval

---

## Anti-Patterns Checklist

Before merging any code, verify:

- [ ] No hardcoded values in function bodies (use `constants.py`)
- [ ] No config discovery (explicit paths at startup)
- [ ] No module side effects (only definitions at import)
- [ ] No string dispatch (`if provider == "x"`)
- [ ] No provider lock-in (interfaces first)
- [ ] No direct instantiation (use DI container)
- [ ] Tests pass (`systemeval test`)
- [ ] State determines behavior (check lifecycle before acting)
- [ ] Events published for state changes
- [ ] Storage paths mirror org-chart
- [ ] Authorization checked before operations

---

## Success Criteria

QuinnAI is complete when:

1. `qn org init && qn org start` spawns CEO automatically
2. CEO can hire reports within budget and authority
3. Work items require OKR alignment (configurable)
4. Messages searchable forever, notifications cleaned
5. Org-chart reflects hiring decisions (git-tracked)
6. Board can intervene at soft/medium/hard levels
7. Worker termination triggers knowledge transfer
8. Skills unlock capabilities
9. Cost maps to model tier automatically
10. All state changes emit events
11. Escalations route correctly based on config
12. All example_orgs workflows pass integration tests

---

*This document is the north star. Current implementation should converge toward this target.*

*Source of truth: CLAUDE.md, openspec/project.md, openspec/AGENTS.md*
