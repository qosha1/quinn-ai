#!/usr/bin/env bash
# Observe the start-simpli org.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/start-simpli"
QN="$SCRIPT_DIR/../common/qn"

echo "=== start-simpli: Observe ==="
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
echo "--- Teams ---"
sqlite3 -header -column "$ORG_DIR/live/quinn.db" \
    "SELECT id, name FROM teams;" 2>/dev/null || echo "(no teams)"

echo
echo "--- Workers ---"
sqlite3 -header -column "$ORG_DIR/live/quinn.db" \
    "SELECT w.id, w.name, w.role, w.status, ws.runtime_status FROM workers w LEFT JOIN worker_state ws ON w.id = ws.worker_id;" 2>/dev/null || echo "(no workers)"

echo
echo "--- Recent Messages ---"
sqlite3 -header -column "$ORG_DIR/live/quinn.db" \
    "SELECT substr(id, 1, 12) as id, channel_id, from_worker_id, substr(content, 1, 50) as content FROM messages ORDER BY created_at DESC LIMIT 10;" 2>/dev/null || echo "(no messages)"

echo
echo "--- Live Sessions ---"
# Get worker IDs from database and find their tmux sessions (named qn-wrkr-<hex>)
if [[ -f "$ORG_DIR/live/quinn.db" ]]; then
    worker_ids=$(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT id FROM workers;" 2>/dev/null)
    if [[ -n "$worker_ids" ]]; then
        # Build grep pattern from worker IDs (wrkr-xxx -> qn-wrkr-xxx)
        pattern=$(echo "$worker_ids" | sed 's/wrkr-/qn-wrkr-/' | tr '\n' '|' | sed 's/|$//')
        tmux list-sessions 2>/dev/null | grep -E "$pattern" || echo "(no sessions found)"
    else
        echo "(no workers in database)"
    fi
else
    echo "(database not found)"
fi

echo
echo "Tip: To watch a worker's session:"
echo "  tmux attach -t <session-name>"
echo
echo "Press Ctrl+C to stop observing"
