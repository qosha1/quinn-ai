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

One folder = one org. Separate concerns in separate places:

```
~/orgs/my-startup/
├── org/
│   ├── structure.yaml      # Who exists, hierarchy, teams
│   ├── roles/              # Role definitions (what can each role do?)
│   │   ├── ceo.yaml
│   │   ├── eng-lead.yaml
│   │   └── developer.yaml
│   └── teams/              # Team definitions
│       ├── engineering.yaml
│       └── product.yaml
├── okrs/
│   ├── 2024-q1/            # OKRs are time-bound
│   │   ├── company.yaml    # Top-level objectives
│   │   ├── engineering.yaml
│   │   └── product.yaml
│   └── current -> 2024-q1  # Symlink to active period
├── work/                   # Where work items live
├── logs/                   # Activity logs
└── state/                  # Runtime state
```

Org structure and OKRs are separate. Both can grow, change, be versioned independently.

### 2. Start the Org

From that folder, start it. Workers wake up based on structure. OKRs drive priorities. Work flows.

### 3. Be the Board

Watch. See work flowing against OKRs. When off-track, give direction. Otherwise, stay out.

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
