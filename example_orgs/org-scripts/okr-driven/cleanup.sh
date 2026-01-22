#!/usr/bin/env bash
# Clean up the okr-driven org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/okr-driven"

echo "=== OKR-Driven: Cleanup ==="
echo

# Pass through any flags (--label, --no-archive, etc.) to common cleanup
"$SCRIPT_DIR/../common/cleanup.sh" --force "$@" "$ORG_DIR"

echo
echo "Ready for a fresh start with ./setup.sh"
