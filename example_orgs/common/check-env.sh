#!/usr/bin/env bash
# Check environment prerequisites for QuinnAI examples
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Checking QuinnAI prerequisites..."
echo

# Check for required commands
check_command() {
    local cmd=$1
    local install_hint=$2
    if command -v "$cmd" &> /dev/null; then
        echo "[OK] $cmd found: $(command -v "$cmd")"
        return 0
    else
        echo "[MISSING] $cmd not found"
        echo "         Install: $install_hint"
        return 1
    fi
}

errors=0

# Required commands
check_command "tmux" "brew install tmux (macOS) or apt install tmux (Linux)" || ((errors++))
check_command "python3" "brew install python3 (macOS) or apt install python3 (Linux)" || ((errors++))

echo

# Check for qn CLI
if command -v qn &> /dev/null; then
    echo "[OK] qn CLI found: $(command -v qn)"
else
    echo "[INFO] qn CLI not in PATH"
    echo "       Run: ./common/install-cli.sh"
    echo "       Or:  cd ../cli && pip install -e ."
fi

echo

# Check API keys
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "[OK] ANTHROPIC_API_KEY is set"
else
    echo "[MISSING] ANTHROPIC_API_KEY not set"
    echo "          Run: export ANTHROPIC_API_KEY=\"sk-ant-...\""
    ((errors++))
fi

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    echo "[OK] OPENAI_API_KEY is set (optional)"
else
    echo "[INFO] OPENAI_API_KEY not set (optional for OpenAI provider)"
fi

echo

# Summary
if [[ $errors -eq 0 ]]; then
    echo "All prerequisites satisfied!"
    echo "You're ready to run the examples."
    exit 0
else
    echo "Found $errors issue(s) to resolve before running examples."
    exit 1
fi
