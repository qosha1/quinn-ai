# QuinnAI Target Architecture

> **Purpose**: This document defines what QuinnAI SHOULD look like, not what it currently is. Use this as the north star for all architectural decisions.

## Vision

**RollerCoaster Tycoon for Organizations.** Design an org, hire AI workers, set goals, watch it run. Intervene only when off-rails.

---

## Core Architectural Principles

### 1. Code = Physics, Config = Behavior

Code defines **dynamics** (gravity exists). Config defines **how orgs play** within those dynamics (build a ball or airplane).

```
┌─────────────────────────────────────────────────────────────┐
│ CODE (Immutable Physics)                                    │
│ - State machines: lifecycle transitions                     │
│ - Interfaces: Provider, Session, Queue, Memory              │
│ - Validation: can_transition(), is_valid_state()            │
├─────────────────────────────────────────────────────────────┤
│ CONFIG (Tunable Behavior)                                   │
│ - providers.yaml: authorized providers, cost thresholds     │
│ - worker-templates.yaml: role definitions, skill profiles   │
│ - workflow.yaml: per-org work states                        │
│ - teams.yaml: team structure, channel mappings              │
└─────────────────────────────────────────────────────────────┘
```

### 2. Session = Worker's Brain (Sacred 1:1)

One session, one worker. Unbreakable binding.

```
Session ON  → Worker awake (can process work)
Session OFF → Worker asleep (dormant, no processing)

STARTING → RUNNING ↔ IDLE → STOPPED
              ↓              ↑
           CRASHED ──────────┘
```

### 3. Every Agent Is A Worker

CEO, manager, junior dev = same base unit. Differ only by:
- **Role**: ceo, director, manager, lead, engineer, analyst
- **Team**: engineering, sales, product
- **Hierarchy**: reports_to relationship
- **Authority**: hiring scope, budget delegation

No special classes for "important" agents.

### 4. One Protocol For Everything

Single central SQLite database (`quinn.db`). All data in one place.

```
Messages      → Permanent knowledge (searchable forever)
Notifications → Ephemeral work units (beads, cleaned after actioned)
Workers       → All agents (CEO to junior)
Teams         → Hierarchical structure
Budget        → Per-worker/team allocations
Sessions      → Runtime state
```

### 5. Work Has Four Independent Dimensions

```
┌─────────────────────────────────────────────────────────────┐
│ ASK        │ Who requested? What? Why?                      │
│ FLOW       │ Lifecycle state (draft → open → closed)        │
│ OWNERSHIP  │ Single owner + deadline                        │
│ OKR        │ Strategic goal alignment                       │
└─────────────────────────────────────────────────────────────┘
```

All independent. All configurable. All tracked.

### 6. OKRs Cascade Hierarchically

```
Board: "Establish market presence"
  └── CEO: "Create base strategy"
        └── Director: "Design 3-month roadmap"
              └── Manager: "Define specs for Q1"
                    └── Worker: [work items link here via 'serves']
```

Every work item traces to strategic objective. Progress rolls up.

### 7. Board = Gutterguards

Humans intervene only when org goes off-track:

```
Intervention Levels:
  SOFT   → Add OKR to CEO (gentle nudge)
  MEDIUM → Direct feedback bead (priority escalation)
  HARD   → Fire CEO (nuclear option)
```

### 8. Lifecycles = State Determines Behavior

State determines what actions are valid, not commands.

```
Worker Lifecycle (org-chart/HR):
  pending → onboarding → active → offboarding → terminated

Worker Runtime (session/process):
  starting → running ↔ idle → stopped | crashed

Org Lifecycle:
  uninitialized → initialized → running ↔ stopped

Work Lifecycle (configurable):
  draft → open → in_progress → review → closed
```

### 9. Organic Growth (CEO-Driven)

Orgs grow from CEO decisions, not config files.

```
Board sets goals + budget
  → CEO plans hiring
  → CEO hires reports within authority
  → Managers delegate authority + budget
  → Tree grows from decisions

Org-chart is OUTPUT (git-tracked), not INPUT
```

