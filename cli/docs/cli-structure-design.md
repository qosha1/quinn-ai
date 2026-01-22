# CLI Structure Design

## Overview

QuinnAI CLI (`qn`) has two command namespaces representing two actors:
- `qn org` - Humans managing the organization
- `qn wrkr` - Workers operating within the organization

## Command Structure

```
qn
├── org                     # Organization management (human actor)
│   ├── init               # Initialize new org
│   ├── start              # Start org (spawn CEO session)
│   ├── stop               # Stop org (graceful shutdown)
│   └── status             # Show org status
│
├── wrkr                    # Worker operations (worker actor)
│   ├── get-work           # Get next work item (bead)
│   ├── inbox              # View messages/notifications
│   ├── send               # Send message to channel/worker
│   └── status             # Show worker status
│
└── bd                      # Beads wrapper (delegated to beads-org)
    └── [all beads commands]
```

## Actor Model

### Human Actor (`qn org`)
- Runs from terminal by human operator
- Has full org-level visibility
- Can hire/fire workers
- Can start/stop org
- Not session-bound

### Worker Actor (`qn wrkr`)
- Runs from within worker session (Claude Code)
- Session-bound (knows its worker ID from env)
- Limited to own scope
- Uses beads for work tracking

## Entry Point Design

```
cli/
├── main.py                 # Entry point: qn command
├── org/                    # qn org subcommands
│   ├── __init__.py        # Click group: @click.group()
│   ├── init.py            # qn org init
│   ├── start.py           # qn org start
│   ├── stop.py            # qn org stop
│   └── status.py          # qn org status
├── wrkr/                   # qn wrkr subcommands
│   ├── __init__.py        # Click group: @click.group()
│   ├── get_work.py        # qn wrkr get-work
│   ├── inbox.py           # qn wrkr inbox
│   ├── send.py            # qn wrkr send
│   └── status.py          # qn wrkr status
└── bd_wrapper.py           # qn bd → delegates to beads-org
```

## Click Structure

```python
# main.py
import click
from cli.org import org_group
from cli.wrkr import wrkr_group

@click.group()
def qn():
    """QuinnAI organization management CLI."""
    pass

qn.add_command(org_group, name="org")
qn.add_command(wrkr_group, name="wrkr")

if __name__ == "__main__":
    qn()
```

```python
# org/__init__.py
import click

@click.group()
def org_group():
    """Manage organization lifecycle."""
    pass

# Subcommands imported and added
from .init import init_cmd
from .start import start_cmd
from .stop import stop_cmd
from .status import status_cmd

org_group.add_command(init_cmd, name="init")
org_group.add_command(start_cmd, name="start")
org_group.add_command(stop_cmd, name="stop")
org_group.add_command(status_cmd, name="status")
```

## Environment Variables

Worker commands use environment variables for context:

| Variable | Description | Required For |
|----------|-------------|--------------|
| `QUINN_WORKER_ID` | Current worker ID | All wrkr commands |
| `QUINN_ORG_PATH` | Path to org folder | All commands |
| `QUINN_DB_PATH` | Override DB path | Optional |

## Configuration

Configuration is passed explicitly, not discovered:

```bash
# Human running org commands
qn --org-path ./my-org org status

# Worker running in session (env vars set by session)
qn wrkr get-work
```

## pyproject.toml Setup

```toml
[project.scripts]
qn = "cli.main:qn"
```

## Implementation Order

1. Setup pyproject.toml with Click dependency
2. Create main.py entry point
3. Create org/ and wrkr/ command groups (empty)
4. Write CLI framework tests
5. Implement org commands (init, start, stop, status)
6. Implement wrkr commands (get-work, inbox, send, status)
