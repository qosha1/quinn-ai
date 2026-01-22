# QuinnAI CLI

Command-line interface for QuinnAI organization management.

## Installation

```bash
# From repo root, install both shared and cli packages in development mode
pip install -r requirements-dev.txt
```

## Commands

### Organization Management (qn org)

Human operators use these commands to manage the organization:

- `qn org init` - Initialize a new organization
- `qn org start` - Start the organization
- `qn org stop` - Stop the organization
- `qn org status` - Show organization status

### Worker Operations (qn wrkr)

AI workers use these commands (requires QUINN_WORKER_ID):

- `qn wrkr get-work` - Get assigned work
- `qn wrkr inbox` - View inbox messages
- `qn wrkr send` - Send a message
- `qn wrkr status` - Show worker status

## Development

The CLI depends on the `quinnai-shared` package which must be installed separately.
See the main README for full development setup instructions.