### 10. Skills & Cost Are Relative (0-100)

**Skills** unlock capabilities:
```yaml
coding: 80+     → git access, terminal, code execution
reasoning: 60+  → multi-step planning
research: 80+   → web search, document retrieval
management: 70+ → hire reports, delegate work
strategy: 90+   → set OKRs, org design
```

**Cost** maps to model tier:
```yaml
0-30:   budget   (haiku, gpt-4o-mini)
31-60:  standard (sonnet, gpt-4o)
61-80:  advanced (opus, gpt-4-turbo)
81-100: premium  (best available)
```

### 11. CLI = Two Actors

```bash
qn org <cmd>   # WE run (humans managing org)
qn wrkr <cmd>  # WORKERS run (from their sessions)
bd <cmd>       # WORKERS use for beads operations
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
│   └── workflow.yaml           # Per-org work states
├── org-chart/                  # OUTPUT (git-tracked)
│   └── current.yaml           # Reflects hiring decisions
├── live/                       # RUNTIME STATE
│   ├── quinn.db               # Central SQLite
│   └── sessions/              # Per-worker session files
│       ├── ceo/
│       └── {worker-id}/
└── storage/                   # WORKER KNOWLEDGE
    ├── shared/               # Org lifetime (survives workers)
    │   ├── engineering/
    │   ├── legal/
    │   └── company/
    └── workers/              # Worker lifetime (mirrors org-chart)
        ├── ceo/
        └── team/
            └── engineering/
                ├── lead-{id}/
                └── {worker-id}/
```

### Codebase Structure (Source)

```
quinnai/
├── cli/                        # CLI APPLICATION
│   ├── commands/
│   │   ├── main.py            # Entry: qn
│   │   ├── context.py         # Request context
│   │   ├── org/               # qn org commands
│   │   │   ├── init.py        # Initialize org
│   │   │   ├── start.py       # Start org (spawns CEO)
│   │   │   ├── stop.py        # Graceful shutdown
│   │   │   ├── status.py      # Org health
│   │   │   ├── okr.py         # OKR management
│   │   │   ├── intervene.py   # Board intervention
│   │   │   └── observe.py     # Watch activity
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
│   │   │   ├── registry.py    # Type → impl mapping
│   │   │   ├── claude_code.py # Claude Code adapter
│   │   │   └── generic.py     # Generic CLI adapter
│   │   ├── provider.py        # Provider selection
│   │   ├── budget.py          # Budget enforcement
│   │   ├── permissions.py     # Team-based access
│   │   ├── lifecycle.py       # State validation
│   │   ├── storage.py         # Storage abstraction
│   │   ├── org_chart.py       # Org-chart generation
│   │   ├── events.py          # Event bus
│   │   ├── notifications.py   # Message/notification mgmt
│   │   ├── bd_wrapper.py      # Beads CLI wrapper
│   │   ├── constants.py       # All magic values
│   │   └── config.py          # Config loading
│   ├── providers/             # PROVIDER IMPLEMENTATIONS
│   │   ├── base.py            # Provider interface
│   │   ├── anthropic.py       # Claude provider
│   │   └── openai.py          # OpenAI provider
│   ├── config/                # DEFAULT TEMPLATES
│   │   ├── providers.yaml
│   │   └── worker-templates.yaml
│   └── bin/                   # BUNDLED BINARIES
│       └── bd                 # Beads CLI
├── shared/                     # SHARED BUSINESS LOGIC
│   ├── __init__.py            # Exports
│   ├── state_machines.py      # Lifecycle definitions
│   ├── exceptions.py          # Business exceptions
│   ├── provider_types.py      # Provider interfaces
│   ├── bd/                    # Beads client (CANONICAL)
│   │   ├── client.py          # BdClient
│   │   └── types.py           # Type constants
│   ├── wrkr/                  # Worker abstractions
│   │   ├── core/              # BaseWorker + state
│   │   ├── comms/             # Messaging (inbox/outbox)
│   │   ├── work/              # Queue, memory, OKR links
│   │   ├── escalation/        # Escalation routing
│   │   └── org/               # Org-chart topology
│   └── pyterm/                # Terminal session management
├── backend/                    # DJANGO API
├── app/                        # DASHBOARD UI
├── landing/                    # MARKETING SITE
├── example_orgs/               # READY-TO-RUN EXAMPLES
├── openspec/                   # SPECIFICATIONS
└── tests/                      # INTEGRATION TESTS
```

