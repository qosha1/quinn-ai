#!/bin/bash
# Run the QuinnAI Board Terminal UI
#
# This script sets up the correct Python path and launches the board.
# Usage: ./scripts/run-board.sh [OPTIONS]
#
# Options are passed through to qn board ui (e.g., -o /path/to/org)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Set PYTHONPATH to include both CLI and terminal-app
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/terminal-app/src:$PYTHONPATH"

# Run the board using the new qn board ui command
exec qn board ui "$@"
