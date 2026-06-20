"""Timing constants: timeouts, polling intervals, state monitoring."""

# ===================
# TIMEOUTS (seconds)
# ===================

DEFAULT_TIMEOUT = 60
"""Default timeout for operations."""

DEFAULT_STARTUP_TIMEOUT = 30
"""Timeout for session startup."""

DEFAULT_RESPONSE_TIMEOUT = 600
"""Timeout for provider responses (10 minutes)."""

DEFAULT_IDLE_TIMEOUT = 300
"""Timeout for idle sessions (5 minutes)."""

DEFAULT_MAX_RETRIES = 3
"""Default maximum retry attempts."""

DEFAULT_HEARTBEAT_THRESHOLD = 60
"""Seconds before heartbeat is considered stale."""

BACKGROUND_THREAD_STOP_TIMEOUT = 5.0
"""Default timeout when stopping background subsystem threads
(activity reporter, session capture, continuation engine)."""

BD_COMMAND_TIMEOUT_SECONDS = 10
"""Subprocess timeout for invocations of the bd CLI."""

TMUX_CAPTURE_TIMEOUT_SECONDS = 2
"""Subprocess timeout for `tmux capture-pane` calls."""

TMUX_CAPTURE_LINES = 100
"""Number of trailing pane lines to capture from tmux."""


# ===================
# POLLING INTERVALS (seconds)
# ===================

DEFAULT_POLL_INTERVAL = 0.5
"""Default polling interval for general operations."""

LOG_TAIL_POLL_INTERVAL = 0.5
"""Polling interval for log tailing operations."""

SESSION_START_POLL_INTERVAL = 1.0
"""Polling interval when waiting for session startup."""

INITIAL_PROMPT_FILESYSTEM_FLUSH = 2.0
"""Pause after writing INITIAL_TASK.md before the tmux read so the
filesystem write is fully visible to the spawned shell."""

TMUX_SEND_KEYS_INTERSTITIAL = 0.5
"""Brief pause between tmux 'send-keys' invocations (typing a command
and then sending Enter), so tmux registers the command buffer before
the Enter keystroke."""

INITIAL_PROMPT_VERIFICATION_WINDOW = 5.0
"""Time budget to confirm the CEO's INITIAL_TASK prompt actually
landed in the tmux pane (vs. disappearing into a not-yet-ready TUI)."""

INITIAL_PROMPT_VERIFICATION_POLL = 0.5
"""Polling interval inside INITIAL_PROMPT_VERIFICATION_WINDOW for
checking whether the pane content has changed."""

INITIAL_PROMPT_DELIVERY_ATTEMPTS = 3
"""How many times to (re)send the CEO's 'cat INITIAL_TASK.md' kickstart,
verifying after each that the prompt actually landed in the pane. A single
send can race claude's still-booting TUI and vanish, leaving the CEO idle
forever (quinn-ai-ns6t); re-sending until verification succeeds is robust
even when pane-readiness detection is imperfect."""

INITIAL_PROMPT_READY_TIMEOUT = 5.0
"""Initial best-effort wait for the CEO TUI before the first kickstart send.
Kept short because the verify-and-retry loop is the real delivery guarantee
(quinn-ai-ns6t) — a too-early first send is simply re-sent, so we don't block
long here."""

GRACEFUL_SHUTDOWN_WAIT = 5.0
"""Wait time after graceful shutdown signal before force termination."""

# ===================
# STATE MONITORING
# ===================

DEFAULT_STATE_POLL_INTERVAL = 1.0
"""Default polling interval for background state monitoring (seconds)."""

DEFAULT_STATE_IDLE_TIMEOUT = 3.0
"""Default timeout for considering session idle (seconds)."""

DEFAULT_STATE_ERROR_RETRY = 5.0
"""Default retry interval after monitoring error (seconds)."""

DEFAULT_STATE_MAX_ERRORS = 10
"""Maximum consecutive errors before stopping monitor."""

STATE_MONITOR_THREAD_PREFIX = "StateMonitor-"
"""Prefix for state monitor thread names."""
