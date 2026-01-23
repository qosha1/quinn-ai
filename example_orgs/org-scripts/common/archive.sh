#!/usr/bin/env bash
# Archive an org's state for historical evaluation
#
# Creates a standardized archive with:
# - CSV exports of all database tables
# - Database snapshot (quinn.db copy)
# - Org chart snapshot
# - systemeval-results.csv for consistent metrics comparison
#
# The systemeval-results.csv is the key output for comparing runs:
# - Consistent schema across ALL example orgs (hello-world, startup-team, okr-driven)
# - Metrics include: workers, messages, budget, tokens, OKRs, duration
# - Parsed by tests/systemeval_utils.py for programmatic validation
#
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
    echo "  Key files:"
    echo "    systemeval-results.csv  - Standardized metrics for comparison"
    echo "    summary.txt             - Human-readable summary"
    echo "    quinn.db                - Database snapshot"
    echo "    *.csv                   - Table exports (workers, messages, etc.)"
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
$(sqlite3 -header -column "$DB" "SELECT status, ceo_worker_id, started_at, stopped_at FROM org_state WHERE id='default';" 2>/dev/null || echo "N/A")

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

# 6. Generate standardized systemeval-results.csv
# This CSV is consistent across ALL example org runs for comparison and aggregation

# Determine example type based on org name
case "$org_name" in
    hello-world) example_type="basic" ;;
    startup-team) example_type="team" ;;
    okr-driven) example_type="okr" ;;
    *) example_type="unknown" ;;
esac

# Extract metrics from database
org_status=$(sqlite3 "$DB" "SELECT status FROM org_state WHERE id='default';" 2>/dev/null || echo "unknown")
started_at=$(sqlite3 "$DB" "SELECT started_at FROM org_state WHERE id='default';" 2>/dev/null || echo "")
stopped_at=$(sqlite3 "$DB" "SELECT stopped_at FROM org_state WHERE id='default';" 2>/dev/null || echo "")

# Calculate duration (-1 if can't compute)
if [[ -n "$started_at" && -n "$stopped_at" ]]; then
    start_epoch=$(date -j -f "%Y-%m-%d %H:%M:%S" "$started_at" "+%s" 2>/dev/null || echo "")
    stop_epoch=$(date -j -f "%Y-%m-%d %H:%M:%S" "$stopped_at" "+%s" 2>/dev/null || echo "")
    if [[ -n "$start_epoch" && -n "$stop_epoch" ]]; then
        duration_seconds=$((stop_epoch - start_epoch))
    else
        duration_seconds=-1
    fi
else
    duration_seconds=-1
fi

# Worker counts
worker_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM workers;" 2>/dev/null || echo "0")
worker_active_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM workers WHERE status='active';" 2>/dev/null || echo "0")
worker_terminated_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM workers WHERE status='terminated';" 2>/dev/null || echo "0")

# Runtime metrics from worker_state
tasks_completed=$(sqlite3 "$DB" "SELECT COALESCE(SUM(tasks_completed), 0) FROM worker_state;" 2>/dev/null || echo "0")
tasks_failed=$(sqlite3 "$DB" "SELECT COALESCE(SUM(tasks_failed), 0) FROM worker_state;" 2>/dev/null || echo "0")

# Communication metrics
message_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM messages;" 2>/dev/null || echo "0")
channel_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM channels;" 2>/dev/null || echo "0")

# Team and OKR metrics
team_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM teams;" 2>/dev/null || echo "0")
okr_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM okrs;" 2>/dev/null || echo "0")
okr_completed_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM okrs WHERE status='completed';" 2>/dev/null || echo "0")

# Budget metrics
total_spent=$(sqlite3 "$DB" "SELECT COALESCE(printf('%.4f', ABS(SUM(amount))), '0.0000') FROM budget_transactions WHERE type='spend';" 2>/dev/null || echo "0.0000")
total_tokens_in=$(sqlite3 "$DB" "SELECT COALESCE(SUM(input_tokens), 0) FROM budget_transactions;" 2>/dev/null || echo "0")
total_tokens_out=$(sqlite3 "$DB" "SELECT COALESCE(SUM(output_tokens), 0) FROM budget_transactions;" 2>/dev/null || echo "0")

# Session count
session_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sessions;" 2>/dev/null || echo "0")

# ISO8601 timestamp
iso_timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Write CSV with header
cat > "$archive_dir/systemeval-results.csv" << EOF
run_id,org_name,example_type,timestamp,label,duration_seconds,org_status,worker_count,worker_active_count,worker_terminated_count,tasks_completed,tasks_failed,message_count,channel_count,team_count,okr_count,okr_completed_count,total_spent,total_tokens_in,total_tokens_out,session_count
$archive_name,$org_name,$example_type,$iso_timestamp,${LABEL:-},$duration_seconds,$org_status,$worker_count,$worker_active_count,$worker_terminated_count,$tasks_completed,$tasks_failed,$message_count,$channel_count,$team_count,$okr_count,$okr_completed_count,$total_spent,$total_tokens_in,$total_tokens_out,$session_count
EOF
echo "  ✓ Systemeval results"

echo
echo "Archive complete: $archive_dir"
echo "View summary: cat $archive_dir/summary.txt"
