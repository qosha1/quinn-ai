#!/usr/bin/env bash
# Initialize the start-simpli host-mode org from org.yml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG_DIR="$SCRIPT_DIR/../../generated-orgs/start-simpli"
QN="$SCRIPT_DIR/../common/qn"
ORG_SPEC="$SCRIPT_DIR/org.yml"
PROJECT_ROOT="/Users/qosha/Repos/start-simpli"

echo "=== start-simpli: Setup ==="
echo

# Check prerequisites — setup just runs 'qn org init' (no LLM session
# spawn), so skip the provider API-key check here. run.sh re-runs
# check-env.sh (full mode) when it's actually about to spawn sessions.
"$SCRIPT_DIR/../common/check-env.sh" --setup-only || {
    echo
    echo "Fix the issues above before continuing."
    exit 1
}

echo

# This is a HOST-MODE org: it operates on the live start-simpli monorepo,
# not a generated scratch project. Make sure the host repo is present.
if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Host project not found at: $PROJECT_ROOT"
    echo "This org runs against the start-simpli monorepo. Clone it there first."
    exit 1
fi

# Check if already initialized
if [[ -d "$ORG_DIR" ]]; then
    echo "Org already exists at: $ORG_DIR"
    echo "Run ./cleanup.sh first to reset."
    exit 1
fi

# Initialize the org from the declarative spec.
#
# NOTE: `qn org init --from <spec>` is provided by the org.yml loader being
# built in parallel (bead quinn-ai-a3pg.2.4.3). Until that loader lands, this
# invocation will fail; the spec in org.yml is the source of truth in the
# meantime. Once the loader is available this is the single setup entrypoint.
echo "Initializing simpli org from org.yml (host mode -> $PROJECT_ROOT)..."
"$QN" --org-path "$ORG_DIR" org init --from "$ORG_SPEC"

echo
echo "=== Setup Complete ==="
echo
echo "Org created at: $ORG_DIR"
echo "Host project:   $PROJECT_ROOT"
echo "CEO:            Quinn"
echo
echo "Declared structure:"
echo "  - core-infra (Dana, Director) + backend/platform/package engineers"
echo "  - raise  (Remy, Lead)  [self-forming]"
echo "  - market (Mara, Lead)  [self-forming]"
echo
echo "Next: Run ./run.sh to start the org and kick off the OKRs."
