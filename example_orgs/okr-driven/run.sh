#!/usr/bin/env bash
# Start the okr-driven org and activate OKRs
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/org"
QN="$SCRIPT_DIR/../common/qn"

echo "=== OKR-Driven: Run ==="
echo

# Check org exists
if [[ ! -d "$ORG_DIR" ]]; then
    echo "Org not found. Run ./setup.sh first."
    exit 1
fi

# Start the org
echo "Starting org..."
"$QN" --org-path "$ORG_DIR" org start

echo
echo "Org is running. Sending OKR directive to CEO..."
echo

# Get CEO worker ID
CEO_ID=$(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT id FROM workers WHERE role='CEO' LIMIT 1;" 2>/dev/null)

if [[ -z "$CEO_ID" ]]; then
    echo "Error: Could not find CEO worker"
    exit 1
fi

# Create board channel and subscribe CEO
sqlite3 "$ORG_DIR/live/quinn.db" <<EOF
INSERT OR IGNORE INTO channels (id, name, type, team_id)
VALUES ('board-channel', 'Board Communications', 'topic', NULL);

INSERT OR IGNORE INTO channel_subscriptions (channel_id, worker_id, subscribed_at)
VALUES ('board-channel', '$CEO_ID', datetime('now'));
EOF

# Read OKR file and send as directive
OKR_FILE="$ORG_DIR/okrs/q1-2025.yaml"
if [[ -f "$OKR_FILE" ]]; then
    OKR_SUMMARY=$(cat << 'DIRECTIVE'
BOARD DIRECTIVE: Q1 2025 Strategic Objectives

OBJECTIVE: Establish market presence in Q1
Timeframe: Jan 1 - Mar 31, 2025

KEY RESULTS:
1. [KR-MVP] Launch MVP to public by Feb 15
   - Owner: CEO
   - Type: Milestone

2. [KR-USERS] Acquire 100 active beta users
   - Owner: Marketing (hire if needed)
   - Type: Metric (current: 0/100)

3. [KR-NPS] Achieve NPS score > 40
   - Owner: Product (hire if needed)
   - Type: Metric

INSTRUCTIONS:
- Break each KR into actionable work items
- Hire necessary team members within budget
- Report weekly progress on each KR
- Escalate blockers immediately

Budget authorized: $10,000/month for AI workers
DIRECTIVE
)

    sqlite3 "$ORG_DIR/live/quinn.db" <<EOF
PRAGMA trusted_schema = ON;
INSERT INTO messages (id, channel_id, from_worker_id, content, priority, created_at)
VALUES (
    'okr-' || hex(randomblob(4)),
    'board-channel',
    '$CEO_ID',
    '$OKR_SUMMARY',
    0,
    datetime('now')
);
EOF

    echo "OKR directive sent to CEO:"
    echo "$OKR_SUMMARY" | head -20
    echo "..."
else
    echo "Warning: OKR file not found at $OKR_FILE"
fi

echo
echo "Current status:"
"$QN" --org-path "$ORG_DIR" org status

echo
echo "Next steps:"
echo "  ./observe.sh    - Watch OKR cascade and progress"
echo "  ./cleanup.sh    - Stop and clean up"
