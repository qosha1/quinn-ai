# QuinnAI Board Terminal UI

Interactive TUI for board oversight of AI organizations.

## Overview

The Board UI provides a terminal-based interface for human oversight of running AI organizations. Board members are "gutterguards" - they intervene only when the org is off-track.

## Features

- **Dashboard**: Org status, metrics, and cost overview with prominent "Chat with CEO" button
- **OKRs View**: Cascading objectives from Board → CEO → Directors → Managers → Workers
- **Team View**: All workers with status and ability to "jump in" to any session
- **Messages**: Async board inbox for escalated questions requiring response

## Key UX Principles

- **No terminal jargon**: Buttons do things, not commands
- **Windows are meetings**: Open = join conversation, close = leave (worker keeps working)
- **No one waits**: All interactions are async or observable state

## Installation

```bash
pip install quinnai-board
```

## Usage

```bash
# Launch the board UI (new command)
qn board ui

# Connect to a specific org
qn board ui -o ~/my-org

# Use a specific terminal for chat windows
qn board ui --terminal kitty

# Legacy command (deprecated, will show warning)
qn board ui
```

## Terminal Support

The board UI opens new windows for "Chat Now" functionality. Supported terminals:

- **Kitty** (recommended) - Uses remote control protocol
- **iTerm2** - Uses AppleScript
- **Terminal.app** - Uses AppleScript (macOS default)
- **Generic** - Fallback for other terminals

## Development

From the monorepo root, one command sets up the venv and installs both `quinnai` (CLI) and `quinnai-board` (this package) with dev deps:

```bash
make setup                # creates .venv, installs cli + terminal-app + dev deps
make test-terminal-app    # runs this package's test suite
```

If you'd rather drive `pip` directly, install in this order — `quinnai-board` declares `quinnai` as a dependency, so the CLI must be on the path first or pip will look on PyPI:

```bash
source .venv/bin/activate
pip install -e ..              # install quinnai (CLI) from monorepo root
pip install -e ".[dev]"        # install board UI + pytest, pytest-asyncio, textual-dev
pytest                         # 332 tests, ~2 minutes
```

`pytest-asyncio` is required (the suite is almost entirely `async def` tests). It's in `[project.optional-dependencies].dev` — if you skip the `[dev]` extra, every test errors at collection with "async def functions are not natively supported".

Run with hot reload:

```bash
textual run --dev board_ui.app:BoardApp
```
