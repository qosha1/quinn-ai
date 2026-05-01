"""Channel, message type, notification, and escalation constants."""

# ===================
# CHANNELS
# ===================

CHANNEL_TYPE_DIRECT = "direct"
"""Direct (1:1 or small-group) channel type."""

CHANNEL_TYPE_TEAM = "team"
"""Team channel type."""

CHANNEL_TYPE_TOPIC = "topic"
"""Topic channel type."""

# Channel-name templates. Use .format(...) — keeps callers from drifting.
CHANNEL_NAME_HANDOFF_TEMPLATE = "handoff-{worker_id}"
"""Channel name for an offboarding handoff between worker and manager."""

CHANNEL_NAME_DM_TEMPLATE = "dm-{worker_id_1}-{worker_id_2}"
"""Channel name for a direct message between two workers."""


# ===================
# MESSAGE TIME SENSITIVITY
# ===================

TIME_SENSITIVITY_IMMEDIATE = "immediate"
"""Needs attention right now."""

TIME_SENSITIVITY_HOURS = "hours"
"""Needs attention within hours."""

TIME_SENSITIVITY_WHENEVER = "whenever"
"""No urgency."""


# ===================
# MESSAGE PRIORITY (1=highest, 4=lowest)
# ===================

MESSAGE_PRIORITY_URGENT = 1
"""Highest message priority — urgent / blocking."""

MESSAGE_PRIORITY_NORMAL = 2
"""Default message priority."""


# ===================
# NOTIFICATIONS
# ===================

DEFAULT_NOTIFICATION_RETENTION_DAYS = 7
"""Days to retain closed notifications before purge."""

DEFAULT_NOTIFICATION_PRIORITY = 2  # Corresponds to Priority.P2 from shared.enums
"""Default priority for notifications (0-4, 0=highest). Maps to Priority.P2."""


# ===================
# ESCALATION
# ===================

# Escalation timeout periods (minutes) - how long before idle worker triggers escalation
DEFAULT_ESCALATION_TIMEOUT_CEO = 60
"""CEO idle timeout before escalation (minutes)."""

DEFAULT_ESCALATION_TIMEOUT_MANAGER = 45
"""Manager idle timeout before escalation (minutes)."""

DEFAULT_ESCALATION_TIMEOUT_WORKER = 30
"""Worker idle timeout before escalation (minutes)."""

# Escalation monitoring
DEFAULT_ESCALATION_POLL_INTERVAL = 60.0
"""Default polling interval for escalation monitor (seconds)."""

# Activity reporting
DEFAULT_ACTIVITY_REPORT_INTERVAL = 300
"""Default interval for sending activity reports to board (seconds, 5 minutes)."""

# No-work escalation
NO_WORK_ESCALATION_THRESHOLD_MINUTES = 60
"""Minutes without work before worker escalates to manager (default 1 hour)."""

NO_WORK_ESCALATION_CHECK_INTERVAL = 300.0
"""Seconds between checks for no-work escalation (default 5 minutes)."""

DEFAULT_ACTIVITY_CREATE_BEADS = True
"""Whether to create beads for activity summaries (queryable history)."""

DEFAULT_SESSION_CAPTURE_INTERVAL = 10
"""Default interval for capturing tmux session output (seconds)."""


# ===================
# ACTIVITY SIGNALS
# ===================

# Signal strength values (1-5, higher = stronger indicator of work)
SIGNAL_STRENGTH_HEARTBEAT = 1
"""Heartbeat signal strength (weakest - just keeping alive)."""

SIGNAL_STRENGTH_SESSION_OUTPUT = 2
"""Session output signal strength (low - could be idle output)."""

SIGNAL_STRENGTH_FILE_CHANGE = 3
"""File change signal strength (moderate - editing files)."""

SIGNAL_STRENGTH_MESSAGE_SENT = 4
"""Message sent signal strength (strong - communicating)."""

SIGNAL_STRENGTH_BEAD_UPDATE = 5
"""Bead update signal strength (strongest - completing work)."""

SIGNAL_STRENGTH_CODE_COMMIT = 5
"""Code commit signal strength (strongest - delivering work)."""

ACTIVITY_SIGNAL_RETENTION_HOURS = 24
"""Hours to retain activity signals before cleanup."""


# ===================
# CONTINUATION ENGINE
# ===================

# Continuation nudge intervals (minutes) - for regular workers
CONTINUATION_NUDGE_1_MINUTES = 5
"""First soft check-in after 5 minutes of inactivity."""

CONTINUATION_NUDGE_2_MINUTES = 15
"""Second status request after 15 minutes of inactivity."""

CONTINUATION_WARNING_MINUTES = 25
"""Final warning after 25 minutes of inactivity."""

CONTINUATION_ESCALATE_MINUTES = 30
"""Escalate to manager after 30 minutes of inactivity."""

# CEO-specific intervals (more autonomy)
CONTINUATION_NUDGE_1_MINUTES_CEO = 15
"""First soft check-in for CEO after 15 minutes."""

CONTINUATION_NUDGE_2_MINUTES_CEO = 30
"""Second status request for CEO after 30 minutes."""

CONTINUATION_WARNING_MINUTES_CEO = 50
"""Final warning for CEO after 50 minutes."""

CONTINUATION_ESCALATE_MINUTES_CEO = 60
"""Escalate CEO to board after 60 minutes."""

# Manager-specific intervals (between worker and CEO)
CONTINUATION_NUDGE_1_MINUTES_MANAGER = 10
"""First soft check-in for managers after 10 minutes."""

CONTINUATION_NUDGE_2_MINUTES_MANAGER = 25
"""Second status request for managers after 25 minutes."""

CONTINUATION_WARNING_MINUTES_MANAGER = 40
"""Final warning for managers after 40 minutes."""

CONTINUATION_ESCALATE_MINUTES_MANAGER = 45
"""Escalate managers after 45 minutes."""

# Continuation engine settings
CONTINUATION_ENGINE_POLL_INTERVAL = 60.0
"""How often continuation engine checks workers (seconds)."""


# ===================
# CONTINUATION PROMPTS
# ===================

CONTINUATION_PROMPT_SOFT_CHECK = """
---
⏱️  WORK CYCLE (5 minutes since last progress)

Run your work cycle now:

1. msgr inbox
2. bd ready
3. Pick up the highest priority item and work it

If you're mid-task, continue — no action needed.
If blocked: msgr send @{manager_id} "BLOCKED: [describe issue]"
---
"""

CONTINUATION_PROMPT_STATUS_REQUEST = """
---
📊 WORK CYCLE CHECK (15 minutes since last progress)

Run your work cycle:

1. msgr inbox
2. bd ready
3. Claim and work the highest priority item

If genuinely blocked on everything: msgr send @{manager_id} "BLOCKED: [describe issue]" --priority=1
Post a status: msgr send #{team_channel} "Status: [what you're working on]"
---
"""

CONTINUATION_PROMPT_FINAL_WARNING = """
---
🚨 URGENT: 25 minutes idle — escalation in 5 minutes

Run your work cycle NOW:

1. msgr inbox
2. bd ready
3. Claim and work something

If done with current task: bd close {current_task_id} && bd ready
If blocked: msgr send @{manager_id} "BLOCKED: [describe issue]" --priority=1

Your manager will be notified automatically if no response.
---
"""
