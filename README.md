# QuinnAI

Hierarchical AI organization management. QuinnAI runs a tree of AI workers (CEO, directors, engineers, …) that own OKRs, hire and fire each other, message across channels, and track work in [beads](https://github.com/steveyegge/beads). The platform is provider-agnostic — `claude_code`, `cursor`, `aider`, and others slot in behind a single session interface.

> QuinnAI is the **computer**, not the software running on it. This repo is the platform; orgs you spin up with `qn org init` are the applications.

- **Quickstart** — see [QUICKSTART.md](./QUICKSTART.md)
- **Architecture decisions** — [docs/architecture-decisions/](./docs/architecture-decisions/)
- **CLI internals** — [cli/README.md](./cli/README.md)

---

## Board UI

The board is a Textual TUI — `qn-board` (or `qn board ui`) — that watches one or more orgs in real time. Six tabs, switchable with single-key shortcuts.

![QuinnAI Board – Team view](./QuinnAI_Board_2026-02-10T16_31_58_031511.svg)

### Tab map

```
┌───────────────────────────────────────────────────────────────────────────┐
│  [d] Dashboard   [o] OKRs   [t] Team   [m] Messages   [l] Logs   [s] …   │
├───────────────────────────────────────────────────────────────────────────┤
│ Dashboard │ Cost (today/week/month) · worker counts · "Chat with CEO"    │
│           │ button · mini org chart · health status · recent activity    │
│ OKRs      │ Cascading objective tree: Board → CEO → Directors → ICs,     │
│           │ expandable, with progress bars per key result                │
│ Team      │ Worker list with status (active/idle/blocked), current task  │
│           │ summary, [Chat Now] per worker, filter by team/status        │
│ Messages  │ Channels list + thread view; reply inline. Board replies     │
│           │ can embed intervention commands (pause / fire / resume)      │
│ Logs      │ Searchable, filterable log stream with pagination            │
│ Settings  │ Provider config, board prefs                                 │
└───────────────────────────────────────────────────────────────────────────┘

Global keys:  c copy   r refresh   q quit   ^p command palette
Multi-org:    OrgTabBar at the top — [+] connect another org, [x] disconnect
```

### Team tab — snapshot

```
================================================================================
QUINNAI BOARD - TEAM
================================================================================
Filter: All

Workers (3 displayed, 3 total):

--------------------------------------------------------------------------------
Name: RecipeSimpli CEO
ID: wrkr-081b461f
Role: ★ CEO
Team: Executive
Manager: None
Status: Working... [auto]
Session State: running
Session Mode: autonomous
Tmux Session: qn-wrkr-081b461f

--------------------------------------------------------------------------------
Name: Senior Full-Stack Engineer
ID: wrkr-f699b742
Role: engineer
Team: Executive
Manager: RecipeSimpli CEO
Status: No session
Session Mode: interactive
================================================================================
```

Each worker row exposes `[Chat]`, `[Fire]`, `[Promote]` actions. The CEO is pinned at the top.

---

## Org hierarchy & delegated hiring

The org-chart is a tree with one CEO root. Every non-CEO worker has exactly one `manager_id`. Storage paths mirror the chart so a worker's directory tree encodes its place in the org.

```
                    ┌─────────────┐
                    │     CEO     │  hiring_authority = base
                    └──────┬──────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │ Director │  │ Director │  │ Manager  │   ← delegated authority
       │ (eng)    │  │ (data)   │  │ (ops)    │
       └────┬─────┘  └────┬─────┘  └────┬─────┘
            │             │             │
        ┌───┴───┐     ┌───┴───┐     ┌───┴───┐
        ▼       ▼     ▼       ▼     ▼       ▼
    Engineer Engineer Analyst Analyst  IC      IC


storage/
├── shared/                       # org-lifetime
│   ├── company/                  # docs all workers can read
│   └── engineering/              # team channel files
└── workers/                      # mirrors org chart
    └── ceo/
        ├── director-eng-abc/
        │   ├── engineer-xyz/
        │   └── engineer-pqr/
        └── manager-ops-def/
            └── ic-mno/
```

### How a worker builds out their own team

Only the CEO has hiring authority by default. Anyone else who wants to hire must first be **delegated** the right to do so.

```
   ┌─────────────────────────────────────────────────────────────────┐
   │ 1. CEO delegates hiring authority to a director                 │
   │                                                                 │
   │    qn org delegate-authority \                                  │
   │        --to <director-id> \                                     │
   │        --roles "engineer,analyst" \                             │
   │        --max-cost 60 \           # per-hire cost cap            │
   │        --max-budget 240 \        # total cost across reports    │
   │        --expires "2026-12-31"                                   │
   │                                                                 │
   │  → writes a DelegationGrant row, audit-logged                   │
   └─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ 2. Director can now hire within that scope                      │
   │                                                                 │
   │    qn org hire \                                                │
   │        --name "Alice"  --role engineer  --cost 45 \             │
   │        --manager <director-id>                                  │
   │                                                                 │
   │  Validations on hire:                                           │
   │   - role ∈ delegated allowed_roles                              │
   │   - cost ≤ max_cost                                             │
   │   - sum(reports.cost) + new ≤ max_total_budget                  │
   │   - direct_reports < DEFAULT_MAX_REPORTS (5)                    │
   │   - no circular delegation (A→B→C→A blocked)                    │
   └─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ 3. Director can sub-delegate (optional, if scope allows)        │
   │                                                                 │
   │    qn org delegate-authority --to <manager-id> --roles "ic" …   │
   │                                                                 │
   │  Auto-revocation: terminating a worker revokes every grant      │
   │  they issued or received. All transitions are audit-logged.     │
   └─────────────────────────────────────────────────────────────────┘
```

Related commands: `qn org revoke-authority`, `qn org delegations` (audit trail), `qn org promote`, `qn org demote`, `qn org fire`, `qn org chart show`.

---

## Messaging system

Workers communicate through a beads-backed message store. The board mirrors the same store, so the human in the loop sees and replies in the same threads workers do.

### Worker-facing CLI — `msgr`

```bash
msgr inbox                          # unread messages + notifications
msgr send @worker-id "hey, status?" # direct message
msgr send #engineering "deploying"  # team / topic channel
msgr send @manager-id "BLOCKED: …" --priority=1
msgr channels                       # list channels you can see
msgr read <message-id>              # mark read; pulls thread context
```

### Channels, types, urgency

```
Channel types                    Message types               Urgency
─────────────                    ─────────────               ───────
DIRECT  (1:1, dm-{a}-{b})        REQUEST     (needs reply)   immediate (now)
TEAM    (team-scoped)            RESPONSE    (replies a req) hours     (within hrs)
TOPIC   (topic-scoped)           INFORM      (FYI)           whenever  (no rush)
                                 ESCALATION  (problem up)
                                 DELEGATION  (work assigned)
                                 BROADCAST   (fan-out)
                                                             priority 1 = urgent
                                                             priority 2 = normal
```

### Flow

```
   ┌──────────┐   msgr send #eng         ┌──────────────┐
   │ Engineer │ ────────────────────────►│ Channel:     │
   └──────────┘                          │   #eng       │
                                         └──────┬───────┘
                                                │  fans out as notification_beads
                       ┌────────────────────────┼────────────────────────┐
                       ▼                        ▼                        ▼
                 ┌──────────┐             ┌──────────┐             ┌──────────┐
                 │ Director │             │ Engineer │             │ Engineer │
                 │  inbox   │             │  inbox   │             │  inbox   │
                 └──────────┘             └──────────┘             └──────────┘

   ┌──────────┐   ESCALATION priority=1  ┌──────────────┐
   │  Worker  │ ────────────────────────►│ board-channel│ ◄─── CEO auto-subscribed
   └──────────┘                          └──────┬───────┘      Human watches in
                                                │               Messages tab,
                                                ▼               can reply with:
                                         ┌──────────────┐         pause <wrkr>
                                         │   Board UI   │         fire  <wrkr>
                                         │ Messages tab │         resume <wrkr>
                                         └──────────────┘
```

Reply text on the board is parsed for intervention commands (`pause` / `fire` / `resume`) and dispatched against the live org without blocking the worker — the worker is notified asynchronously when the reply lands.

---

## Provider abstraction

QuinnAI defines the contracts; providers implement them. Swap providers via config — zero code changes.

```
   SessionInterface  (we own this)
          ▲
   ┌──────┼──────┬──────────┬──────────┐
   │      │      │          │          │
ClaudeCodeSession  CursorSession  AiderSession  …  ← adapters
```

Configured per-org in `config/providers.yaml`:

```yaml
providers:
  claude_code:
    enabled: true
    model: claude-opus-4-7
    api_key_env: ANTHROPIC_API_KEY
  cursor:
    enabled: false
    model: gpt-4
    api_key_env: OPENAI_API_KEY
```

---

## Common commands

```bash
# Org lifecycle
qn org init           # scaffold a new org
qn org start          # spawn CEO session, transition to running
qn org stop           # graceful shutdown
qn org status         # health + worker rollup

# Org structure
qn org hire   --name … --role … --manager <id> [--cost N] [--skills '{…}']
qn org fire   <worker-id> --reason …
qn org promote <worker-id>
qn org chart show

# Hiring delegation
qn org delegate-authority --to <id> --roles "engineer,analyst" --max-cost 60
qn org revoke-authority   <grant-id>
qn org delegations                    # audit trail

# OKRs
qn org okr list --from-db
qn org okr update-kr <okr-id> --metric "coverage" --current 85

# Board UI
qn-board                              # multi-org dashboard
qn board ui                           # same, via main CLI

# Worker-side (run from inside a worker session)
qn wrkr get-work
msgr inbox
msgr send @<id> "…"
```

See `qn --help` and `msgr --help` for the full surface.

---

## Repo layout

```
quinn-ai/
├── cli/                    # qn + msgr CLIs
│   ├── commands/           # Click groups (org/, wrkr/, qn_bd, board, …)
│   └── core/               # state machines, sessions, storage, messaging
├── shared/                 # exceptions, enums, message protocol
├── board_ui/               # Textual TUI (views/, widgets/, services/)
├── docs/                   # ADRs, design notes, audits
├── example_orgs/           # runnable examples (hello-world, startup-team, okr-driven)
└── tests/                  # pytest suites
```

---

## Contributing

See [DEVELOPMENT.md](./DEVELOPMENT.md) and [CONTRIBUTING.md](./CONTRIBUTING.md). Work is tracked in beads — `bd ready` to find an issue, `bd update <id> --claim` to start.
