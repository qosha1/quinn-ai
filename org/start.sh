#!/bin/bash
# Start QuinnAI Organization
# This script ensures the API key is set and starts the org

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 Starting QuinnAI Organization..."
echo ""

# Check if API key is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}❌ ERROR: ANTHROPIC_API_KEY is not set${NC}"
    echo ""
    echo "Please set your API key:"
    echo "  export ANTHROPIC_API_KEY='sk-ant-...'"
    echo ""
    echo "Or add it to your shell profile (~/.bashrc, ~/.zshrc):"
    echo "  echo 'export ANTHROPIC_API_KEY=\"sk-ant-...\"' >> ~/.zshrc"
    echo ""
    exit 1
fi

# Validate API key format
if [[ ! "$ANTHROPIC_API_KEY" =~ ^sk-ant- ]]; then
    echo -e "${YELLOW}⚠️  WARNING: API key doesn't look like an Anthropic key (should start with 'sk-ant-')${NC}"
    echo ""
fi

# Check if org is already running
ORG_STATUS=$(qn --org-path . org status 2>&1)
if echo "$ORG_STATUS" | grep -q "Status: running"; then
    echo -e "${YELLOW}⚠️  Organization is already running${NC}"
    echo ""
    echo "$ORG_STATUS"
    echo ""
    echo "To observe the CEO:"
    echo "  qn --org-path . org observe"
    exit 0
fi

# Start the organization
echo "Starting organization..."
echo ""
qn --org-path . org start

# Check status
echo ""
echo "✅ Organization started!"
echo ""
qn --org-path . org status

echo ""
echo "Next steps:"
echo "  📊 View OKRs:     bd list --label=okr"
echo "  📋 Ready work:    bd ready"
echo "  👀 Observe CEO:   qn --org-path . org observe"
echo "  🎯 Watch board:   qn --org-path . board ui"
