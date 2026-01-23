#!/usr/bin/env bash
# Observe the hello-world org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/hello-world"
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
echo "--- Database Stats ---"
if [[ -f "$ORG_DIR/live/quinn.db" ]]; then
    echo "Workers: $(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT COUNT(*) FROM workers;" 2>/dev/null || echo "?")"
    echo "Messages: $(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT COUNT(*) FROM messages;" 2>/dev/null || echo "?")"
    echo "Channels: $(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT COUNT(*) FROM channels;" 2>/dev/null || echo "?")"
fi

echo
echo "--- Budget Status ---"
if [[ -f "$ORG_DIR/live/quinn.db" ]]; then
    # Show budget pool info
    pool_info=$(sqlite3 "$ORG_DIR/live/quinn.db" \
        "SELECT name, total_credits FROM budget_pools LIMIT 1;" 2>/dev/null)
    if [[ -n "$pool_info" ]]; then
        pool_name=$(echo "$pool_info" | cut -d'|' -f1)
        pool_total=$(echo "$pool_info" | cut -d'|' -f2)
        echo "Pool: $pool_name ($pool_total credits)"
    fi

    # Show CEO budget
    ceo_budget=$(sqlite3 "$ORG_DIR/live/quinn.db" \
        "SELECT w.name, ba.allocated_credits,
                ABS(COALESCE((SELECT SUM(amount) FROM budget_transactions WHERE worker_id = w.id AND type = 'spend'), 0)) as spent
         FROM workers w
         JOIN budget_allocations ba ON ba.worker_id = w.id
         WHERE w.manager_id IS NULL
         LIMIT 1;" 2>/dev/null)
    if [[ -n "$ceo_budget" ]]; then
        ceo_name=$(echo "$ceo_budget" | cut -d'|' -f1)
        allocated=$(echo "$ceo_budget" | cut -d'|' -f2)
        spent=$(echo "$ceo_budget" | cut -d'|' -f3)
        available=$(echo "$allocated - $spent" | bc 2>/dev/null || echo "?")
        echo "$ceo_name: $allocated allocated, $spent spent, $available available"
    else
        echo "(no budget allocations found)"
    fi
else
    echo "(database not found)"
fi

echo
echo "Press Ctrl+C to stop observing"
echo "To attach to CEO session: tmux attach -t <session-name>"
