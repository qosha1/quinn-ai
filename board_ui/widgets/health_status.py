"""
Health status widget - shows org health indicators.

Displays:
- Overall health score (green/yellow/red)
- List of health issues
- Worker issue count
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Label, Static
from textual.widget import Widget

from ..interfaces.org_connection import HealthStatus


class HealthStatusWidget(Widget):
    """Widget displaying org health status."""

    DEFAULT_CSS = """
    HealthStatusWidget {
        height: auto;
        border: solid $secondary;
        padding: 1;
        margin-bottom: 1;
    }

    .health-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .health-healthy {
        color: $success;
    }

    .health-warning {
        color: $warning;
    }

    .health-critical {
        color: $error;
    }

    .health-summary {
        text-align: center;
        margin-bottom: 1;
    }

    .issue-list {
        height: auto;
        max-height: 10;
        overflow-y: auto;
    }

    .issue-item {
        margin-left: 2;
        margin-bottom: 0;
    }

    .issue-error {
        color: $error;
    }

    .issue-warning {
        color: $warning;
    }

    .issue-info {
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._health_status: HealthStatus | None = None

    def compose(self) -> ComposeResult:
        yield Label("Org Health", classes="health-title")
        yield Label("Checking...", id="health-score", classes="health-summary")
        with Vertical(classes="issue-list", id="issue-list"):
            yield Label("No issues detected", classes="issue-info")

    def update_health(self, health: HealthStatus) -> None:
        """Update the health display with new status.

        Args:
            health: HealthStatus to display
        """
        self._health_status = health

        # Update overall score
        score_label = self.query_one("#health-score", Label)
        if health.overall_score == "healthy":
            emoji = "✅"
            status_class = "health-healthy"
            status_text = "Healthy"
        elif health.overall_score == "warning":
            emoji = "⚠️"
            status_class = "health-warning"
            status_text = "Needs Attention"
        else:  # critical
            emoji = "🔴"
            status_class = "health-critical"
            status_text = "Critical Issues"

        if health.overall_score == "healthy":
            if health.workers_with_issues == 0:
                display_text = f"{emoji} {status_text}"
            else:
                display_text = (
                    f"{emoji} {status_text} ({health.workers_with_issues} workers have notes)"
                )
        else:
            display_text = (
                f"{emoji} {status_text}"
                f" ({health.workers_with_issues}/{health.total_workers} workers with issues)"
            )

        score_label.update(display_text)

        # Remove all health state classes then apply the current one
        for cls in ("health-healthy", "health-warning", "health-critical"):
            score_label.remove_class(cls)
        score_label.add_class(status_class)

        # Update issue list
        issue_container = self.query_one("#issue-list", Vertical)
        issue_container.remove_children()

        if not health.issues:
            issue_container.mount(Label("No issues detected", classes="issue-info"))
        else:
            # Group issues by severity for better display
            error_issues = [i for i in health.issues if i.severity == "error"]
            warning_issues = [i for i in health.issues if i.severity == "warning"]
            info_issues = [i for i in health.issues if i.severity == "info"]

            for issue in error_issues:
                issue_container.mount(
                    Label(f"🔴 {issue.message}", classes="issue-item issue-error")
                )

            for issue in warning_issues:
                issue_container.mount(
                    Label(f"⚠️ {issue.message}", classes="issue-item issue-warning")
                )

            for issue in info_issues:
                issue_container.mount(
                    Label(f"ℹ️ {issue.message}", classes="issue-item issue-info")
                )
