#!/usr/bin/env bash
# Archive an org's state for historical evaluation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HISTORY_DIR="$SCRIPT_DIR/../../run-history"

usage() {
    echo "Usage: $0 <org-path> [label]"
    echo
    echo "Archive an org's state for later evaluation."
    echo
    echo "Arguments:"
    echo "  org-path    Path to the org directory"
    echo "  label       Optional label for this run (default: timestamp)"
    echo
    echo "Output:"
    echo "  Creates archive in run-history/<org-name>/<timestamp>[-label]/"
    echo
    echo "Example:"
    echo "  $0 ./generated-orgs/hello-world"
    echo "  $0 ./generated-orgs/hello-world 'first-successful-run'"
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

ORG_PATH="$1"
LABEL="${2:-}"

# Convert to absolute path
ORG_PATH="$(cd "$ORG_PATH" 2>/dev/null && pwd)" || {
    echo "Error: Org path does not exist: $1"
    exit 1
}

# Check if org has database
if [[ ! -f "$ORG_PATH/live/quinn.db" ]]; then
    echo "Error: No database found at $ORG_PATH/live/quinn.db"
    exit 1
fi

# Create archive directory
org_name=$(basename "$ORG_PATH")
timestamp=$(date +%Y%m%d-%H%M%S)
if [[ -n "$LABEL" ]]; then
    archive_name="${timestamp}-${LABEL}"
else
    archive_name="$timestamp"
fi
archive_dir="$HISTORY_DIR/$org_name/$archive_name"

mkdir -p "$archive_dir"
echo "Archiving $org_name to: $archive_dir"

# 1. Copy org chart
if [[ -f "$ORG_PATH/org-chart/current.yaml" ]]; then
    cp "$ORG_PATH/org-chart/current.yaml" "$archive_dir/org-chart.yaml"
    echo "  ✓ Org chart"
fi

# 2. Export database tables to readable format
DB="$ORG_PATH/live/quinn.db"

# Org state
sqlite3 -header -csv "$DB" "SELECT * FROM org_state;" > "$archive_dir/org-state.csv" 2>/dev/null || true
echo "  ✓ Org state"

# Workers
sqlite3 -header -csv "$DB" "SELECT * FROM workers;" > "$archive_dir/workers.csv" 2>/dev/null || true
echo "  ✓ Workers"

# Worker state (runtime status)
sqlite3 -header -csv "$DB" "SELECT * FROM worker_state;" > "$archive_dir/worker-state.csv" 2>/dev/null || true
echo "  ✓ Worker state"

# Messages (full content)
sqlite3 -header -csv "$DB" "SELECT m.id, m.channel_id, m.from_worker_id, c.name as channel_name, m.content, m.priority, m.created_at FROM messages m LEFT JOIN channels c ON m.channel_id = c.id ORDER BY m.created_at;" > "$archive_dir/messages.csv" 2>/dev/null || true
echo "  ✓ Messages"

# Channels
sqlite3 -header -csv "$DB" "SELECT * FROM channels;" > "$archive_dir/channels.csv" 2>/dev/null || true
echo "  ✓ Channels"

# Teams
sqlite3 -header -csv "$DB" "SELECT * FROM teams;" > "$archive_dir/teams.csv" 2>/dev/null || true
echo "  ✓ Teams"

# OKRs if present
sqlite3 -header -csv "$DB" "SELECT * FROM okrs;" > "$archive_dir/okrs.csv" 2>/dev/null || true
if [[ -s "$archive_dir/okrs.csv" ]]; then
    echo "  ✓ OKRs"
fi

# Budget transactions
sqlite3 -header -csv "$DB" "SELECT * FROM budget_transactions;" > "$archive_dir/budget-transactions.csv" 2>/dev/null || true
if [[ -s "$archive_dir/budget-transactions.csv" ]]; then
    echo "  ✓ Budget transactions"
fi

# 3. Copy the full database for detailed analysis
cp "$DB" "$archive_dir/quinn.db"
echo "  ✓ Database snapshot"

# 4. Copy OKR files if present
if [[ -d "$ORG_PATH/okrs" ]]; then
    cp -r "$ORG_PATH/okrs" "$archive_dir/okrs"
    echo "  ✓ OKR files"
fi

# 5. Create a summary file
cat > "$archive_dir/summary.txt" << EOF
Org Archive: $org_name
Timestamp: $(date)
Label: ${LABEL:-none}

--- Org Status ---
$(sqlite3 "$DB" "SELECT key, value FROM org_state;" 2>/dev/null || echo "N/A")

--- Worker Count ---
$(sqlite3 "$DB" "SELECT COUNT(*) FROM workers;" 2>/dev/null || echo "0")

--- Message Count ---
$(sqlite3 "$DB" "SELECT COUNT(*) FROM messages;" 2>/dev/null || echo "0")

--- Workers ---
$(sqlite3 -header -column "$DB" "SELECT id, name, role, status FROM workers;" 2>/dev/null || echo "None")

--- Recent Messages ---
$(sqlite3 -header -column "$DB" "SELECT substr(id,1,12) as id, from_worker_id, substr(content,1,60) as content FROM messages ORDER BY created_at DESC LIMIT 10;" 2>/dev/null || echo "None")
EOF
echo "  ✓ Summary"

echo
echo "Archive complete: $archive_dir"
echo "View summary: cat $archive_dir/summary.txt"
