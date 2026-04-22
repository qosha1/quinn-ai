"""System constants: IDs, names, pagination, database, terminal, logging, and stop controller."""

# ===================
# PAGINATION
# ===================

DEFAULT_LIMIT = 50
"""Default limit for paginated queries."""

DEFAULT_MESSAGE_LIMIT = 50
"""Default limit for message queries."""

DEFAULT_NOTIFICATION_LIMIT = 50
"""Default limit for notification queries."""

DEFAULT_WORKER_LIMIT = 100
"""Default limit for worker queries."""


# ===================
# IDS & NAMES
# ===================

DEFAULT_ORG_ID = "default"
"""Default organization ID."""

DEFAULT_PROVIDER = "anthropic"
"""Default AI provider."""

DEFAULT_CEO_ROLE = "ceo"
"""Role identifier for CEO."""

DEFAULT_BOARD_CHANNEL = "board-channel"
"""Default channel for board communications."""

DEFAULT_ACTIVITY_FEED_CHANNEL = "activity-feed"
"""Default channel for worker activity reports."""


# ===================
# DATABASE
# ===================

DEFAULT_DB_NAME = "quinn.db"
"""Default database filename."""

DB_SCHEMA_VERSION = 23
"""Current database schema version."""

DEFAULT_DB_BUSY_TIMEOUT_MS = 5000
"""Default SQLite busy timeout in milliseconds (5 seconds)."""

LIVE_DIR = "live"
"""Runtime state directory name."""

CONFIG_DIR = "config"
"""Configuration directory name."""

ORG_CHART_DIR = "org-chart"
"""Org chart output directory name."""


# ===================
# TERMINAL
# ===================

DEFAULT_TERMINAL_COLS = 120
"""Default terminal width."""

DEFAULT_TERMINAL_ROWS = 40
"""Default terminal height."""

DEFAULT_MAX_CONTEXT_TOKENS = 100000
"""Maximum context tokens for sessions."""

TMUX_SESSION_PREFIX = "qn-"
"""Prefix for tmux session names. Session names are formatted as {prefix}{worker_id}."""


# ===================
# LOGGING
# ===================

LOG_RETENTION_DAYS = 30
"""Number of days to retain component logs."""

LOG_DATE_FORMAT = "%Y-%m-%d"
"""Date format for daily log files."""

LOG_COMPONENTS = ["cli", "worker", "session", "board", "system"]
"""Valid log component names."""


# ===================
# STOP SEQUENCE (ORG STOP)
# ===================

# Role-based graceful shutdown timeouts (seconds)
# Higher roles get more time to wrap up complex work
STOP_TIMEOUT_CEO = 120
"""CEO graceful shutdown timeout (2 minutes)."""

STOP_TIMEOUT_MANAGER = 90
"""Manager graceful shutdown timeout (90 seconds)."""

STOP_TIMEOUT_WORKER = 60
"""Worker graceful shutdown timeout (1 minute)."""

# Timeout mapping by role pattern
STOP_TIMEOUT_BY_ROLE = {
    "ceo": STOP_TIMEOUT_CEO,
    "director": STOP_TIMEOUT_MANAGER,
    "manager": STOP_TIMEOUT_MANAGER,
    "team-lead": STOP_TIMEOUT_MANAGER,
    # All other roles get worker timeout
}

DEFAULT_STOP_TIMEOUT = STOP_TIMEOUT_WORKER
"""Default timeout for roles not in STOP_TIMEOUT_BY_ROLE."""

# Acknowledgement polling
STOP_ACK_POLL_INTERVAL = 2.0
"""Seconds between acknowledgement polls."""

STOP_ACK_TIMEOUT_RATIO = 0.8
"""Ratio of role timeout to use as ack deadline (80%)."""

# Session termination
STOP_SESSION_GRACE_PERIOD = 5.0
"""Seconds to wait after graceful stop before force kill."""

STOP_SESSION_FORCE_TIMEOUT = 10.0
"""Maximum seconds to wait for force kill."""

# Wrap-up message types
WRAPUP_MESSAGE_TYPE = "wrapup_request"
"""Message type for wrap-up notifications."""

WRAPUP_ACK_MESSAGE_TYPE = "wrapup_ack"
"""Message type for wrap-up acknowledgements."""

# State persistence
RESUME_STATE_TTL_HOURS = 24
"""Hours to retain resume state before expiry."""
