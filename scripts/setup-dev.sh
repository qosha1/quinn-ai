#!/bin/bash
# Set up QuinnAI development environment
#
# This script:
# 1. Creates a virtual environment (if needed)
# 2. Installs all dependencies
# 3. Sets up the CLI and terminal-app
# 4. Validates the environment
#
# Usage: ./scripts/setup-dev.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== QuinnAI Development Setup ==="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]); then
    echo "Error: Python 3.11+ required (found $PYTHON_VERSION)"
    exit 1
fi
echo "✓ Python $PYTHON_VERSION"

# Create virtual environment if needed
cd "$PROJECT_ROOT"
if [ ! -d ".venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
source .venv/bin/activate
echo "✓ Virtual environment activated"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -q --upgrade pip

# Install root package (includes cli and shared)
pip install -q -e ".[dev]"
echo "✓ CLI installed"

# Install terminal-app
pip install -q -e "./terminal-app[dev]"
echo "✓ Terminal app installed"

# Check for environment file
echo ""
ENV_FILE="$PROJECT_ROOT/.envs/.local/.django"
if [ -f "$ENV_FILE" ]; then
    echo "✓ Environment file found"
else
    echo "⚠ No environment file at .envs/.local/.django"
    echo "  Copy from example: cp .envs/.local/.django.example .envs/.local/.django"
    echo "  Then add your API keys"
fi

# Validate installation
echo ""
echo "Validating installation..."
python -c "import cli.commands.main; print('✓ CLI module OK')"
python -c "import board_ui.main; print('✓ Board UI module OK')"
python -c "import shared; print('✓ Shared module OK')"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Quick start:"
echo "  source .venv/bin/activate"
echo "  source .envs/.local/.django  # Load API keys"
echo ""
echo "Commands:"
echo "  qn --help                    # CLI help"
echo "  qn board ui                  # Launch board UI"
echo "  ./scripts/run-qn.sh          # Run CLI (auto-loads env)"
echo "  ./scripts/run-board.sh       # Run board (auto-loads env)"
echo ""
echo "Create an org:"
echo "  qn --org-path ~/orgs/my-org org init"
echo "  qn --org-path ~/orgs/my-org org start"
