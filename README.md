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

One folder = one org. You describe it declaratively:

```yaml
# ~/orgs/my-startup/org.yaml

name: my-startup

okrs:
  - id: okr-1
    objective: "Build MVP"
    key_results:
      - "Launch beta to 100 users"
      - "Achieve 40% weekly retention"

workers:
  ceo:
    role: CEO
    level: 0
    domain: "*"

  eng-lead:
    role: Engineering Lead
    level: 1
    domain: engineering
    reports_to: ceo

  dev-1:
    role: Developer
    level: 2
    domain: engineering
    reports_to: eng-lead
```

### 2. Start the Org

From that folder, start it. Workers wake up, sessions spin up, work begins flowing.

### 3. Be the Board

Watch the dashboard. See work flowing. See OKR progress. When something's off-track, give direction. Otherwise, stay out of the way.

---

## What Needs Building

The above is aspirational. Here's what we need to figure out:

- **Installation**: How does QuinnAI get on your machine? pip? npm? Standalone binary?
- **Org isolation**: One folder = one org. How do workers, sessions, state stay isolated?
- **Worker runtime**: What actually runs when a worker "wakes up"? A process? Container?
- **Session abstraction**: How do we connect to ANY terminal/CLI without hardcoding?
- **Communication protocol**: How do workers talk? Files? Sockets? Queue?
- **Board interface**: CLI? Web dashboard? Both?
- **State persistence**: Where does org state live? SQLite? Postgres? Files?

These questions drive what we build.

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
