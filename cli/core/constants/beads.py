"""Bead types, entity types, reference types, lifecycle states, and OKR constants."""

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
# BOOTSTRAP OKRs
# ===================

DEFAULT_BOOTSTRAP_OKR_TITLE = "Establish organizational foundation"
"""Default bootstrap OKR title when no OKRs configured."""

DEFAULT_BOOTSTRAP_OKR_DESCRIPTION = "Set up core processes, hire initial team, and establish workflows to enable productive operations."
"""Default bootstrap OKR description."""
