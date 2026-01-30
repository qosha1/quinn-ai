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

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with hot reload (requires textual-dev)
textual run --dev board_ui.app:BoardApp
```
