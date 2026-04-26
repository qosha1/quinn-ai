"""Worker activity tracking — the WRITE side of the activity pipeline.

Owns the per-worker `live/logs/activity/{worker_id}.jsonl` log: appending raw
events (commands, file changes, decisions) and reading them back as
summaries. Pure data layer — no scheduling, no fan-out.

Pairs with `activity_reporter.py`, which is the READ/PUBLISH side:
ActivityReporter periodically reads from this log on a background thread and
publishes summaries to the activity-feed channel + (optionally) beads.

Rule of thumb: writes/reads of the activity log live here; anything that
runs on a timer or talks to other subsystems lives in activity_reporter.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
import json

from .constants import ACTIVITY_DIR, LIVE_DIR, LOGS_DIR

_logger = logging.getLogger(__name__)


class ActivityTracker:
    """Tracks worker session activity and creates summaries."""

    def __init__(self, org_path: Path, worker_id: str):
        """Initialize activity tracker.

        Args:
            org_path: Path to organization directory
            worker_id: Worker ID to track
        """
        self.org_path = org_path
        self.worker_id = worker_id
        self.activity_log = org_path / LIVE_DIR / LOGS_DIR / ACTIVITY_DIR / f"{worker_id}.jsonl"
        self.activity_log.parent.mkdir(parents=True, exist_ok=True)

    def log_command(self, command: str, output: Optional[str] = None, success: bool = True) -> None:
        """Log a command executed by the worker.

        Args:
            command: The command that was executed
            output: Command output (truncated if too long)
            success: Whether command succeeded
        """
        self._append_activity({
            "type": "command",
            "command": command,
            "output": output[:500] if output else None,  # Limit output size
            "success": success,
        })

    def log_file_edit(self, file_path: str, action: str = "edit") -> None:
        """Log a file edit by the worker.

        Args:
            file_path: Path to file that was edited
            action: Type of action (edit, create, delete)
        """
        self._append_activity({
            "type": "file_edit",
            "file_path": file_path,
            "action": action,
        })

    def log_decision(self, decision: str, reasoning: Optional[str] = None) -> None:
        """Log a decision made by the worker.

        Args:
            decision: The decision that was made
            reasoning: Why the decision was made
        """
        self._append_activity({
            "type": "decision",
            "decision": decision,
            "reasoning": reasoning,
        })

    def log_task_progress(self, task_id: str, status: str, notes: Optional[str] = None) -> None:
        """Log progress on a task.

        Args:
            task_id: Task/bead ID
            status: New status (in_progress, completed, blocked)
            notes: Additional notes about progress
        """
        self._append_activity({
            "type": "task_progress",
            "task_id": task_id,
            "status": status,
            "notes": notes,
        })

    def log_message(self, message: str, context: Optional[str] = None) -> None:
        """Log a message/thought from the worker.

        Args:
            message: The message content
            context: Additional context (what they were working on)
        """
        self._append_activity({
            "type": "message",
            "message": message,
            "context": context,
        })

    def _append_activity(self, activity_data: dict) -> None:
        """Append activity to JSONL log.

        Args:
            activity_data: Activity data to log
        """
        activity_data["timestamp"] = datetime.now().isoformat()
        activity_data["worker_id"] = self.worker_id

        try:
            with open(self.activity_log, "a") as f:
                f.write(json.dumps(activity_data) + "\n")
        except (OSError, TypeError):
            _logger.exception(
                "Failed to log activity for worker=%s", self.worker_id
            )

    def get_recent_activity(self, minutes: int = 30, limit: int = 50) -> List[dict]:
        """Get recent activity entries.

        Args:
            minutes: How far back to look
            limit: Maximum number of entries

        Returns:
            List of activity dictionaries
        """
        if not self.activity_log.exists():
            return []

        cutoff = datetime.now() - timedelta(minutes=minutes)
        activities = []

        try:
            with open(self.activity_log, "r") as f:
                for line in f:
                    try:
                        activity = json.loads(line)
                        activity_time = datetime.fromisoformat(activity["timestamp"])
                        if activity_time >= cutoff:
                            activities.append(activity)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue

            # Return most recent first
            activities.reverse()
            return activities[:limit]

        except OSError:
            _logger.exception(
                "Failed to read activity log for worker=%s", self.worker_id
            )
            return []

    def create_activity_summary(self, minutes: int = 30) -> str:
        """Create a human-readable summary of recent activity.

        Args:
            minutes: How far back to summarize

        Returns:
            Markdown-formatted activity summary
        """
        activities = self.get_recent_activity(minutes=minutes)

        if not activities:
            return f"_No activity in the last {minutes} minutes_"

        summary_parts = []
        summary_parts.append(f"### Activity Summary (last {minutes} minutes)\n")

        # Count by type
        by_type = {}
        for activity in activities:
            activity_type = activity.get("type", "unknown")
            by_type[activity_type] = by_type.get(activity_type, 0) + 1

        # Add overview
        summary_parts.append("**Overview:**")
        for activity_type, count in sorted(by_type.items()):
            summary_parts.append(f"- {count} {activity_type}(s)")

        # Add recent highlights (last 5 activities)
        summary_parts.append("\n**Recent highlights:**")
        for activity in activities[:5]:
            timestamp = activity.get("timestamp", "unknown")
            activity_type = activity.get("type")

            if activity_type == "command":
                cmd = activity.get("command", "")
                success = "✓" if activity.get("success") else "✗"
                summary_parts.append(f"- {success} `{cmd}` _{timestamp[-8:]}_")

            elif activity_type == "file_edit":
                file_path = activity.get("file_path", "")
                action = activity.get("action", "edit")
                summary_parts.append(f"- {action} {file_path} _{timestamp[-8:]}_")

            elif activity_type == "decision":
                decision = activity.get("decision", "")
                summary_parts.append(f"- Decided: {decision} _{timestamp[-8:]}_")

            elif activity_type == "task_progress":
                task_id = activity.get("task_id", "")
                status = activity.get("status", "")
                summary_parts.append(f"- {task_id}: {status} _{timestamp[-8:]}_")

            elif activity_type == "message":
                message = activity.get("message", "")
                summary_parts.append(f"- 💬 {message[:100]} _{timestamp[-8:]}_")

        return "\n".join(summary_parts)
