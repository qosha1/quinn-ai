#!/usr/bin/env bash
# Install the qn CLI for QuinnAI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_DIR="$(cd "$SCRIPT_DIR/../../cli" && pwd)"

echo "Installing QuinnAI CLI..."
echo

# Check if we're in the right place
if [[ ! -f "$CLI_DIR/pyproject.toml" ]] && [[ ! -f "$CLI_DIR/setup.py" ]]; then
    echo "Error: Cannot find CLI source at $CLI_DIR"
    echo "Make sure you're running from within the quinnai repository."
    exit 1
fi

# Install in development mode
echo "Installing from: $CLI_DIR"
cd "$CLI_DIR"

if command -v uv &> /dev/null; then
    echo "Using uv for installation..."
    uv pip install -e .
elif command -v pip3 &> /dev/null; then
    echo "Using pip3 for installation..."
    pip3 install -e .
elif command -v pip &> /dev/null; then
    echo "Using pip for installation..."
    pip install -e .
else
    echo "Error: No pip found. Install Python first."
    exit 1
fi

echo
echo "Installation complete!"

# Verify
if command -v qn &> /dev/null; then
    echo "qn CLI installed at: $(command -v qn)"
    echo
    echo "Test it:"
    echo "  qn --help"
else
    echo "Warning: qn not found in PATH"
    echo "You may need to add Python's bin directory to your PATH"
    echo "Try: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
