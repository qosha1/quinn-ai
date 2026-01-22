#!/usr/bin/env bash
# Clean up an org - archive, stop sessions, and remove folder
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 [OPTIONS] <org-path>"
    echo
    echo "Clean up an org by archiving state, stopping sessions, and removing its folder."
    echo
    echo "Options:"
    echo "  -f, --force       Skip confirmation"
    echo "  -k, --keep        Stop org but keep folder"
    echo "  -n, --no-archive  Skip archiving (default: archive before cleanup)"
    echo "  -l, --label TEXT  Label for the archive (default: timestamp only)"
    echo "  -h, --help        Show this help"
    echo
    echo "Example:"
    echo "  $0 ./my-org"
    echo "  $0 --force ./my-org"
    echo "  $0 --label 'successful-run' ./my-org"
    echo "  $0 --no-archive --force ./my-org"
}

FORCE=false
KEEP=false
ARCHIVE=true
LABEL=""

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
        -n|--no-archive)
            ARCHIVE=false
            shift
            ;;
        -l|--label)
            LABEL="$2"
            shift 2
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

# Archive before cleanup (unless --no-archive)
if [[ "$ARCHIVE" == "true" ]] && [[ -f "$ORG_PATH/live/quinn.db" ]]; then
    echo "Archiving org state..."
    if [[ -n "$LABEL" ]]; then
        "$SCRIPT_DIR/archive.sh" "$ORG_PATH" "$LABEL"
    else
        "$SCRIPT_DIR/archive.sh" "$ORG_PATH"
    fi
    echo
fi

# Try to stop the org gracefully
QN="$SCRIPT_DIR/qn"
if [[ -f "$ORG_PATH/live/quinn.db" ]]; then
    echo "Stopping org..."
    "$QN" --org-path "$ORG_PATH" org stop 2>/dev/null || true
fi

# Kill any tmux sessions for this org's workers
org_name=$(basename "$ORG_PATH")
echo "Killing tmux sessions for $org_name..."
if [[ -f "$ORG_PATH/live/quinn.db" ]]; then
    # Get worker IDs from database and kill their sessions
    # Worker IDs are like 'wrkr-87561a3a', session names are 'qn-wrkr-87561a3a'
    sqlite3 "$ORG_PATH/live/quinn.db" "SELECT id FROM workers;" 2>/dev/null | while read worker_id; do
        # Extract the hex part after 'wrkr-'
        hex_id="${worker_id#wrkr-}"
        session_name="qn-wrkr-$hex_id"
        if tmux has-session -t "$session_name" 2>/dev/null; then
            echo "  Killing session: $session_name"
            tmux kill-session -t "$session_name" 2>/dev/null || true
        fi
    done
fi

# Remove folder unless --keep
if [[ "$KEEP" != "true" ]]; then
    echo "Removing org folder..."
    rm -rf "$ORG_PATH"
    echo "Cleanup complete. Org removed."
else
    echo "Cleanup complete. Org folder kept at: $ORG_PATH"
fi
