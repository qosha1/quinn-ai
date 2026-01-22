# Hello World - Your First QuinnAI Org

The simplest possible QuinnAI organization. Learn the basic lifecycle:
`init` → `start` → `status` → `stop`

## What You'll See

1. An org folder structure gets created
2. A CEO worker is initialized
3. The org starts running
4. You can check status and observe the CEO
5. The org stops gracefully

## Quick Start

```bash
# 1. Set up your API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 2. Initialize the org
./setup.sh

# 3. Start it running
./run.sh

# 4. Watch what happens
./observe.sh

# 5. Clean up when done
./cleanup.sh
```

## Step-by-Step

### Step 1: Check Prerequisites

```bash
../common/check-env.sh
```

You need:
- `ANTHROPIC_API_KEY` set
- `tmux` installed
- `qn` CLI installed (or run `../common/install-cli.sh`)

### Step 2: Initialize the Org

```bash
./setup.sh
```

This creates:
```
org/
├── config/
│   ├── providers.yaml      # Claude as the AI provider
│   └── worker-templates.yaml   # CEO role definition
├── org-chart/
│   └── current.yaml        # Just the CEO for now
├── live/
│   ├── quinn.db           # All org data
│   └── workers/           # Session state (empty until start)
└── storage/
    ├── shared/            # Org-wide knowledge
    └── workers/           # Per-worker storage
```

### Step 3: Start the Org

```bash
./run.sh
```

What happens:
1. Org transitions from `initialized` → `running`
2. CEO worker activates (`pending` → `active`)
3. A tmux session spawns for the CEO
4. The CEO is ready to receive work

### Step 4: Observe

```bash
./observe.sh
```

Shows:
- Current org status
- CEO worker state
- Recent activity (if any)

### Step 5: Stop and Cleanup

```bash
# Stop the org (keeps folder)
qn org stop --org-path org

# Or full cleanup (removes folder)
./cleanup.sh
```

## What This Demonstrates

| Concept | How It's Shown |
|---------|----------------|
| Org initialization | `qn org init` creates structure |
| Config templates | `providers.yaml` and `worker-templates.yaml` copied |
| Database | Single `quinn.db` for everything |
| Worker lifecycle | CEO goes pending → active |
| Session management | tmux session created for CEO |
| Graceful shutdown | `qn org stop` cleanly stops |

## Next Steps

After mastering hello-world:

1. **[startup-team](../startup-team/)** - CEO hires a worker and delegates tasks
2. **[okr-driven](../okr-driven/)** - Set strategic goals and watch them cascade

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "API key not set" | `export ANTHROPIC_API_KEY="sk-ant-..."` |
| "Org already initialized" | Run `./cleanup.sh` first |
| "qn command not found" | Run `../common/install-cli.sh` |
| "tmux session exists" | `tmux kill-session -t hello-world-ceo` |
