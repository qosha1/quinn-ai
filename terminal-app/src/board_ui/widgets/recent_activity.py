"""Recent activity widget for board dashboard.

Shows recent worker actions/commands/decisions in real-time.
"""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static, Label
from textual.reactive import reactive
from datetime import datetime
from typing import List, Optional

from board_ui.interfaces.org_connection import OrgConnection


class ActivityItem(Static):
    """Single activity item display."""

    def __init__(self, activity: dict):
        """Initialize activity item.

        Args:
            activity: Activity data dict
        """
        super().__init__()
        self.activity = activity

    def compose(self) -> ComposeResult:
        """Compose the activity item."""
        activity_type = self.activity.get("type", "unknown")
        worker_id = self.activity.get("worker_id", "")
        timestamp = self.activity.get("timestamp", "")

        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%H:%M:%S")
        except:
            time_str = timestamp[-8:] if len(timestamp) >= 8 else timestamp

        # Build content based on type
        if activity_type == "command":
            cmd = self.activity.get("command", "")
            success = self.activity.get("success", True)
            icon = "✓" if success else "✗"
            content = f"{icon} `{cmd[:60]}`"

        elif activity_type == "file_edit":
            file_path = self.activity.get("file_path", "")
            action = self.activity.get("action", "edit")
            content = f"📝 {action} {file_path}"

        elif activity_type == "decision":
            decision = self.activity.get("decision", "")
            content = f"💭 {decision[:80]}"

        elif activity_type == "task_progress":
            task_id = self.activity.get("task_id", "")
            status = self.activity.get("status", "")
            content = f"📋 {task_id}: {status}"

        elif activity_type == "message":
            message = self.activity.get("message", "")
            content = f"💬 {message[:80]}"

        else:
            content = f"Unknown activity type: {activity_type}"

        # Yield time and content
        yield Label(f"[dim]{time_str}[/] {content}", classes="activity-item")


class RecentActivityWidget(VerticalScroll):
    """Widget showing recent worker activity."""

    DEFAULT_CSS = """
    RecentActivityWidget {
        height: 100%;
        border: solid $accent;
        padding: 1;
    }

    RecentActivityWidget > Label {
        margin-bottom: 1;
    }

    .activity-item {
        padding: 0 1;
    }

    .no-activity {
        color: $text-muted;
        text-align: center;
        margin-top: 2;
    }
    """

    activities: reactive[List[dict]] = reactive([], recompose=True)

    def __init__(
        self,
        org_connection: Optional[OrgConnection] = None,
        limit: int = 20,
        **kwargs
    ):
        """Initialize recent activity widget.

        Args:
            org_connection: Organization connection
            limit: Maximum number of activities to show
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.org_connection = org_connection
        self.limit = limit
        self.border_title = "Recent Activity"

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        if not self.activities:
            yield Label("No recent activity", classes="no-activity")
        else:
            for activity in self.activities[:self.limit]:
                yield ActivityItem(activity)

    def refresh_activities(self) -> None:
        """Refresh activity data from org connection."""
        if not self.org_connection:
            return

        try:
            # Get recent activities from all workers
            activities = self.org_connection.get_recent_activity(
                minutes=30,
                limit=self.limit
            )
            self.activities = activities

        except Exception as e:
            self.app.notify(
                f"Failed to load recent activity: {e}",
                severity="error",
                timeout=5
            )

    def on_mount(self) -> None:
        """Handle mount event."""
        self.refresh_activities()

        # Auto-refresh every 30 seconds
        self.set_interval(30, self.refresh_activities)
