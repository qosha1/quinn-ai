#!/usr/bin/env bash
# Initialize the hello-world org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/org"

echo "=== Hello World: Setup ==="
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
echo "Initializing org..."
qn org init --org-path "$ORG_DIR" --ceo-name "Alice"

# Copy our custom config (optional - defaults are fine for hello-world)
# cp "$SCRIPT_DIR/config/providers.yaml" "$ORG_DIR/config/"

echo
echo "=== Setup Complete ==="
echo
echo "Org created at: $ORG_DIR"
echo
echo "Next: Run ./run.sh to start the org"
