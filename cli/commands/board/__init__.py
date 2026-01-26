"""
Board intervention commands.

Per CLAUDE.md: "Board = Gutterguards. Humans intervene only when org is off-track.
Not required for daily operation."

Commands:
- ui: Launch interactive board terminal UI
- status: Show org status dashboard
- alerts: View/dismiss system alerts
- pause: Pause a worker
- resume: Resume a paused worker
- fire: Terminate a worker immediately
"""

from .ui import ui_cmd
from .status import status_cmd
from .alerts import alerts_cmd
from .intervene import pause_cmd, resume_cmd, fire_cmd

__all__ = ["ui_cmd", "status_cmd", "alerts_cmd", "pause_cmd", "resume_cmd", "fire_cmd"]
