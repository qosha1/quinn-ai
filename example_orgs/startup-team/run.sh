#!/usr/bin/env bash
# Start the startup-team org and send initial goal
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/org"
QN="$SCRIPT_DIR/../common/qn"

echo "=== Startup Team: Run ==="
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
echo "Org is running. Sending initial goal to CEO..."
echo

# Get CEO worker ID
CEO_ID=$(sqlite3 "$ORG_DIR/live/quinn.db" "SELECT id FROM workers WHERE role='CEO' LIMIT 1;" 2>/dev/null)

if [[ -z "$CEO_ID" ]]; then
    echo "Error: Could not find CEO worker"
    exit 1
fi

# Send initial goal via the CEO's channel
# First, create a channel for board communications if it doesn't exist
sqlite3 "$ORG_DIR/live/quinn.db" <<EOF
INSERT OR IGNORE INTO channels (id, name, type, creator_id, description)
VALUES ('board-channel', 'Board Communications', 'announcement', 'board', 'Strategic directives from the board');

INSERT OR IGNORE INTO channel_subscriptions (channel_id, worker_id, role, subscribed_at)
VALUES ('board-channel', '$CEO_ID', 'member', datetime('now'));
EOF

# Send the initial goal as a message
GOAL_MESSAGE="BOARD DIRECTIVE: Build a landing page for our product. This should be a simple, clean page that explains what we do. You have budget to hire one engineer if needed. Report back when complete."

sqlite3 "$ORG_DIR/live/quinn.db" <<EOF
INSERT INTO messages (id, channel_id, sender_id, sender_type, content, priority, created_at)
VALUES (
    'goal-' || hex(randomblob(4)),
    'board-channel',
    'board',
    'system',
    '$GOAL_MESSAGE',
    1,
    datetime('now')
);
EOF

echo "Goal sent to CEO (Alice):"
echo "  $GOAL_MESSAGE"
echo

# Show status
echo "Current status:"
"$QN" --org-path "$ORG_DIR" org status

echo
echo "Next steps:"
echo "  ./observe.sh    - Watch the CEO hire and delegate"
echo "  ./cleanup.sh    - Stop and clean up"
