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
    "suspended",
    "terminated",
])

LIFECYCLE_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["onboarding", "terminated"],
    "onboarding": ["active", "terminated"],
    "active": ["offboarding", "suspended", "terminated"],
    "offboarding": ["terminated"],
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
    "stopped",
    "crashed",
])

RUNTIME_TRANSITIONS: dict[str, list[str]] = {
    "starting": ["running", "crashed", "stopped"],
    "running": ["idle", "stopped", "crashed"],
    "idle": ["running", "stopped"],
    "stopped": ["starting"],  # Allow restart from stopped
    "crashed": ["starting"],  # Allow restart from crashed
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

# ===================
# ESCALATION STATES
# ===================

ESCALATION_STATES = frozenset([
    "normal",
    "idle_warning",
    "escalated_pending",
    "escalated_resolved",
])

ESCALATION_TRANSITIONS: dict[str, list[str]] = {
    "normal": ["idle_warning", "escalated_pending"],
    "idle_warning": ["normal", "escalated_pending"],
    "escalated_pending": ["escalated_resolved", "normal"],
    "escalated_resolved": ["normal"],
}
