# Startup Team - Multi-Worker Organization

Watch a CEO hire an engineer and delegate work. Learn:
- How workers get hired
- How messages flow between workers
- How tasks get assigned and completed

## What You'll See

1. CEO receives a goal: "Build a landing page"
2. CEO decides to hire an engineer
3. Engineer joins the org
4. CEO delegates the task to engineer
5. Engineer works on it and reports back
6. CEO marks the work complete

## Quick Start

```bash
# 1. Set up your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 2. Initialize the org
./setup.sh

# 3. Start and send initial goal
./run.sh

# 4. Watch the hiring and delegation
./observe.sh

# 5. Clean up when done
./cleanup.sh
```

## The Flow

```
Board (You)
    │
    ▼  "Build a landing page by Friday"
   CEO
    │
    ├─── Thinks: "I need an engineer for this"
    │
    ▼  Hires
 Engineer
    │
    ├─── Gets work: "Build landing page"
    │
    ▼  Completes
   CEO
    │
    └─── Reports: "Landing page done"
```

## Step-by-Step

### Step 1: Setup

```bash
./setup.sh
```

Creates org with:
- CEO (Alice) - manages the team
- Worker template for Engineer role
- Channels for communication

### Step 2: Run with Initial Goal

```bash
./run.sh
```

Sends goal to CEO: "Build a landing page for our product"

### Step 3: Watch the Magic

```bash
./observe.sh
```

You'll see:
1. CEO receives the goal
2. CEO creates a hiring request
3. Engineer (Bob) gets hired
4. CEO sends task to Bob
5. Bob acknowledges and works
6. Bob sends completion message
7. CEO updates work status

### Step 4: Explore the State

```bash
# Check org chart - should show CEO + Engineer
cat org/org-chart/current.yaml

# Check messages (from within worker session)
msgr inbox

# Check work items
# (once beads integration is complete)
```

## What This Demonstrates

| Concept | How It's Shown |
|---------|----------------|
| Organic hiring | CEO decides when to hire |
| Worker lifecycle | Engineer: pending → onboarding → active |
| Message passing | CEO → Engineer, Engineer → CEO |
| Org chart updates | Git-tracked hiring decisions |
| Role differentiation | CEO (manager) vs Engineer (IC) |

## Configuration

This example uses pre-configured roles:

**CEO (Alice)**
- Skills: strategy=90, management=85, reasoning=80
- Cost: 75 (mid-tier model)

**Engineer (Bob)**
- Skills: coding=85, reasoning=70
- Cost: 50 (efficient model)

See `config/worker-templates.yaml` for full definitions.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Engineer never hired" | CEO might need more context. Check CEO's session. |
| "Messages not delivered" | Check channel subscriptions in database |
| "Work not assigned" | Beads integration pending (Sprint 2.3) |

## Next Steps

After mastering multi-worker:

1. **[okr-driven](../okr-driven/)** - Set strategic goals that cascade through the org
2. Create your own org with custom roles
