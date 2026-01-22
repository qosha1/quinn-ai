#!/usr/bin/env bash
# Start the hello-world org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/hello-world"
QN="$SCRIPT_DIR/../common/qn"

echo "=== Hello World: Run ==="
echo

# Check org exists
if [[ ! -d "$ORG_DIR" ]]; then
    echo "Org not found. Run ./setup.sh first."
    exit 1
fi

# Check org is initialized
if [[ ! -f "$ORG_DIR/live/quinn.db" ]]; then
    echo "Org not initialized properly. Run ./cleanup.sh then ./setup.sh"
    exit 1
fi

# Start the org
echo "Starting org..."
"$QN" --org-path "$ORG_DIR" org start

echo
echo "=== Org Started ==="
echo

# Show status
echo "Current status:"
"$QN" --org-path "$ORG_DIR" org status

echo
echo "Next steps:"
echo "  ./observe.sh    - Watch the CEO"
echo "  ./cleanup.sh    - Stop and clean up"
