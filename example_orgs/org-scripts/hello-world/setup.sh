#!/usr/bin/env bash
# Initialize the hello-world org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/hello-world"
QN="$SCRIPT_DIR/../common/qn"

echo "=== Hello World: Setup ==="
echo

# Check prerequisites (skip qn check since we use local wrapper)
if ! command -v tmux &> /dev/null; then
    echo "[ERROR] tmux not found. Install: brew install tmux"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found"
    exit 1
fi

echo "[OK] Prerequisites satisfied"
echo

# Check if already initialized
if [[ -d "$ORG_DIR" ]]; then
    echo "Org already exists at: $ORG_DIR"
    echo "Run ./cleanup.sh first to reset."
    exit 1
fi

# Initialize the org
echo "Initializing org..."
"$QN" --org-path "$ORG_DIR" org init --ceo-name "Alice"

# Copy our custom config (optional - defaults are fine for hello-world)
# cp "$SCRIPT_DIR/config/providers.yaml" "$ORG_DIR/config/"

echo
echo "=== Setup Complete ==="
echo
echo "Org created at: $ORG_DIR"
echo
echo "Next: Run ./run.sh to start the org"
