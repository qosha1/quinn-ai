#!/usr/bin/env bash
# Clean up the okr-driven org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/org"

echo "=== OKR-Driven: Cleanup ==="
echo

"$SCRIPT_DIR/../common/cleanup.sh" --force "$ORG_DIR"

echo
echo "Ready for a fresh start with ./setup.sh"
