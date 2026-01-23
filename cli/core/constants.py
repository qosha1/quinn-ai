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
# LIFECYCLE STATES
# ===================

# Lifecycle state definitions per bead type
# Format:
#   states: ordered list of valid states
#   terminal: states where bead can be closed
#   transitions: dict mapping current state -> list of allowed next states
LIFECYCLE_STATES = {
    "task": {
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
    "bug": {
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
    "feature": {
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
    "task": "investigation",
    "bug": "triage",
    "feature": "discovery",
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
