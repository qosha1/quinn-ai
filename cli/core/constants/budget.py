"""Budget, worker cost, and skill threshold constants."""

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
# BUDGET
# ===================

DEFAULT_BUDGET_PERIOD_DAYS = 30
"""Default budget period in days."""

DEFAULT_DELEGATION_LIMIT_PERCENT = 0.5
"""Default maximum percentage of budget that can be delegated to a single subordinate (50%)."""

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
# DELEGATION
# ===================

# Delegation event types (for audit logging)
EVENT_AUTHORITY_DELEGATED = "authority_delegated"
"""Event type when hiring authority is delegated to a worker."""

EVENT_AUTHORITY_REVOKED = "authority_revoked"
"""Event type when hiring authority is revoked from a worker."""

EVENT_DELEGATION_EXPIRED = "delegation_expired"
"""Event type when a time-limited delegation expires."""

EVENT_DELEGATION_CASCADE_REVOKED = "delegation_cascade_revoked"
"""Event type when delegation is revoked due to cascade from parent revocation."""

# Delegation preset names
DELEGATION_PRESET_TEAM_LEAD = "team-lead"
"""Preset for team lead level delegation (engineers, designers, QA)."""

DELEGATION_PRESET_DIRECTOR = "director"
"""Preset for director level delegation (includes managers)."""

DELEGATION_PRESET_VP = "vp"
"""Preset for VP level delegation (all roles)."""

# Delegation preset configurations
# Format: {preset_name: {"allowed_roles": [...], "max_cost": int, "max_budget": int}}
DELEGATION_PRESETS = {
    DELEGATION_PRESET_TEAM_LEAD: {
        "allowed_roles": ["engineer", "designer", "qa"],
        "max_cost": 60,
        "max_budget": 5000,
    },
    DELEGATION_PRESET_DIRECTOR: {
        "allowed_roles": ["engineer", "designer", "qa", "manager", "team-lead"],
        "max_cost": 80,
        "max_budget": 20000,
    },
    DELEGATION_PRESET_VP: {
        "allowed_roles": ["*"],  # All roles
        "max_cost": 90,
        "max_budget": 100000,
    },
}

# Delegation audit event types (must match CHECK constraint in database)
DELEGATION_AUDIT_EVENT_GRANTED = "granted"
DELEGATION_AUDIT_EVENT_REVOKED = "revoked"
DELEGATION_AUDIT_EVENT_EXPIRED = "expired"
DELEGATION_AUDIT_EVENT_CASCADE_REVOKED = "cascade_revoked"
DELEGATION_AUDIT_EVENT_MODIFIED = "modified"
DELEGATION_AUDIT_EVENT_TERMINATED_REVOKED = "terminated_revoked"
