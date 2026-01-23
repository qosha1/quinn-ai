#!/bin/bash
# Run the QuinnAI Board Terminal UI
#
# This script sets up the correct Python path and launches the board.
# Usage: ./scripts/run-board.sh [OPTIONS]
#
# Options are passed through to qn-board (e.g., -o /path/to/org)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Set PYTHONPATH to include both CLI and terminal-app
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/terminal-app/src:$PYTHONPATH"

# Source environment variables if available
ENV_FILE="$PROJECT_ROOT/.envs/.local/.django"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# Run the board
exec python -m board_ui.main "$@"
