#!/usr/bin/env bash
# Observe the hello-world org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/org"
QN="$SCRIPT_DIR/../common/qn"

echo "=== Hello World: Observe ==="
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
echo "--- Live Sessions ---"
tmux list-sessions 2>/dev/null | grep -i "hello-world\|alice\|ceo" || echo "(no sessions found)"

echo
echo "--- Database Stats ---"
if [[ -f "$ORG_DIR/live/quinn.db" ]]; then
    echo "Workers: $(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT COUNT(*) FROM workers;" 2>/dev/null || echo "?")"
    echo "Messages: $(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT COUNT(*) FROM messages;" 2>/dev/null || echo "?")"
    echo "Channels: $(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT COUNT(*) FROM channels;" 2>/dev/null || echo "?")"
fi

echo
echo "Press Ctrl+C to stop observing"
echo "To attach to CEO session: tmux attach -t <session-name>"
