#!/usr/bin/env bash
# Initialize the startup-team org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/org"

echo "=== Startup Team: Setup ==="
echo

# Check prerequisites
"$SCRIPT_DIR/../common/check-env.sh" || {
    echo
    echo "Fix the issues above before continuing."
    exit 1
}

echo

# Check if already initialized
if [[ -d "$ORG_DIR" ]]; then
    echo "Org already exists at: $ORG_DIR"
    echo "Run ./cleanup.sh first to reset."
    exit 1
fi

# Initialize the org
echo "Initializing org with CEO..."
qn org init --org-path "$ORG_DIR" --ceo-name "Alice" --ceo-role "CEO"

# Copy custom worker templates (includes Engineer role)
if [[ -f "$SCRIPT_DIR/config/worker-templates.yaml" ]]; then
    echo "Copying custom worker templates..."
    cp "$SCRIPT_DIR/config/worker-templates.yaml" "$ORG_DIR/config/"
fi

echo
echo "=== Setup Complete ==="
echo
echo "Org created at: $ORG_DIR"
echo "CEO: Alice"
echo
echo "Available worker templates:"
echo "  - CEO (already hired)"
echo "  - Engineer (can be hired by CEO)"
echo
echo "Next: Run ./run.sh to start and send initial goal"
