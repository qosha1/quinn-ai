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
    "offboarding",
    "terminated",
])

LIFECYCLE_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["onboarding"],
    "onboarding": ["active", "terminated"],
    "active": ["offboarding"],
    "offboarding": ["terminated"],
    "terminated": [],
}

# ===================
# WORKER RUNTIME
# ===================

RUNTIME_STATES = frozenset([
    "starting",
    "running",
    "idle",
    "stopped",
    "crashed",
])

RUNTIME_TRANSITIONS: dict[str, list[str]] = {
    "starting": ["running", "crashed"],
    "running": ["idle", "stopped", "crashed"],
    "idle": ["running", "stopped"],
    "stopped": ["starting"],
    "crashed": ["starting"],
}

# Lifecycle states that allow runtime sessions
SESSION_ALLOWED_LIFECYCLES = frozenset(["onboarding", "active", "offboarding"])

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