---

## Target Database Schema

```sql
-- Schema version 6 (target)

-- Org state
CREATE TABLE org_state (
    id INTEGER PRIMARY KEY,
    status TEXT NOT NULL,        -- uninitialized|initialized|running|stopped
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Workers (all agents)
CREATE TABLE workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,          -- ceo|director|manager|lead|engineer|analyst
    team_id TEXT REFERENCES teams(id),
    reports_to TEXT REFERENCES workers(id),

    -- Skills (0-100)
    skill_coding INTEGER DEFAULT 50,
    skill_reasoning INTEGER DEFAULT 50,
    skill_research INTEGER DEFAULT 50,
    skill_management INTEGER DEFAULT 50,
    skill_strategy INTEGER DEFAULT 50,
    skill_creative INTEGER DEFAULT 50,

    -- Cost & Authority
    cost INTEGER DEFAULT 50,     -- 0-100 relative cost
    hiring_authority_scope TEXT, -- who they can hire (JSON)
    delegated_budget INTEGER,    -- budget they can delegate
    max_reports INTEGER,         -- max direct reports

    -- State
    lifecycle_status TEXT NOT NULL,  -- pending|onboarding|active|offboarding|terminated
    runtime_status TEXT,             -- starting|running|idle|stopped|crashed

    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Teams (hierarchical)
CREATE TABLE teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES teams(id),
    channel_id TEXT REFERENCES channels(id),  -- auto-created channel
    created_at TIMESTAMP
);

-- Channels (communication)
CREATE TABLE channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,          -- #engineering, #general
    type TEXT NOT NULL,          -- team|topic|direct
    created_at TIMESTAMP
);

-- Channel members
CREATE TABLE channel_members (
    channel_id TEXT REFERENCES channels(id),
    worker_id TEXT REFERENCES workers(id),
    subscribed_at TIMESTAMP,
    PRIMARY KEY (channel_id, worker_id)
);

-- Messages (permanent, searchable)
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT REFERENCES channels(id),
    sender_id TEXT REFERENCES workers(id),
    content TEXT NOT NULL,
    thread_id TEXT REFERENCES messages(id),  -- for threading
    references_bead TEXT,        -- optional bead reference
    created_at TIMESTAMP
);

-- Full-text search on messages
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='rowid'
);

-- Notifications (ephemeral, cleaned after action)
CREATE TABLE notifications (
    id TEXT PRIMARY KEY,
    worker_id TEXT REFERENCES workers(id),
    message_id TEXT REFERENCES messages(id),
    bead_id TEXT,                -- optional bead reference
    type TEXT NOT NULL,          -- message|mention|assignment|escalation
    status TEXT DEFAULT 'unread',-- unread|read|actioned
    created_at TIMESTAMP,
    actioned_at TIMESTAMP
);

-- OKRs (hierarchical, tracked)
CREATE TABLE okrs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    owner_id TEXT REFERENCES workers(id),
    parent_id TEXT REFERENCES okrs(id),  -- cascade hierarchy
    status TEXT DEFAULT 'active',        -- active|completed|cancelled

    -- Key Results (JSON array of {metric, target, current})
    key_results TEXT,

    due_date DATE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Work item OKR links
CREATE TABLE work_okr_links (
    bead_id TEXT NOT NULL,
    okr_id TEXT REFERENCES okrs(id),
    link_type TEXT DEFAULT 'serves',  -- serves|contributes
    PRIMARY KEY (bead_id, okr_id)
);

-- Budget allocations
CREATE TABLE budget_allocations (
    id TEXT PRIMARY KEY,
    worker_id TEXT REFERENCES workers(id),
    team_id TEXT REFERENCES teams(id),
    amount INTEGER NOT NULL,
    period TEXT NOT NULL,        -- monthly|quarterly
    used INTEGER DEFAULT 0,
    created_at TIMESTAMP
);

-- Sessions (runtime)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    worker_id TEXT REFERENCES workers(id) UNIQUE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,        -- starting|running|idle|stopped|crashed
    pid INTEGER,
    started_at TIMESTAMP,
    last_activity TIMESTAMP
);

-- Events (audit trail)
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,    -- worker.hired|worker.fired|okr.created|...
    entity_type TEXT NOT NULL,   -- worker|team|okr|message
    entity_id TEXT NOT NULL,
    payload TEXT,                -- JSON event data
    actor_id TEXT,               -- who triggered
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Target Event System

```python
# cli/core/events.py

