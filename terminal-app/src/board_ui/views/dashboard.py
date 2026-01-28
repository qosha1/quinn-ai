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
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Label, Static
from textual.widget import Widget

from ..interfaces.org_connection import OrgInfo, WorkerInfo, BudgetSummary


class DashboardView(Widget):
    """Main dashboard view."""

    DEFAULT_CSS = """
    DashboardView {
        layout: vertical;
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

    #activity-panel {
        height: 1fr;
        border: solid $secondary;
        padding: 1;
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

        with Container(id="activity-panel", classes="panel"):
            yield Label("Recent Activity", classes="panel-title")
            yield Static("Connect to an org to see activity", id="activity-content")

        with Container(id="actions-panel", classes="panel"):
            yield Label("Org Actions", classes="panel-title")
            with Horizontal(classes="action-buttons"):
                yield Button("Restart Org", id="restart-org-btn", variant="warning")

    async def on_mount(self) -> None:
        """Load data when view mounts."""
        await self.refresh_data()
        # Start auto-refresh timer
        self.set_interval(self._refresh_interval_seconds, self._auto_refresh)

    async def _auto_refresh(self) -> None:
        """Auto-refresh callback for timer."""
        await self.refresh_data()

    async def refresh_data(self) -> None:
        """Refresh dashboard data from org connection."""
        if not hasattr(self.app, 'org_connection') or not self.app.org_connection:
            return

        conn = self.app.org_connection

        # Get org info
        self._org_info = conn.get_org_info()
        self._update_org_metrics()

        # Get CEO
        self._ceo = conn.get_ceo()
        self._update_ceo_card()

        # Get budget
        self._budget = conn.get_budget_summary()
        self._update_budget_metrics()

        # Get unread count
        unread = conn.get_unread_count()
        self._update_unread_count(unread)

        # Update activity
        self._update_activity()

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

    def _update_activity(self) -> None:
        """Update recent activity display."""
        activity = self.query_one("#activity-content", Static)

        if not self._org_info:
            activity.update("Connect to an org to see activity")
            return

        # Build activity summary
        lines = []
        if self._org_info.started_at:
            lines.append(f"Org started: {self._org_info.started_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Workers: {self._org_info.worker_count}")
        lines.append(f"Active sessions: {self._org_info.active_session_count}")

        if self._budget and self._budget.total_spent > 0:
            lines.append(f"Budget used: ${self._budget.total_spent:.2f} / ${self._budget.total_allocated:.2f}")

        activity.update("\n".join(lines))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "chat-ceo-btn":
            await self._open_ceo_chat()
        elif event.button.id == "restart-org-btn":
            await self._restart_org()

    async def _open_ceo_chat(self) -> None:
        """Open a chat window with the CEO."""
        if not self._ceo or not self._ceo.tmux_session_name:
            self.app.notify("CEO has no active session", severity="warning")
            return

        try:
            from ..terminals import get_terminal_provider

            terminal = get_terminal_provider()
            if terminal is None:
                self.app.notify(
                    "No terminal emulator available. Supported: iTerm2, Kitty, Terminal.app",
                    severity="error"
                )
                return

            # Validate terminal type
            self.app.notify(f"Opening {terminal.terminal_type.value} window...", timeout=2)

            terminal.attach_to_session(
                title="Chat with CEO",
                session_name=self._ceo.tmux_session_name,
            )
            self.app.notify("Opened CEO chat window", severity="success")

        except ValueError as e:
            # Specific error from tmux session validation
            self.app.notify(f"Session error: {e}", severity="error")
        except ImportError as e:
            # Terminal module import failed
            self.app.notify(f"Terminal module error: {e}", severity="error")
        except Exception as e:
            # Generic error
            self.app.notify(f"Failed to open chat: {type(e).__name__}: {e}", severity="error")

    async def _restart_org(self) -> None:
        """Restart the organization."""
        if not hasattr(self.app, 'org_connection') or not self.app.org_connection:
            self.app.notify("No org connected", severity="error")
            return

        # Confirm with user
        from textual.app import ComposeResult
        from textual.containers import Container
        from textual.widgets import Static

        # Show notification that restart is happening
        self.app.notify("Restarting organization...", severity="information")

        # Perform restart in background
        conn = self.app.org_connection
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
