"""
QuinnAI CLI constants.

Central location for all magic values, following the 'No Magic Values' principle.
All default values that are used in multiple places should be defined here.
"""

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


# ===================
# SKILL THRESHOLDS (0-100)
# ===================

DEFAULT_SKILL_THRESHOLD_CODING = 80
"""Skill score required to unlock coding capability."""

DEFAULT_SKILL_THRESHOLD_REASONING = 60
"""Skill score required to unlock advanced reasoning."""

DEFAULT_SKILL_THRESHOLD_RESEARCH = 80
"""Skill score required to unlock research capability."""

DEFAULT_SKILL_THRESHOLD_MANAGEMENT = 70
"""Skill score required to unlock management capability."""

DEFAULT_SKILL_THRESHOLD_STRATEGY = 90
"""Skill score required to unlock strategic capability."""

# Collected as dict for convenience
DEFAULT_SKILL_THRESHOLDS = {
    "coding": DEFAULT_SKILL_THRESHOLD_CODING,
    "reasoning": DEFAULT_SKILL_THRESHOLD_REASONING,
    "research": DEFAULT_SKILL_THRESHOLD_RESEARCH,
    "management": DEFAULT_SKILL_THRESHOLD_MANAGEMENT,
    "strategy": DEFAULT_SKILL_THRESHOLD_STRATEGY,
}


# ===================
# WORKER COSTS (0-100)
# ===================

DEFAULT_WORKER_COST = 50
"""Default cost score for new workers."""

DEFAULT_CEO_COST = 100
"""Cost score for CEO workers (highest tier)."""

COST_TIER_BUDGET_MAX = 30
"""Maximum cost for budget tier (0-30)."""

COST_TIER_STANDARD_MAX = 60
"""Maximum cost for standard tier (31-60)."""

COST_TIER_ADVANCED_MAX = 80
"""Maximum cost for advanced tier (61-80)."""

# Premium tier is > 80 (81-100)


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


# ===================
# DATABASE
# ===================

DEFAULT_DB_NAME = "quinn.db"
"""Default database filename."""

LIVE_DIR = "live"
"""Runtime state directory name."""

CONFIG_DIR = "config"
"""Configuration directory name."""

ORG_CHART_DIR = "org-chart"
"""Org chart output directory name."""


# ===================
# NOTIFICATIONS
# ===================

DEFAULT_NOTIFICATION_RETENTION_DAYS = 7
"""Days to retain closed notifications before purge."""

DEFAULT_NOTIFICATION_PRIORITY = 2  # Corresponds to Priority.P2 from shared.enums
"""Default priority for notifications (0-4, 0=highest). Maps to Priority.P2."""


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
# BUDGET
# ===================

DEFAULT_BUDGET_PERIOD_DAYS = 30
"""Default budget period in days."""

# Cost per 1000 tokens by tier (in dollars)
COST_PER_1K_TOKENS_BUDGET = {"input": 0.00025, "output": 0.00125}
COST_PER_1K_TOKENS_STANDARD = {"input": 0.003, "output": 0.015}
COST_PER_1K_TOKENS_ADVANCED = {"input": 0.003, "output": 0.015}
COST_PER_1K_TOKENS_PREMIUM = {"input": 0.015, "output": 0.075}

# Estimated session spawn cost (initial context setup)
# Conservative estimate: ~2K input tokens + ~500 output tokens for session init
DEFAULT_SESSION_SPAWN_TOKENS_INPUT = 2000
"""Estimated input tokens for session spawn."""

DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT = 500
"""Estimated output tokens for session spawn."""


# ===================
# PERMISSIONS
# ===================

# Permission levels (0-5)
PERM_LEVEL_NONE = 0
"""No access."""

PERM_LEVEL_READ = 1
"""Can read/view."""

PERM_LEVEL_COMMENT = 2
"""Can read and comment."""

PERM_LEVEL_WRITE = 3
"""Can create and update."""

PERM_LEVEL_APPROVE = 4
"""Can approve/close work."""

PERM_LEVEL_ADMIN = 5
"""Full administrative access."""

# Permission level names for display
PERM_LEVEL_NAMES = {
    PERM_LEVEL_NONE: "none",
    PERM_LEVEL_READ: "read",
    PERM_LEVEL_COMMENT: "comment",
    PERM_LEVEL_WRITE: "write",
    PERM_LEVEL_APPROVE: "approve",
    PERM_LEVEL_ADMIN: "admin",
}

# Required permission level for bd commands
BD_COMMAND_PERMISSIONS = {
    # Read operations
    "list": PERM_LEVEL_READ,
    "show": PERM_LEVEL_READ,
    "ready": PERM_LEVEL_READ,
    "stats": PERM_LEVEL_READ,
    "blocked": PERM_LEVEL_READ,
    "doctor": PERM_LEVEL_READ,
    "sync": PERM_LEVEL_READ,
    # Write operations
    "create": PERM_LEVEL_WRITE,
    "update": PERM_LEVEL_WRITE,
    "close": PERM_LEVEL_WRITE,
    "dep": PERM_LEVEL_WRITE,
    # Admin operations
    "delete": PERM_LEVEL_ADMIN,
    "prime": PERM_LEVEL_ADMIN,
}


# ===================
# BEAD & ENTITY TYPES
# ===================

# Bead types (for bd CLI and bead system)
BEAD_TYPE_TASK = "task"
"""Task bead type."""

BEAD_TYPE_BUG = "bug"
"""Bug bead type."""

BEAD_TYPE_FEATURE = "feature"
"""Feature bead type."""

BEAD_TYPE_EPIC = "epic"
"""Epic bead type."""

BEAD_TYPE_ASK = "ask"
"""Ask bead type (for requesting help/review)."""

