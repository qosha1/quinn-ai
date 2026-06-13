#!/usr/bin/env bash
# Clean up the start-simpli org.
#
# Tears down the QuinnAI org state only. The host monorepo at
# /Users/qosha/Repos/start-simpli is NEVER touched by cleanup.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/start-simpli"

echo "=== start-simpli: Cleanup ==="
echo

# Pass through any flags (--label, --no-archive, etc.) to common cleanup
"$SCRIPT_DIR/../common/cleanup.sh" --force "$@" "$ORG_DIR"

echo
echo "Ready for a fresh start with ./setup.sh"
