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
- `qn wrkr status` - Show worker status

### Messaging (msgr)

Workers use the standalone messaging CLI for communication:

- `msgr inbox` - View inbox messages and notifications
- `msgr send <channel> <message>` - Send messages to channels (#engineering) or workers (@alice)
- `msgr channels` - List available channels
- `msgr read <notification-id>` - Mark notifications as read

## Development

The CLI depends on the `quinnai-shared` package which must be installed separately.
See the main README for full development setup instructions.
