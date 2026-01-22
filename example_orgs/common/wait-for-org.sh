#!/usr/bin/env bash
# Wait for org to reach a desired state
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 [OPTIONS] <org-path> <desired-state>"
    echo
    echo "Wait for an org to reach a specific state."
    echo
    echo "States: initialized, running, stopped"
    echo
    echo "Options:"
    echo "  -t, --timeout SECONDS    Max time to wait (default: 60)"
    echo "  -i, --interval SECONDS   Check interval (default: 2)"
    echo "  -h, --help               Show this help"
    echo
    echo "Example:"
    echo "  $0 ./my-org running"
    echo "  $0 --timeout 120 ./my-org running"
}

# Defaults
TIMEOUT=60
INTERVAL=2

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -i|--interval)
            INTERVAL="$2"
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

if [[ $# -lt 2 ]]; then
    usage
    exit 1
fi

ORG_PATH="$1"
DESIRED_STATE="$2"

# Validate desired state
case "$DESIRED_STATE" in
    initialized|running|stopped)
        ;;
    *)
        echo "Error: Invalid state '$DESIRED_STATE'"
        echo "Valid states: initialized, running, stopped"
        exit 1
        ;;
esac

echo "Waiting for org at $ORG_PATH to reach '$DESIRED_STATE' state..."
echo "Timeout: ${TIMEOUT}s, Check interval: ${INTERVAL}s"

start_time=$(date +%s)
while true; do
    # Check current state
    current_state=$(qn org status --org-path "$ORG_PATH" 2>/dev/null | grep "Status:" | awk '{print $2}' || echo "unknown")

    if [[ "$current_state" == "$DESIRED_STATE" ]]; then
        echo "Org reached '$DESIRED_STATE' state!"
        exit 0
    fi

    # Check timeout
    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    if [[ $elapsed -ge $TIMEOUT ]]; then
        echo "Timeout after ${elapsed}s. Current state: $current_state"
        exit 1
    fi

    echo "  State: $current_state (waiting... ${elapsed}s/${TIMEOUT}s)"
    sleep "$INTERVAL"
done