BEAD_TYPE_OKR = "okr"
"""OKR bead type."""

BEAD_TYPE_KEY_RESULT = "key_result"
"""Key result bead type (sub-item of OKR)."""

BEAD_TYPE_REPORT = "report"
"""Report bead type."""

BEAD_TYPE_EXECUTION = "execution"
"""Execution bead type."""

BEAD_TYPE_GATE = "gate"
"""Gate bead type (approval checkpoint)."""

BEAD_TYPE_AGENT = "agent"
"""Agent bead type."""

BEAD_TYPE_ROLE = "role"
"""Role bead type."""

BEAD_TYPE_RIG = "rig"
"""Rig bead type."""

BEAD_TYPE_CONVOY = "convoy"
"""Convoy bead type."""

BEAD_TYPE_EVENT = "event"
"""Event bead type."""

# Entity types (for events and references)
ENTITY_TYPE_ORG = "org"
"""Organization entity type."""

ENTITY_TYPE_WORKER = "worker"
"""Worker entity type."""

ENTITY_TYPE_SESSION = "session"
"""Session entity type."""

ENTITY_TYPE_TEAM = "team"
"""Team entity type."""

ENTITY_TYPE_OKR = "okr"
"""OKR entity type."""

ENTITY_TYPE_ESCALATION = "escalation"
"""Escalation entity type."""

ENTITY_TYPE_BOARD_ESCALATION = "board-escalation"
"""Board escalation entity type."""

ENTITY_TYPE_MESSAGE = "message"
"""Message entity type."""

ENTITY_TYPE_WORK = "work"
"""Work entity type."""

ENTITY_TYPE_OFFBOARDING = "offboarding"
"""Offboarding entity type."""

ENTITY_TYPE_BUDGET = "budget"
"""Budget entity type."""

# Grantee types (for permissions)
GRANTEE_TYPE_WORKER = "worker"
"""Worker grantee type for permissions."""

# Reference types (for transactions and links)
REFERENCE_TYPE_TASK = "task"
"""Task reference type."""

REFERENCE_TYPE_MESSAGE = "message"
"""Message reference type."""

REFERENCE_TYPE_SESSION = "session"
"""Session reference type."""

REFERENCE_TYPE_BEAD = "bead"
"""Bead reference type."""

REFERENCE_TYPE_ASK = "ask"
"""Ask reference type."""

REFERENCE_TYPE_OKR = "okr"
"""OKR reference type."""


# ===================
# LIFECYCLE STATES
# ===================

# Lifecycle state definitions per bead type
# Format:
#   states: ordered list of valid states
#   terminal: states where bead can be closed
#   transitions: dict mapping current state -> list of allowed next states
LIFECYCLE_STATES = {
    BEAD_TYPE_TASK: {
        "states": ["investigation", "planning", "implementation", "review", "done"],
        "terminal": ["done", "rejected", "abandoned"],
        "transitions": {
            "investigation": ["planning", "rejected", "abandoned"],
            "planning": ["implementation", "investigation", "rejected", "abandoned"],
            "implementation": ["review", "planning", "rejected", "abandoned"],
            "review": ["done", "implementation", "rejected", "abandoned"],
            "done": [],  # Terminal state - no further transitions
            "rejected": [],  # Terminal state
            "abandoned": [],  # Terminal state
        },
    },
    BEAD_TYPE_BUG: {
        "states": ["triage", "investigation", "fixing", "review", "done"],
        "terminal": ["done", "wontfix", "duplicate"],
        "transitions": {
            "triage": ["investigation", "wontfix", "duplicate"],
            "investigation": ["fixing", "triage", "wontfix", "duplicate"],
            "fixing": ["review", "investigation", "wontfix"],
            "review": ["done", "fixing", "wontfix"],
            "done": [],
            "wontfix": [],
            "duplicate": [],
        },
    },
    BEAD_TYPE_FEATURE: {
        "states": ["discovery", "design", "implementation", "review", "done"],
        "terminal": ["done", "rejected", "deferred"],
        "transitions": {
            "discovery": ["design", "rejected", "deferred"],
            "design": ["implementation", "discovery", "rejected", "deferred"],
            "implementation": ["review", "design", "rejected", "deferred"],
            "review": ["done", "implementation", "rejected", "deferred"],
            "done": [],
            "rejected": [],
            "deferred": [],
        },
    },
    # Default lifecycle for unspecified bead types
    "default": {
        "states": ["open", "in_progress", "done"],
        "terminal": ["done", "closed"],
        "transitions": {
            "open": ["in_progress", "done", "closed"],
            "in_progress": ["done", "open", "closed"],
            "done": [],
            "closed": [],
        },
    },
}

# Default initial state for each bead type
LIFECYCLE_INITIAL_STATES = {
    BEAD_TYPE_TASK: "investigation",
    BEAD_TYPE_BUG: "triage",
    BEAD_TYPE_FEATURE: "discovery",
    "default": "open",
}


# ===================
# HIRING AUTHORITY
# ===================

DEFAULT_MAX_REPORTS = 10
"""Default maximum direct reports for a worker."""

DEFAULT_DELEGATED_BUDGET = 0
"""Default delegated budget for new workers (none)."""

DEFAULT_HIRING_MAX_COST = 50
"""Default maximum cost for individual hires."""

DEFAULT_HIRING_MAX_TOTAL_BUDGET = 0
"""Default total hiring budget (none - must be delegated)."""


# ===================
# LOGGING
# ===================

LOG_RETENTION_DAYS = 30
"""Number of days to retain component logs."""

LOG_DATE_FORMAT = "%Y-%m-%d"
"""Date format for daily log files."""

LOG_COMPONENTS = ["cli", "worker", "session", "board", "system"]
"""Valid log component names."""
