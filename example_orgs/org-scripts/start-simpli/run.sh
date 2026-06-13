#!/usr/bin/env bash
# Start the start-simpli org and send the kickoff directive to the CEO.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/start-simpli"
QN="$SCRIPT_DIR/../common/qn"

echo "=== start-simpli: Run ==="
echo

# Check org exists
if [[ ! -d "$ORG_DIR" ]]; then
    echo "Org not found. Run ./setup.sh first."
    exit 1
fi

# Check API key is set (required to spawn the CEO session)
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "Error: ANTHROPIC_API_KEY is not set."
    echo
    echo "To run this example, you need an Anthropic API key."
    echo "Set it with: export ANTHROPIC_API_KEY=\"sk-ant-...\""
    echo
    echo "Or source your env file: set -a && source .envs/.local/.django && set +a"
    exit 1
fi

# Start the org
echo "Starting org..."
"$QN" --org-path "$ORG_DIR" org start

echo
echo "Org is running. Sending kickoff directive to CEO..."
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

# Kickoff directive. Core Infra is declared; the app groups (raise, market)
# self-form, so the directive points the Leads at discovery before execution.
DIRECTIVE=$(cat << 'DIRECTIVE'
BOARD DIRECTIVE: start-simpli platform iteration

We operate on the start-simpli monorepo (auth-web, start-simpli-api, and the
shared packages/@startsimpli/* packages), plus the customer-facing apps under
apps/ (raise, market) and the foundry control plane.

STRUCTURE:
- Core Infra (Dana, Director) owns the auth host, the Django/DRF API, and the
  shared @startsimpli/* packages. This team is already declared.
- App groups raise (Remy) and market (Mara) self-form. Each Lead should run
  discovery first, then hire app-engineer / app-designer ICs as needed.

OKRs:
1. Platform reliability & shared-package health (Core Infra / Dana)
   - shared package test coverage -> 80%
   - API p95 latency -> 300ms
2. Ship raise iteration (raise / Remy)
   - conversion rate -> 5%
3. Ship market iteration (market / Mara)
   - qualified leads -> 100

INSTRUCTIONS:
- Honor the simpli profile conventions (shared packages over app src,
  camelCase on the wire, TypeScript must compile, MCP browser verification for
  UI, server-side pagination, generic data models, foundry for tenant stacks).
- Break each KR into work items and delegate within budget.
- Report progress per KR.
DIRECTIVE
)

sqlite3 "$ORG_DIR/live/quinn.db" <<EOF
PRAGMA trusted_schema = ON;
INSERT INTO messages (id, channel_id, from_worker_id, content, priority, created_at)
VALUES (
    'kickoff-' || hex(randomblob(4)),
    'board-channel',
    '$CEO_ID',
    '$DIRECTIVE',
    0,
    datetime('now')
);
EOF

echo "Kickoff directive sent to CEO (Quinn):"
echo "$DIRECTIVE" | head -20
echo "..."
echo

# Show status
echo "Current status:"
"$QN" --org-path "$ORG_DIR" org status

echo
echo "Next steps:"
echo "  ./observe.sh    - Watch Core Infra work and the app groups self-form"
echo "  ./cleanup.sh    - Stop and clean up"
