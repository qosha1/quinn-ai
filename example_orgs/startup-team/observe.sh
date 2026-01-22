#!/usr/bin/env bash
# Observe the startup-team org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/org"
QN="$SCRIPT_DIR/../common/qn"

echo "=== Startup Team: Observe ==="
echo

# Check org exists
if [[ ! -d "$ORG_DIR" ]]; then
    echo "Org not found. Run ./setup.sh first."
    exit 1
fi

# Show status
echo "--- Org Status ---"
"$QN" --org-path "$ORG_DIR" org status

echo
echo "--- Org Chart ---"
cat "$ORG_DIR/org-chart/current.yaml" 2>/dev/null || echo "(not found)"

echo
echo "--- Workers ---"
sqlite3 -header -column "$ORG_DIR/live/quinn.db" \
    "SELECT id, name, role, lifecycle_status, runtime_status FROM workers;" 2>/dev/null || echo "(no workers)"

echo
echo "--- Recent Messages ---"
sqlite3 -header -column "$ORG_DIR/live/quinn.db" \
    "SELECT substr(id, 1, 12) as id, channel_id, sender_id, substr(content, 1, 50) as content FROM messages ORDER BY created_at DESC LIMIT 10;" 2>/dev/null || echo "(no messages)"

echo
echo "--- Live Sessions ---"
tmux list-sessions 2>/dev/null | grep -iE "startup|alice|bob|ceo|engineer" || echo "(no sessions found)"

echo
echo "Tip: To watch a worker's session:"
echo "  tmux attach -t <session-name>"
echo
echo "Press Ctrl+C to stop observing"
