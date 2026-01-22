# OKR-Driven - Strategic Goal Management

The most advanced example. See how strategic goals cascade through the organization:
Board → CEO → Teams → Work Items

## What You'll See

1. Board sets a high-level objective
2. CEO breaks it into key results
3. Key results become team goals
4. Team goals become work items
5. Work completion updates key results
6. Objective progress is tracked

## The OKR Cascade

```
BOARD OBJECTIVE: "Establish market presence in Q1"
    │
    ├── KEY RESULT 1: "Launch MVP by Feb 15"
    │   │
    │   ├── Team Goal: "Complete backend API"
    │   │   └── Work: API endpoints, database, auth
    │   │
    │   └── Team Goal: "Ship frontend"
    │       └── Work: UI components, integration
    │
    └── KEY RESULT 2: "Acquire 100 beta users"
        │
        └── Team Goal: "Marketing campaign"
            └── Work: Landing page, outreach
```

## Quick Start

```bash
# 1. Set up your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 2. Initialize with OKRs
./setup.sh

# 3. Start and watch goals cascade
./run.sh

# 4. Track progress
./observe.sh

# 5. Clean up
./cleanup.sh
```

## Step-by-Step

### Step 1: Setup with OKRs

```bash
./setup.sh
```

This creates:
- CEO (Alice)
- Board-level OKR structure
- Pre-defined objective for Q1

### Step 2: Run

```bash
./run.sh
```

The CEO receives the objective and starts:
1. Breaking down into key results
2. Assigning owners to each KR
3. Hiring if needed
4. Tracking progress

### Step 3: Watch Progress

```bash
./observe.sh
```

Shows:
- Objective status
- Key result progress (0-100%)
- Work items linked to goals
- Team activity

## OKR Structure

### Objectives
High-level, qualitative goals. Set by the board.

```yaml
objective:
  id: obj-q1-market
  title: "Establish market presence in Q1"
  owner: ceo
  timeframe: Q1 2025
```

### Key Results
Measurable outcomes. Owned by leaders.

```yaml
key_results:
  - id: kr-mvp
    title: "Launch MVP by Feb 15"
    metric: launch_date
    target: "2025-02-15"
    current: null
    owner: ceo

  - id: kr-users
    title: "Acquire 100 beta users"
    metric: user_count
    target: 100
    current: 0
    owner: marketing-lead
```

### Work Items (via Beads)
Actionable tasks linked to key results.

```yaml
work_item:
  id: bd-abc123
  title: "Build landing page"
  serves: kr-users  # Links to key result
  owner: engineer-1
  status: in_progress
```

## What This Demonstrates

| Concept | How It's Shown |
|---------|----------------|
| Goal hierarchy | Board → CEO → Teams → Work |
| Strategic alignment | Every work item serves an OKR |
| Progress tracking | KR metrics update as work completes |
| Accountability | Each KR has an owner |
| Transparency | Everyone sees how their work fits |

## Configuration

### Sample OKR (okrs/q1-2025.yaml)

```yaml
objective:
  id: obj-q1-market
  title: "Establish market presence in Q1"
  description: "Get our product into users' hands and prove value"
  owner: ceo
  timeframe:
    start: 2025-01-01
    end: 2025-03-31

key_results:
  - id: kr-mvp-launch
    title: "Launch MVP to public"
    type: milestone
    target_date: 2025-02-15
    owner: ceo

  - id: kr-beta-users
    title: "100 active beta users"
    type: metric
    metric_name: active_users
    target_value: 100
    current_value: 0
    owner: marketing

  - id: kr-nps
    title: "NPS score > 40"
    type: metric
    metric_name: nps_score
    target_value: 40
    current_value: null
    owner: product
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "OKR not loading" | Check `okrs/` directory exists |
| "Work not linking" | Ensure `serves` field in beads |
| "Progress not updating" | KR metrics need manual/auto update |

## Next Steps

After mastering OKRs:

1. Create your own org with custom objectives
2. Build dashboards to visualize OKR progress
3. Automate metric updates from work completion