class EventType(Enum):
    # Worker events
    WORKER_HIRED = "worker.hired"
    WORKER_FIRED = "worker.fired"
    WORKER_PROMOTED = "worker.promoted"
    WORKER_STARTED = "worker.started"
    WORKER_STOPPED = "worker.stopped"

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

    # OKR events
    OKR_CREATED = "okr.created"
    OKR_UPDATED = "okr.updated"
    OKR_COMPLETED = "okr.completed"

class EventBus:
    """Central event bus for system-wide events."""

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """Subscribe to events of a specific type."""

    def publish(self, event_type: EventType, payload: dict) -> None:
        """Publish an event to all subscribers."""

    def replay(self, since: datetime) -> Iterator[Event]:
        """Replay events since a timestamp (for recovery)."""
```

### Auto-Triggered Behaviors

| Event | Auto-Trigger |
|-------|-------------|
| `TEAM_CREATED` | Create #team-{name} channel, subscribe members |
| `TEAM_MEMBER_ADDED` | Subscribe to team channel |
| `TEAM_MEMBER_REMOVED` | Unsubscribe from team channel |
| `WORKER_HIRED` | Update org-chart, create storage folder |
| `WORKER_FIRED` | Freeze storage, create review bead, update org-chart |
| `MESSAGE_SENT` | Create notifications for channel members |
| `WORK_ASSIGNED` | Create notification for assignee |
| `OKR_CREATED` | Cascade to direct reports if applicable |

---

## Target Provider System

```python
# cli/core/provider.py

class ProviderRegistry:
    """Registry of available providers."""

    def select_for_worker(
        self,
        worker_cost: int,
        worker_skills: dict[str, int],
        authorized_providers: list[str],
    ) -> ProviderSelection:
        """
        Select optimal provider for worker.

        Algorithm:
        1. Map cost to tier (0-30=budget, 31-60=standard, etc.)
        2. Derive required capabilities from skills
        3. Filter to authorized providers
        4. Find provider + model satisfying all requirements
        5. Return selection with fallback chain
        """

class ProviderSelection:
    provider: Provider
    model: ModelInfo
    cost_tier: CostTier
    capabilities: set[str]
    fallback_chain: list[tuple[Provider, ModelInfo]]
```

### No String Dispatch

```python
# WRONG (anti-pattern)
if provider_name == "anthropic":
    return ClaudeProvider()
elif provider_name == "openai":
    return OpenAIProvider()

# RIGHT (polymorphic)
class ProviderRegistry:
    _providers: dict[str, Type[Provider]]

    def get(self, name: str) -> Provider:
        return self._providers[name]()
```

---

## Target Session System

```python
# cli/core/session.py

class SessionInterface(ABC):
    """Universal AI session abstraction."""

    @abstractmethod
    async def start(self) -> None:
        """Start the session (spawn process)."""

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
    """Maps provider → session implementation."""

    _implementations: dict[str, Type[SessionInterface]]

    def create_for_worker(
        self,
        worker: Worker,
        provider_selection: ProviderSelection,
    ) -> SessionInterface:
        """Create appropriate session for worker."""
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

    def get_worker_path(self, worker: Worker) -> Path:
        """Get storage path for worker (mirrors org-chart)."""

    def get_shared_path(self, topic: str) -> Path:
        """Get shared storage path for topic."""

    def freeze_worker(self, worker_id: str) -> None:
        """Freeze worker storage on termination."""

    def cleanup_worker(self, worker_id: str, useful_files: list[Path]) -> None:
        """Move useful files to shared, delete worker folder."""
