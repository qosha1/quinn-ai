"""
State machine definitions for QuinnAI.

Contains the transition rules for Worker lifecycle, Worker runtime,
and Org lifecycle state machines. These are pure data definitions
with no storage dependencies.
"""

# ===================
# WORKER LIFECYCLE
# ===================

LIFECYCLE_STATES = frozenset([
    "pending",
    "onboarding",
    "active",
    "suspended",
    "terminated",
])

LIFECYCLE_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["onboarding", "terminated"],
    "onboarding": ["active", "terminated"],
    "active": ["suspended", "terminated"],
    "suspended": ["active", "terminated"],
    "terminated": [],
}

# ===================
# WORKER RUNTIME
# ===================

RUNTIME_STATES = frozenset([
    "starting",
    "running",
    "idle",
    "working",
    "blocked",
    "stopped",
    "crashed",
])

RUNTIME_TRANSITIONS: dict[str, list[str]] = {
    "starting": ["running", "crashed"],
    "running": ["idle", "working", "stopped", "crashed"],
    "idle": ["running", "stopped"],
    "working": ["blocked", "idle", "stopped", "crashed"],
    "blocked": ["working", "stopped", "crashed"],
    "stopped": [],
    "crashed": [],
}

# Lifecycle states that allow runtime sessions
SESSION_ALLOWED_LIFECYCLES = frozenset(["onboarding", "active"])

# ===================
# ORG LIFECYCLE
# ===================

ORG_STATES = frozenset([
    "uninitialized",
    "initialized",
    "running",
    "stopped",
])

ORG_TRANSITIONS: dict[str, list[str]] = {
    "uninitialized": ["initialized"],
    "initialized": ["running"],
    "running": ["stopped"],
    "stopped": ["running"],
}
