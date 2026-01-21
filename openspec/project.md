# QuinnAI - Project Definition

## What This Is

An autonomous AI organization that operates like a real company. The org runs itself. Humans are the board - gutterguards that bump it back on track when needed, not required for daily operation.

## Core Abstraction: Session = Worker's Brain

A **Session** is to a **Worker** what a brain is to a human.

```
Session ON  → Worker AWAKE (ready for work)
Session OFF → Worker ASLEEP (inactive)
```

This is one-to-one. Unbreakable. The most critical abstraction in the system.

- Session interface must be provider-agnostic (terminal, Claude Code, Cursor, vim, whatever)
- Session capture must be swappable (PTY, log file, socket, API)
- Session state must be observable (awake/asleep/busy/idle)

**If the session abstraction breaks, everything breaks.**

## Every Agent Is A Worker

CEO is a worker. Manager is a worker. Junior dev is a worker. Same base unit, different:

- **Role** - What they do (PM, Engineer, QA, CEO, etc.)
- **Team** - What group they belong to (Product, Engineering, Operations)
- **Hierarchy** - Who's above, who's below

A worker is not defined by its level. It's defined by its capabilities and relationships.

## Communication Protocol

All worker-to-worker communication uses the same abstracted interface. No special cases. No "claude hooks" vs "file watches" vs "API calls". One protocol.

### Request Types (expandable)

| Type | Direction | Example |
|------|-----------|---------|
| `work-handoff` | down/lateral | "Here's a task for you" |
| `work-request` | up/lateral | "I'm free, give me work" |
| `information-request` | any | "Who handles auth?" |
| `resource-request` | up | "I need more workers" |
| `status-report` | up | "Task complete, here's result" |
| `guidance-request` | up | "Stuck, need direction" |
| `review-request` | up/lateral | "Please review this" |

New types added over time. Protocol is extensible.

### Communication Channels

Each worker can:
1. **Receive/request from outside the org** (metrics, customer feedback, external APIs)
2. **Receive/request from boss** (direction, tasks, feedback)
3. **Delegate/assist subordinates** (tasks, guidance, resources)
4. **Collaborate with peers** (lateral requests, information sharing)

All through the same interface. Channel is just metadata on the request.

## Decision Authority (Who Can Decide What)

Each worker has a **level of freedom** defined by the org configuration. This determines what they can decide autonomously vs. what requires escalation.

### Authority Model

```
Level 0 (Top/CEO): Full decision power across all domains
        ↓
Level 1 (Directors): Full decision power WITHIN their domain
        ↓
Level 2 (Managers): Tactical decisions within domain, escalate strategic
        ↓
Level 3 (Workers): Execute within guidelines, escalate exceptions
```

### Authority = Scope × Domain

- **Scope**: How big a decision can you make? (tactical vs strategic, small vs large impact)
- **Domain**: What area does your authority cover? (product, engineering, support, etc.)

A Level 1 Product Director can make strategic product decisions, but cannot make engineering decisions. They escalate cross-domain issues to Level 0.

A Level 2 Engineering Manager can make tactical engineering decisions (assign tasks, approve PRs), but escalates strategic ones (architecture changes, new hires) to Level 1.

### Configurable, Not Hardcoded

Authority levels are defined in org config (currently YAML, should be flexible):

```yaml
workers:
  ceo:
    level: 0
    domain: "*"  # all domains
    scope: ["strategic", "tactical", "operational"]

  product_director:
    level: 1
    domain: "product"
    scope: ["strategic", "tactical"]
    reports_to: ceo

  eng_lead:
    level: 2
    domain: "engineering"
    scope: ["tactical", "operational"]
    reports_to: ceo
```

### Dynamic Over Time

Authority evolves as org learns:
- Worker proves capable → expand scope/domain
- Worker makes repeated mistakes → narrow scope
- Org grows → add hierarchy levels
- Org shrinks → flatten hierarchy

This is not static. The org adapts.

### Decision Flow

When a worker faces a decision:
1. Is it within my **domain**? No → route to correct domain
2. Is it within my **scope**? No → escalate to higher level
3. Yes to both → decide and act
4. Uncertain → can still act, but queue for review (org doesn't stop)

Top level (CEO) has no one to escalate to except the board (gutterguards). CEO queues questions for board but doesn't block on them.

## Goal Flow (How Work Gets Decided)

The org decides what to do. Not hardcoded. Not human-driven (except gutterguards).

```
External Input (metrics, errors, user feedback)
        ↓
Team interprets (Product decides feature vs bug, Eng estimates effort)
        ↓
Hierarchy prioritizes (CEO allocates resources, Managers assign work)
        ↓
Workers execute
        ↓
Results flow back up + out
```

### Real Org Modeling

Like a real company:
- **Product team** decides what to build (input: customers, metrics, strategy)
- **Engineering team** builds it (input: specs, priorities, resources)
- **QA team** validates it (input: requirements, code, test plans)
- **Operations** keeps it running (input: alerts, logs, incidents)

Each team has its own decision-making process. CEO coordinates across teams. Board provides high-level guidance ("focus on stability" or "ship features fast").

## Board (Humans) = Gutterguards

The ball keeps rolling no matter what. Board only intervenes when:
- Org is heading in wrong direction (strategy misalignment)
- Major decision needs approval (new capability, big resource allocation)
- Something is fundamentally broken (repeated failures, stuck loops)

Board is NOT:
- Required for daily operation
- Approving every task
- Micromanaging workers

Board IS:
- Setting high-level direction ("we're focused on testing this quarter")
- Course-correcting when off track
- Approving expansion (new teams, new capabilities)

## What We're Building

### From Previous Projects (Concepts Only)

**From quinn:** Session observation patterns, message queue flow
**From brain:** Memory and context management concepts
**From dev-hq:** Multi-agent orchestration patterns, activity streaming
**From bottas:** Worker unit protocol, queue mechanics, hierarchy model

**No code reuse.** Concepts and learnings only. Everything rebuilt clean.

### Core Components Needed

1. **Session Interface** - Abstracted session capture/state (provider-agnostic)
2. **Worker Runtime** - The execution loop (claim, execute, report)
3. **Communication Protocol** - Typed requests, unified interface
4. **Goal Handler** - How org decides what to do
5. **Hierarchy Model** - Roles, teams, reporting relationships
6. **Board Interface** - How humans provide gutterguard input

### Success = Process Works

Not "structure is defined." Process works:
- Worker wakes when session starts
- Worker receives/requests work through protocol
- Worker executes and reports through protocol
- Goals flow from org structure + external input
- Board intervenes only when gutterguards trigger
- All communication is abstracted and swappable

## Open Design Questions

1. **Session interface** - What's the minimal abstraction? (start, stop, observe, inject?)
2. **Request protocol** - Wire format? (YAML? JSON? Protobuf?)
3. **Authority config format** - YAML works but is there something better? (typed schema? DSL?)
4. **Team boundaries** - How do teams form and communicate?
5. **Worker spawning** - How does "I need more workers" actually work?
6. **Authority evolution** - How does the org "learn" to adjust authority over time?
