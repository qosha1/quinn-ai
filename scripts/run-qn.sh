#!/bin/bash
# Run the QuinnAI CLI
#
# This script sets up the correct Python path and launches qn.
# Usage: ./scripts/run-qn.sh [COMMAND] [OPTIONS]
#
# Examples:
#   ./scripts/run-qn.sh org status --org-path ~/orgs/my-org
#   ./scripts/run-qn.sh org start --org-path ~/orgs/my-org

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Activate virtual environment if it exists
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Set PYTHONPATH to include CLI
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Run the CLI
exec python -m cli.commands.main "$@"
