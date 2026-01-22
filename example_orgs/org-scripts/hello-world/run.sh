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

# Check API key is set (required to spawn CEO session)
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "Error: ANTHROPIC_API_KEY is not set."
    echo
    echo "To run this example, you need an Anthropic API key."
    echo "Set it with: export ANTHROPIC_API_KEY=\"sk-ant-...\""
    echo
    echo "Or source your env file: set -a && source .envs/.local/.django && set +a"
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
