#!/bin/bash
# Stop QuinnAI Organization gracefully

set -e

echo "🛑 Stopping QuinnAI Organization..."
echo ""

# Check if org is running
ORG_STATUS=$(qn --org-path . org status 2>&1)
if echo "$ORG_STATUS" | grep -q "Status: stopped"; then
    echo "✅ Organization is already stopped"
    exit 0
fi

# Stop the organization
qn --org-path . org stop

echo ""
echo "✅ Organization stopped"
