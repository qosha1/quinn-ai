#!/usr/bin/env bash
# Clean up the startup-team org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/startup-team"

echo "=== Startup Team: Cleanup ==="
echo

# Pass through any flags (--label, --no-archive, etc.) to common cleanup
"$SCRIPT_DIR/../common/cleanup.sh" --force "$@" "$ORG_DIR"

echo
echo "Ready for a fresh start with ./setup.sh"
