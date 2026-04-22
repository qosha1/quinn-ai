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


# ===================
# POLLING INTERVALS (seconds)
# ===================

DEFAULT_POLL_INTERVAL = 0.5
"""Default polling interval for general operations."""

LOG_TAIL_POLL_INTERVAL = 0.5
"""Polling interval for log tailing operations."""

SESSION_START_POLL_INTERVAL = 1.0
"""Polling interval when waiting for session startup."""

GRACEFUL_SHUTDOWN_WAIT = 5.0
"""Wait time after graceful shutdown signal before force termination."""

TMUX_ATTACH_WAIT = 0.5
"""Wait time after tmux session spawn for attachment."""


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
