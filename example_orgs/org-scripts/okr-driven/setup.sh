#!/usr/bin/env bash
# Initialize the okr-driven org
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/okr-driven"
QN="$SCRIPT_DIR/../common/qn"

echo "=== OKR-Driven: Setup ==="
echo

# Check prerequisites
"$SCRIPT_DIR/../common/check-env.sh" || {
    echo
    echo "Fix the issues above before continuing."
    exit 1
}

echo

# Check if already initialized
if [[ -d "$ORG_DIR" ]]; then
    echo "Org already exists at: $ORG_DIR"
    echo "Run ./cleanup.sh first to reset."
    exit 1
fi

# Initialize the org
echo "Initializing org with CEO..."
"$QN" --org-path "$ORG_DIR" org init --ceo-name "Alice" --ceo-role "CEO"

# Copy custom configs
if [[ -f "$SCRIPT_DIR/config/worker-templates.yaml" ]]; then
    echo "Copying worker templates..."
    cp "$SCRIPT_DIR/config/worker-templates.yaml" "$ORG_DIR/config/"
fi

# Create OKR directory and sample OKRs
echo "Setting up OKR structure..."
mkdir -p "$ORG_DIR/okrs"
cp "$SCRIPT_DIR/okrs/q1-2025.yaml" "$ORG_DIR/okrs/" 2>/dev/null || \
    cat > "$ORG_DIR/okrs/q1-2025.yaml" << 'EOF'
# Q1 2025 OKRs
objective:
  id: obj-q1-market
  title: "Establish market presence in Q1"
  description: "Get our product into users' hands and prove value"
  owner: ceo
  timeframe:
    start: 2025-01-01
    end: 2025-03-31
  status: active

key_results:
  - id: kr-mvp-launch
    title: "Launch MVP to public"
    type: milestone
    target_date: 2025-02-15
    status: not_started
    owner: ceo
    progress: 0

  - id: kr-beta-users
    title: "100 active beta users"
    type: metric
    metric_name: active_users
    target_value: 100
    current_value: 0
    status: not_started
    owner: marketing
    progress: 0

  - id: kr-nps
    title: "NPS score > 40"
    type: metric
    metric_name: nps_score
    target_value: 40
    current_value: null
    status: not_started
    owner: product
    progress: 0
EOF

echo
echo "=== Setup Complete ==="
echo
echo "Org created at: $ORG_DIR"
echo "CEO: Alice"
echo
echo "OKR loaded: Q1 2025 - Establish market presence"
echo "  KR1: Launch MVP by Feb 15"
echo "  KR2: 100 beta users"
echo "  KR3: NPS > 40"
echo
echo "Next: Run ./run.sh to start and activate OKRs"
