#!/usr/bin/env bash
# Clean up an org - stop sessions and remove folder
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 [OPTIONS] <org-path>"
    echo
    echo "Clean up an org by stopping sessions and removing its folder."
    echo
    echo "Options:"
    echo "  -f, --force    Skip confirmation"
    echo "  -k, --keep     Stop org but keep folder"
    echo "  -h, --help     Show this help"
    echo
    echo "Example:"
    echo "  $0 ./my-org"
    echo "  $0 --force ./my-org"
}

FORCE=false
KEEP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--force)
            FORCE=true
            shift
            ;;
        -k|--keep)
            KEEP=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

ORG_PATH="$1"

# Convert to absolute path
ORG_PATH="$(cd "$ORG_PATH" 2>/dev/null && pwd)" || {
    echo "Org path does not exist: $1"
    exit 0  # Not an error - nothing to clean
}

echo "Cleaning up org at: $ORG_PATH"

# Confirm unless forced
if [[ "$FORCE" != "true" ]]; then
    read -p "This will stop all sessions and delete the org. Continue? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
fi

# Try to stop the org gracefully
if [[ -f "$ORG_PATH/live/quinn.db" ]]; then
    echo "Stopping org..."
    qn org stop --org-path "$ORG_PATH" 2>/dev/null || true
fi

# Kill any tmux sessions for this org
org_name=$(basename "$ORG_PATH")
echo "Killing tmux sessions for $org_name..."
tmux list-sessions 2>/dev/null | grep "$org_name" | cut -d: -f1 | while read session; do
    echo "  Killing session: $session"
    tmux kill-session -t "$session" 2>/dev/null || true
done

# Remove folder unless --keep
if [[ "$KEEP" != "true" ]]; then
    echo "Removing org folder..."
    rm -rf "$ORG_PATH"
    echo "Cleanup complete. Org removed."
else
    echo "Cleanup complete. Org folder kept at: $ORG_PATH"
fi
