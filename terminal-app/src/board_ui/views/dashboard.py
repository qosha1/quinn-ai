"""
Dashboard view - org metrics and overview.

Shows:
- Org status (running/stopped)
- Cost metrics (today/week/month)
- Worker count and status breakdown
- Prominent "Chat with CEO" button
- Mini org chart
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static
from textual.widget import Widget

from ..interfaces.org_connection import OrgInfo, WorkerInfo, BudgetSummary, OrgStatus
from ..widgets.recent_activity import RecentActivityWidget
from ..widgets.health_status import HealthStatusWidget
from ..logging_config import get_board_logger
from ._org_access import get_org_connection

logger = get_board_logger(__name__)


class DashboardView(VerticalScroll):
    """Main dashboard view."""

    DEFAULT_CSS = """
    DashboardView {
        height: 100%;
    }

    #top-row {
        height: auto;
        margin-bottom: 1;
    }

    #ceo-card {
        width: 30;
        height: 7;
        border: solid $primary;
        padding: 1;
        margin-right: 2;
    }

    #metrics-row {
        height: auto;
        margin-bottom: 1;
    }

    .metric-card {
        width: 20;
        height: auto;
        border: solid $secondary;
        padding: 1;
        margin-right: 1;
        layout: vertical;
        align: center middle;
    }

    .metric-value {
        text-align: center;
        width: 100%;
    }

    .metric-label {
        text-align: center;
        width: 100%;
        color: $text-muted;
    }

    #activity-widget {
        height: auto;
        max-height: 12;
        margin-bottom: 1;
    }

    #actions-panel {
        height: auto;
    }

    .action-buttons {
        height: auto;
    }

    .action-buttons Button {
        margin-right: 1;
    }

    #chat-ceo-btn {
        margin-top: 1;
    }

    .ceo-inactive #chat-ceo-btn {
        opacity: 0.5;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ceo: Optional[WorkerInfo] = None
        self._org_info: Optional[OrgInfo] = None
        self._budget: Optional[BudgetSummary] = None
        self._spawning_session: bool = False  # Guard against double-spawn
        self._refresh_interval_seconds = 2  # Auto-refresh every 2 seconds

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-row"):
            # CEO quick access card
            with Container(id="ceo-card", classes="panel"):
                yield Label("CEO", classes="panel-title worker-ceo")
                yield Label("Status: --", id="ceo-status")
                yield Button("Chat Now", id="chat-ceo-btn", variant="primary")

            # Unread messages card
            with Container(classes="metric-card", id="messages-card"):
                yield Label("--", id="unread-count", classes="metric-value")
                yield Label("messages need reply", classes="metric-label")

        with Horizontal(id="metrics-row"):
            with Container(classes="metric-card"):
                yield Label("$--", id="spend-today", classes="metric-value")
                yield Label("spent today", classes="metric-label")

            with Container(classes="metric-card"):
                yield Label("--", id="worker-count", classes="metric-value")
                yield Label("workers", classes="metric-label")

            with Container(classes="metric-card"):
                yield Label("--", id="active-count", classes="metric-value status-running")
                yield Label("active sessions", classes="metric-label")

        # Health status widget
        yield HealthStatusWidget(id="health-widget")

        # Recent activity widget (auto-refreshes every 30s)
        yield RecentActivityWidget(
            org_connection=None,  # Will be set in on_mount
            limit=20,
            id="activity-widget"
        )

        with Container(id="actions-panel", classes="panel"):
            yield Label("Org Actions", classes="panel-title")
            with Horizontal(classes="action-buttons"):
                yield Button("Start Org", id="start-org-btn", variant="success")
                yield Button("Stop Org", id="stop-org-btn", variant="error")
                yield Button("Restart Org", id="restart-org-btn", variant="warning")

    async def on_mount(self) -> None:
        """Load data when view mounts."""
        conn = get_org_connection(self.app)
        if conn is not None:
            activity_widget = self.query_one("#activity-widget", RecentActivityWidget)
            activity_widget.org_connection = conn
            activity_widget.refresh_activities()

        await self.refresh_data()
        # Start auto-refresh timer
        self.set_interval(self._refresh_interval_seconds, self._auto_refresh)

    async def _auto_refresh(self) -> None:
        """Auto-refresh callback for timer."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh dashboard data from org connection."""
        conn = get_org_connection(self.app)
        if conn is None:
            return

        try:
            # Get org info
            self._org_info = conn.get_org_info()
            self._update_org_metrics()
            self._update_org_action_buttons()

            # Get CEO
            self._ceo = conn.get_ceo()
            self._update_ceo_card()

            # Get budget
            self._budget = conn.get_budget_summary()
            self._update_budget_metrics()

            # Get unread count
            unread = conn.get_unread_count()
            self._update_unread_count(unread)

            # Get health status
            health = conn.get_health_status()
            self._update_health_status(health)
        except Exception as e:
            logger.error(f"Error refreshing dashboard data: {e}")
            self.app.notify("Failed to refresh dashboard data", severity="warning")

    def _update_org_metrics(self) -> None:
        """Update org metrics display."""
        if not self._org_info:
            return

        # Worker count
        worker_label = self.query_one("#worker-count", Label)
        worker_label.update(str(self._org_info.worker_count))

        # Active sessions
        active_label = self.query_one("#active-count", Label)
        active_label.update(str(self._org_info.active_session_count))

    def _update_org_action_buttons(self) -> None:
        """Update org action button states based on org status."""
        if not self._org_info:
            return

        start_btn = self.query_one("#start-org-btn", Button)
        stop_btn = self.query_one("#stop-org-btn", Button)
        restart_btn = self.query_one("#restart-org-btn", Button)

        status = self._org_info.status

        if status == OrgStatus.RUNNING:
            # Org is running - can stop or restart, but not start
            start_btn.disabled = True
            stop_btn.disabled = False
            restart_btn.disabled = False
        elif status in (OrgStatus.STOPPED, OrgStatus.INITIALIZED):
            # Org is stopped or initialized - can start, but not stop or restart
            start_btn.disabled = False
            stop_btn.disabled = True
            restart_btn.disabled = True
        elif status == OrgStatus.UNINITIALIZED:
            # Org not initialized - disable all actions
            start_btn.disabled = True
            stop_btn.disabled = True
            restart_btn.disabled = True
        else:
            # Unknown state - disable all for safety
            start_btn.disabled = True
            stop_btn.disabled = True
            restart_btn.disabled = True

    def _update_ceo_card(self) -> None:
        """Update CEO card display."""
        from ..interfaces.org_connection import SessionState

        ceo_card = self.query_one("#ceo-card", Container)
        ceo_status = self.query_one("#ceo-status", Label)
        chat_btn = self.query_one("#chat-ceo-btn", Button)

        if self._ceo:
            # Show detailed session state
            if self._ceo.session_state == SessionState.RUNNING:
                status_text = "🟢 Working"
            elif self._ceo.session_state == SessionState.IDLE:
                status_text = "🟡 Idle"
            elif self._ceo.session_state == SessionState.STARTING:
                status_text = "🔵 Starting"
            elif self._ceo.session_state == SessionState.STOPPED:
                status_text = "⚫ Stopped"
            elif self._ceo.session_state == SessionState.CRASHED:
                status_text = "🔴 Crashed"
            else:
                status_text = "⚫ Inactive"

            ceo_status.update(f"Status: {status_text}")
            chat_btn.disabled = self._ceo.tmux_session_name is None
            ceo_card.remove_class("ceo-inactive")
        else:
            ceo_status.update("Status: No CEO")
            chat_btn.disabled = True
            ceo_card.add_class("ceo-inactive")

    def _update_budget_metrics(self) -> None:
        """Update budget metrics display."""
        spend_label = self.query_one("#spend-today", Label)
        if self._budget:
            spend_label.update(f"${self._budget.spend_today:.2f}")
        else:
            spend_label.update("$0.00")

    def _update_unread_count(self, count: int) -> None:
        """Update unread message count."""
        unread_label = self.query_one("#unread-count", Label)
        unread_label.update(str(count))

    def _update_health_status(self, health) -> None:
        """Update health status widget.

        Args:
            health: HealthStatus from org connection
        """
        health_widget = self.query_one("#health-widget", HealthStatusWidget)
        health_widget.update_health(health)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "chat-ceo-btn":
            await self._open_ceo_chat()
        elif event.button.id == "start-org-btn":
            await self._start_org()
        elif event.button.id == "stop-org-btn":
            await self._stop_org()
        elif event.button.id == "restart-org-btn":
            await self._restart_org()

    async def _open_ceo_chat(self) -> None:
        """Open a chat window with the CEO.

        If the CEO has no active session, spawns one first, then opens the window.
        """
        if not self._ceo:
            self.app.notify("No CEO found", severity="warning")
            return

        if self._spawning_session:
            return  # Already in progress

        tmux_session = self._ceo.tmux_session_name

        # No session? Start one.
        if not tmux_session:
            self._spawning_session = True
            try:
                tmux_session = await self._ensure_worker_session(self._ceo)
            finally:
                self._spawning_session = False
            if not tmux_session:
                return

        self._attach_to_worker(self._ceo.name, tmux_session)

    async def _ensure_worker_session(self, worker) -> str | None:
        """Ensure a worker has a running session, spawning if needed.

        Args:
            worker: WorkerInfo to ensure session for

        Returns:
            tmux_session_name if session is running, None on failure
        """
        conn = get_org_connection(self.app)
        if conn is None:
            self.app.notify("No org connected", severity="error")
            return None

        self.app.notify(f"Starting session for {worker.name}...", severity="information")

        try:
            bg = self.app.run_worker(
                lambda: conn.restart_worker_session(worker.id),
                thread=True,
            )
            success, tmux_name = await bg.wait()
        except Exception as e:
            self.app.notify(f"Failed to start session: {e}", severity="error")
            return None

        if not success or not tmux_name:
            self.app.notify(
                f"Failed to start session for {worker.name}",
                severity="error",
            )
            return None

        self.app.notify(f"Session started for {worker.name}", severity="success")
        await self.refresh_data()
        return tmux_name

    def _attach_to_worker(self, worker_name: str, tmux_session: str) -> None:
        """Open a terminal window attached to a worker's tmux session."""
        from ..terminals import get_terminal_provider

        terminal = get_terminal_provider()
        if terminal is None:
            self.app.notify("No terminal available", severity="error")
            return

        try:
            terminal.attach_to_session(
                title=f"Chat with {worker_name}",
                session_name=tmux_session,
            )
        except ValueError as e:
            self.app.notify(f"Session error: {e}", severity="error")
        except Exception as e:
            self.app.notify(f"Failed to open chat: {e}", severity="error")

    async def _start_org(self) -> None:
        """Start the organization."""
        conn = get_org_connection(self.app)
        if conn is None:
            self.app.notify("No org connected", severity="error")
            return

        self.app.notify("Starting organization...", severity="information")

        try:
            worker = self.app.run_worker(conn.start_org, thread=True)
            success = await worker.wait()
            if success:
                self.app.notify("Organization started successfully", severity="success")
                await self.refresh_data()
            else:
                self.app.notify("Failed to start organization", severity="error")
        except Exception as e:
            self.app.notify(f"Error starting org: {e}", severity="error")

    async def _stop_org(self) -> None:
        """Stop the organization."""
        conn = get_org_connection(self.app)
        if conn is None:
            self.app.notify("No org connected", severity="error")
            return

        self.app.notify("Stopping organization...", severity="information")

        try:
            worker = self.app.run_worker(conn.stop_org, thread=True)
            success = await worker.wait()
            if success:
                self.app.notify("Organization stopped successfully", severity="success")
                await self.refresh_data()
            else:
                self.app.notify("Failed to stop organization", severity="error")
        except Exception as e:
            self.app.notify(f"Error stopping org: {e}", severity="error")

    async def _restart_org(self) -> None:
        """Restart the organization."""
        conn = get_org_connection(self.app)
        if conn is None:
            self.app.notify("No org connected", severity="error")
            return

        self.app.notify("Restarting organization...", severity="information")

        try:
            worker = self.app.run_worker(conn.restart_org, thread=True)
            success, message = await worker.wait()
            if success:
                self.app.notify(message, severity="success")
                # Refresh dashboard data
                await self.refresh_data()
            else:
                self.app.notify(f"Failed to restart: {message}", severity="error")
        except Exception as e:
            self.app.notify(f"Error restarting org: {e}", severity="error")

    def export_as_text(self) -> str:
        """Export dashboard content as plain text.

        Returns:
            Formatted text representation of dashboard
        """
        lines = []
        lines.append("=" * 60)
        lines.append("QUINNAI BOARD - DASHBOARD")
        lines.append("=" * 60)
        lines.append("")

        # Org info
        if self._org_info:
            lines.append(f"Organization: {self._org_info.name}")
            lines.append(f"Status: {self._org_info.status.value}")
            lines.append(f"Workers: {self._org_info.worker_count}")
            lines.append(f"Active Sessions: {self._org_info.active_session_count}")
            lines.append("")

        # CEO info
        if self._ceo:
            lines.append("CEO:")
            lines.append(f"  Name: {self._ceo.name}")
            lines.append(f"  Role: {self._ceo.role}")
            if self._ceo.session_state:
                lines.append(f"  Session State: {self._ceo.session_state.value}")
            if self._ceo.tmux_session_name:
                lines.append(f"  Tmux Session: {self._ceo.tmux_session_name}")
            lines.append("")

        # Budget metrics
        if self._budget:
            lines.append("Budget:")
            lines.append(f"  Spend Today: ${self._budget.spend_today:.2f}")
            lines.append(f"  Spend This Week: ${self._budget.spend_this_week:.2f}")
            lines.append(f"  Total Spent: ${self._budget.total_spent:.2f}")
            lines.append(f"  Total Available: ${self._budget.total_available:.2f}")
            lines.append("")

        # Health status (if available)
        conn = get_org_connection(self.app)
        if conn is not None:
            try:
                health = conn.get_health_status()
                lines.append("Health Status:")
                lines.append(f"  Overall Score: {health.overall_score}/100")
                lines.append(f"  Total Workers: {health.total_workers}")
                lines.append(f"  Workers With Issues: {health.workers_with_issues}")
                lines.append("")

                if health.issues:
                    lines.append("Issues:")
                    for issue in health.issues:
                        lines.append(f"  - [{issue.severity.upper()}] {issue.worker_name}: {issue.description}")
                    lines.append("")

                if health.metrics:
                    lines.append("Metrics:")
                    for metric in health.metrics:
                        lines.append(f"  - {metric.name}: {metric.value} {metric.unit}")
                    lines.append("")
            except Exception:
                # Health status not available
                pass

        lines.append("=" * 60)
        return "\n".join(lines)
