# QuinnAI Example Organizations

Try QuinnAI in 5 minutes with these ready-to-run examples.

## Directory Structure

```
example_orgs/
├── org-scripts/          # Example scripts and templates (version controlled)
│   ├── common/           # Shared utilities
│   ├── hello-world/      # Beginner example
│   ├── startup-team/     # Intermediate example
│   └── okr-driven/       # Advanced example
├── generated-orgs/       # Runtime org data (gitignored)
│   ├── hello-world/      # Created by hello-world/setup.sh
│   ├── startup-team/     # Created by startup-team/setup.sh
│   └── okr-driven/       # Created by okr-driven/setup.sh
└── README.md
```

## Quick Start

```bash
# 1. Go to simplest example
cd org-scripts/hello-world

# 2. Initialize and run
./setup.sh
./run.sh

# 3. Watch the CEO work
./observe.sh
```

## Examples

| Example | Difficulty | What You'll Learn |
|---------|------------|-------------------|
| [hello-world](./org-scripts/hello-world/) | Beginner | Basic org lifecycle: init → start → status → stop |
| [startup-team](./org-scripts/startup-team/) | Intermediate | CEO hiring workers, task delegation, message passing |
| [okr-driven](./org-scripts/okr-driven/) | Advanced | Board sets OKRs, goals cascade, work links to objectives |

## Example Script Structure

Each example in `org-scripts/` contains:

```
example-name/
├── README.md           # What this example demonstrates
├── setup.sh            # Initialize the org (run once)
├── run.sh              # Start the org and send initial goal
├── observe.sh          # Watch what's happening
├── cleanup.sh          # Tear down and reset
└── config/             # Pre-configured templates
    ├── providers.yaml      # Which AI providers to use
    └── worker-templates.yaml   # Worker role definitions
```

Generated orgs are created in `generated-orgs/<example-name>/` and contain:
- `config/` - Provider and worker configs
- `live/` - Runtime database and session state
- `org-chart/` - Git-tracked hiring decisions
- `storage/` - Persistent org and worker storage

## Common Utilities

The [common/](./org-scripts/common/) folder contains shared scripts:

- `qn` - CLI wrapper for running qn commands
- `install-cli.sh` - Download and install `qn` CLI
- `wait-for-org.sh` - Wait until org is in desired state
- `cleanup.sh` - Generic cleanup for any org
- `check-env.sh` - Validate environment (API keys, etc.)

## Prerequisites

1. **API Key**: Set `ANTHROPIC_API_KEY` environment variable
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. **tmux**: Required for session management
   ```bash
   # macOS
   brew install tmux

   # Ubuntu/Debian
   apt install tmux
   ```

## Workflow

### First Time Setup

```bash
# 1. Check your environment
./org-scripts/common/check-env.sh

# 2. Start with hello-world
cd org-scripts/hello-world
./setup.sh
./run.sh
```

### Trying Another Example

```bash
# Clean up current example
./cleanup.sh

# Move to next example
cd ../startup-team
./setup.sh
./run.sh
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| "API key not set" | `export ANTHROPIC_API_KEY="sk-ant-..."` |
| "tmux not found" | Install tmux (see Prerequisites) |
| "Org already initialized" | Run `./cleanup.sh` first |
| "No provider configured" | Check `config/providers.yaml` |

## What Happens Under the Hood

When you run an example:

1. **setup.sh**: Creates org in `generated-orgs/<example>/`
   - `config/` - Provider and worker configs
   - `live/` - Runtime database and session state
   - `org-chart/` - Git-tracked hiring decisions
   - `storage/` - Persistent org and worker storage

2. **run.sh**: Starts the organization
   - CEO worker session spawns in tmux
   - Org transitions to "running" state
   - Initial goal/OKR is set (if any)

3. **observe.sh**: Shows real-time activity
   - Tails the org database for changes
   - Shows CEO session output
   - Displays work items and messages

4. **cleanup.sh**: Resets everything
   - Stops all sessions
   - Removes org folder from `generated-orgs/`
   - Ready for fresh start

## Next Steps

After trying these examples:

1. **Create your own org**: Copy `org-scripts/hello-world/` and customize
2. **Configure providers**: Edit `config/providers.yaml`
3. **Define worker roles**: Edit `config/worker-templates.yaml`
4. **Set strategic goals**: Use OKRs to direct your org

See the [QuinnAI README](../README.md) for full documentation.
