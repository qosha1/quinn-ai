"""Channel, message type, notification, and escalation constants."""

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
⏱️  ACTIVITY CHECK (5 minutes since last progress)

Are you making progress? If you're working, no action needed.

If blocked, please either:
1. Update your current bead: bd update {current_task_id}
2. Message your manager: msgr send @{manager_id} "status update"
3. Post to team: msgr send #{team_channel} "working on X"

This is a gentle reminder - continue your work.
---
"""

CONTINUATION_PROMPT_STATUS_REQUEST = """
---
📊 STATUS REQUEST (15 minutes since last progress)

Please provide a brief status update using ONE of these:

1. Update bead: bd update {current_task_id} --notes="working on X"
2. Team message: msgr send #{team_channel} "Status: working on X, ETA Y"
3. Manager DM: msgr send @{manager_id} "blocked on X, need help"

Status updates help your team know you're progressing.
---
"""

CONTINUATION_PROMPT_FINAL_WARNING = """
---
🚨 URGENT: Final warning (25 minutes idle)

You will be escalated to your manager in 5 minutes if no activity detected.

Please take action NOW:
- Update bead: bd update {current_task_id} --notes="progress update"
- If blocked: msgr send @{manager_id} "BLOCKED: [describe issue]" --priority=1
- If done: bd close {current_task_id} && bd ready

Your manager will be notified automatically if no response.
---
"""
