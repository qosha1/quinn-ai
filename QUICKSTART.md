# Quick Start Guide

Get QuinnAI running in 5 minutes.

## Prerequisites

- **Python 3.11+**
- **tmux** - Worker session management
- **API Key** - At least one provider (Anthropic recommended)

```bash
# Install tmux (if not installed)
brew install tmux        # macOS
apt install tmux         # Ubuntu/Debian

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Installation

**Option 1: pip (recommended)**
```bash
pip install quinnai
```

**Option 2: Development setup**
```bash
git clone https://github.com/your-org/quinnai.git
cd quinnai
pip install -r requirements-dev.txt
```

## Run Your First Org

```bash
# 1. Go to the hello-world example
cd example_orgs/org-scripts/hello-world

# 2. Initialize the org
./setup.sh

# 3. Start it
./run.sh

# 4. Watch the CEO work
./observe.sh
```

## What Just Happened?

1. **setup.sh** created an org folder in `generated-orgs/hello-world/` with:
   - `config/` - Provider and worker settings
   - `live/` - Runtime database and session state
   - `org-chart/` - Git-tracked hierarchy
   - `storage/` - Persistent org files

2. **run.sh** started the org:
   - CEO session spawned in tmux
   - Org transitioned to "running" state

3. **observe.sh** shows real-time activity:
   - CEO session output
   - Work items and messages

## Core Commands

```bash
# Organization management (humans run these)
qn org init <path>     # Initialize a new org
qn org start           # Start the org
qn org stop            # Stop the org
qn org status          # Check org state

# Worker operations (workers run these from sessions)
qn wrkr get-work       # Get assigned work
qn wrkr status         # Worker state

# Messaging (workers use standalone msgr CLI)
msgr inbox             # View messages and notifications
msgr send #channel "message"  # Send to channel
msgr send @worker "message"   # Send direct message
msgr channels          # List available channels
```

## Try More Examples

| Example | Time | What You'll Learn |
|---------|------|-------------------|
| [hello-world](./example_orgs/org-scripts/hello-world/) | 5 min | Basic org lifecycle |
| [startup-team](./example_orgs/org-scripts/startup-team/) | 10 min | CEO hiring and delegation |
| [okr-driven](./example_orgs/org-scripts/okr-driven/) | 15 min | Strategic goals cascading |

## Cleanup

```bash
# From the example directory
./cleanup.sh
```

## Next Steps

- Read [README.md](./README.md) for full concepts
- Explore [example_orgs/](./example_orgs/) for more examples
- See [DEVELOPMENT.md](./DEVELOPMENT.md) for contributor setup
- Check [cli/README.md](./cli/README.md) for CLI details
