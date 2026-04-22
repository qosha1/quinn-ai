#!/usr/bin/env bash
set -euo pipefail

TTYD_PORT="${TTYD_PORT:-7681}"
SESSION_NAME="${BOARD_SESSION:-quinnai-board}"
NGROK=false

for arg in "$@"; do
  case $arg in
    --ngrok) NGROK=true ;;
    --port=*) TTYD_PORT="${arg#*=}" ;;
    --session=*) SESSION_NAME="${arg#*=}" ;;
  esac
done

# Require tmux
if ! command -v tmux &>/dev/null; then
  echo "tmux not found. Install with: brew install tmux"
  exit 1
fi

# Require ttyd
if ! command -v ttyd &>/dev/null; then
  echo "ttyd not found. Install with: brew install ttyd"
  exit 1
fi

# Require qn
if ! command -v qn &>/dev/null; then
  echo "qn not found. Is the quinnai venv active?"
  exit 1
fi

# Kill any existing ttyd on this port
lsof -ti tcp:"$TTYD_PORT" | xargs kill -9 2>/dev/null || true

# Kill existing board tmux session if any
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Create tmux session with board UI
tmux new-session -d -s "$SESSION_NAME" -n "board" "qn board ui"

echo ""
echo "  QuinnAI Board"
echo "  Local:   http://localhost:${TTYD_PORT}"
echo "  Session: $SESSION_NAME"
echo "  Attach:  tmux attach -t $SESSION_NAME"

# Start ngrok if requested
if [ "$NGROK" = true ]; then
  if ! command -v ngrok &>/dev/null; then
    echo "  ngrok not found. Install with: brew install ngrok"
    NGROK=false
  else
    # Kill existing ngrok on this port
    pkill -f "ngrok http ${TTYD_PORT}" 2>/dev/null || true
    ngrok http "$TTYD_PORT" --log=stdout > /tmp/ngrok-board.log 2>&1 &
    sleep 2
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"[^"]*' | grep https | cut -d'"' -f4 || echo "")
    if [ -n "$NGROK_URL" ]; then
      echo "  Public: ${NGROK_URL}"
    else
      echo "  Public: (ngrok starting, check http://localhost:4040)"
    fi
  fi
fi

echo ""

# Cleanup tmux session on exit
cleanup() {
  tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
}
trap cleanup EXIT

# Serve tmux session via ttyd (foreground — Ctrl+C to stop)
exec ttyd \
  --port "$TTYD_PORT" \
  --writable \
  tmux attach-session -t "$SESSION_NAME"