```

---

## Target Hiring Authority

```python
# In Worker class

class Worker:
    # ... existing fields ...

    hiring_authority_scope: HiringScope
    delegated_budget: int
    max_reports: int

    def can_hire(self, role: str, cost: int) -> tuple[bool, str]:
        """Check if worker can hire for this role/cost."""

    def hire(
        self,
        name: str,
        role: str,
        skills: dict[str, int],
        cost: int,
    ) -> Worker:
        """
        Hire a new worker.

        Validates:
        - Role within authority scope
        - Cost within delegated budget
        - Reports count under max

        Triggers:
        - WORKER_HIRED event
        - Org-chart update
        - Storage folder creation
        """

    def delegate_authority(
        self,
        report: Worker,
        budget: int,
        scope: HiringScope,
    ) -> None:
        """Delegate hiring authority to a report."""

class HiringScope:
    """Defines who a worker can hire."""

    allowed_roles: set[str]      # e.g., {"engineer", "analyst"}
    max_cost: int                # max cost of hires
    max_total_budget: int        # total budget for all hires
```

---

## Target Board Intervention

```python
# cli/commands/org/intervene.py

@click.command()
@click.option("--level", type=click.Choice(["soft", "medium", "hard"]))
@click.option("--message", "-m")
def intervene_cmd(level: str, message: str):
    """
    Board intervention on organization.

    Levels:
    - soft: Add OKR to CEO (gentle nudge)
    - medium: High-priority bead to CEO (escalation)
    - hard: Terminate CEO (nuclear option)
    """
```

---

## Target Work Lifecycle

```yaml
# config/workflow.yaml (per-org customizable)

work_states:
  - draft
  - open
  - in_progress
  - review
  - closed

transitions:
  draft: [open]
  open: [in_progress, closed]
  in_progress: [review, closed]
  review: [in_progress, closed]
  closed: []  # terminal

terminal_states: [closed]

require_okr_link: true  # work must link to OKR
```

---

## Migration Path

### Phase 1: Foundation (Blocking)
1. Event system (`cli/core/events.py`)
2. Hiring authority cascade in Worker
3. Storage abstraction (`cli/core/storage.py`)
4. CEO auto-spawn on `qn org start`

### Phase 2: Core Functionality
5. Work lifecycle enforcement
6. Message full-text search
7. OKR cascade with work linking
8. Team channel auto-creation

### Phase 3: Board Controls
9. Board intervention commands
10. Org-chart tracking on hire/fire
11. Worker termination cleanup workflow

### Phase 4: Consolidation
12. Consolidate BdClient to `shared/bd/`
13. Remove all string dispatch
14. Explicit config injection everywhere

---

## Anti-Patterns Checklist

Before merging any code, verify:

- [ ] No hardcoded values in function bodies (use `constants.py`)
- [ ] No config discovery (explicit paths at startup)
- [ ] No module side effects (only definitions at import)
- [ ] No string dispatch (`if provider == "x"`)
- [ ] No provider lock-in (interfaces first)
- [ ] Tests pass (`systemeval test`)
- [ ] State determines behavior (check lifecycle before acting)
- [ ] Events published for state changes
- [ ] Storage paths mirror org-chart

---

## Success Criteria

QuinnAI is complete when:

1. `qn org init && qn org start` spawns CEO automatically
2. CEO can hire reports within budget
3. Work items require OKR alignment
4. Messages searchable forever, notifications cleaned
5. Org-chart reflects hiring decisions (git-tracked)
6. Board can intervene at soft/medium/hard levels
7. Worker termination triggers knowledge transfer
8. Skills unlock capabilities
9. Cost maps to model tier automatically
10. All state changes emit events

---

*This document is the north star. Current implementation should converge toward this target.*
