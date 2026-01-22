#!/usr/bin/env bash
# Observe the okr-driven org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/org"

echo "=== OKR-Driven: Observe ==="
echo

# Check org exists
if [[ ! -d "$ORG_DIR" ]]; then
    echo "Org not found. Run ./setup.sh first."
    exit 1
fi

# Show status
echo "--- Org Status ---"
qn org status --org-path "$ORG_DIR"

echo
echo "--- OKR Status ---"
if [[ -f "$ORG_DIR/okrs/q1-2025.yaml" ]]; then
    echo "Q1 2025 Objective: Establish market presence"
    echo
    # Simple YAML parsing for display
    grep -E "^\s+title:|^\s+progress:|^\s+status:" "$ORG_DIR/okrs/q1-2025.yaml" 2>/dev/null | \
        sed 's/^[ ]*/  /' || echo "(parse error)"
else
    echo "(no OKRs found)"
fi

echo
echo "--- Org Chart ---"
cat "$ORG_DIR/org-chart/current.yaml" 2>/dev/null || echo "(not found)"

echo
echo "--- Workers ---"
sqlite3 -header -column "$ORG_DIR/live/quinn.db" \
    "SELECT id, name, role, lifecycle_status FROM workers;" 2>/dev/null || echo "(no workers)"

echo
echo "--- Recent Messages ---"
sqlite3 -header -column "$ORG_DIR/live/quinn.db" \
    "SELECT substr(id, 1, 12) as id, sender_id, substr(content, 1, 60) as content FROM messages ORDER BY created_at DESC LIMIT 5;" 2>/dev/null || echo "(no messages)"

echo
echo "--- Live Sessions ---"
tmux list-sessions 2>/dev/null | grep -iE "okr|alice|ceo" || echo "(no sessions found)"

echo
echo "Tip: Check OKR progress with:"
echo "  cat org/okrs/q1-2025.yaml"
echo
echo "Press Ctrl+C to stop observing"
