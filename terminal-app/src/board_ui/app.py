"""
Main Board TUI Application.

The board is the human oversight interface for AI organizations.
Board members are gutterguards - they intervene only when the org
is off-track. This UI makes that intervention natural and accessible.

Key UX principles:
- No terminal jargon - buttons do things, not commands
- Windows are meetings - open = join, close = leave (worker keeps working)
- No one waits - all interactions are async or observable state
"""

from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, TabbedContent, TabPane

from .config import BoardConfig
from .views.dashboard import DashboardView
from .views.okrs import OKRsView
from .views.team import TeamView
from .views.messages import MessagesView
from .views.logs import LogsView
from .views.settings import SettingsView
from .logging_config import configure_board_logging
from .views.no_org import (
    NoOrgView,
    ConnectToOrg,
    StartOrg,
    ShowNewOrgWizard,
    RefreshOrgList,
)
from .views.org_wizard import OrgInitWizard, OrgConfig
from .views.org_tabs import OrgTabBar
from .widgets.ceo_briefing import CEOBriefingWidget
from .interfaces.org_connection import OrgStatus
from .services import (
    QuinnAIOrgConnection,
    OrgConnectionError,
    OrgNotFound,
    DatabaseNotFound,
    discover_available_orgs,
    start_org,
)
from .services.clipboard_exporter import ClipboardExporter
from .services.org_connection import DatabaseLocked
from .services.org_connection_registry import OrgConnectionRegistry, connect_with_retry
from .services.wizard_init import CliCoreUnavailable, init_org_from_wizard


class BoardApp(App):
    """QuinnAI Board Terminal UI.

    Interactive oversight interface for AI organizations.
    Board members can:
    - View org status, metrics, and org chart
    - See cascading OKRs and progress
    - Jump into worker sessions for real-time meetings
    - Respond to escalated messages asynchronously

    Multi-org support: Maintains connections to multiple orgs with tab switching.
    """

    TITLE = "QuinnAI Board"
    SUB_TITLE = "Organization Oversight"

    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("d", "switch_tab('dashboard')", "Dashboard", show=True),
        Binding("o", "switch_tab('okrs')", "OKRs", show=True),
        Binding("t", "switch_tab('team')", "Team", show=True),
        Binding("m", "switch_tab('messages')", "Messages", show=True),
        Binding("l", "switch_tab('logs')", "Logs", show=True),
        Binding("s", "switch_tab('settings')", "Settings", show=True),
        Binding("c", "copy_current_view", "Copy", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def __init__(self, config: BoardConfig) -> None:
        """Initialize the board app.

        Args:
            config: Board configuration (explicit, not discovered)
        """
        super().__init__()
        self.config = config
        self._org_registry = OrgConnectionRegistry()

    @property
    def org_connection(self) -> Optional[QuinnAIOrgConnection]:
        """Active org connection (backward-compat property used by views)."""
        return self._org_registry.active

    @property
    def _is_connected(self) -> bool:
        """Check if connected to any org."""
        return self._org_registry.active_path is not None

    # Backward-compat: tests reach into these directly. They're proxies to the
    # registry's internals so the single source of truth stays the registry.
    @property
    def _active_org_path(self) -> Optional[Path]:
        return self._org_registry.active_path

    @_active_org_path.setter
    def _active_org_path(self, value: Optional[Path]) -> None:
        self._org_registry._active_path = value

    @_active_org_path.deleter
    def _active_org_path(self) -> None:
        # patch.object cleanup calls delattr; reset rather than truly delete.
        self._org_registry._active_path = None

    @property
    def _org_connections(self) -> dict[Path, QuinnAIOrgConnection]:
        return self._org_registry._connections

    @_org_connections.setter
    def _org_connections(self, value: dict[Path, QuinnAIOrgConnection]) -> None:
        self._org_registry._connections = value

    @_org_connections.deleter
    def _org_connections(self) -> None:
        self._org_registry._connections = {}

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()

        # Org tab bar for multi-org switching (hidden until connected)
        yield OrgTabBar(id="org-tab-bar", classes="hidden")

        # Start with no-org view, will be replaced when connected
        yield NoOrgView(id="no-org-view")

        # Org init wizard (hidden until user clicks "New Org")
        yield OrgInitWizard(id="org-wizard", classes="hidden")

        # Org views container (hidden until connected)
        with TabbedContent(initial="dashboard", id="org-tabs", classes="hidden"):
            with TabPane("Dashboard", id="dashboard"):
                yield DashboardView(id="dashboard-view")

            with TabPane("OKRs", id="okrs"):
                yield OKRsView(id="okrs-view")

            with TabPane("Team", id="team"):
                yield TeamView(id="team-view")

            with TabPane("Messages", id="messages"):
                yield MessagesView(id="messages-view")

            with TabPane("Logs", id="logs"):
                yield LogsView(id="logs-view")

            with TabPane("Settings", id="settings"):
                yield SettingsView(id="settings-view")

        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific tab.

        Don't switch if user is typing in an input field.
        """
        # Check if focus is on an input widget
        focused = self.focused
        if focused and hasattr(focused, '__class__'):
            from textual.widgets import Input, TextArea
            if isinstance(focused, (Input, TextArea)):
                # User is typing - don't switch tabs
                return

        if not self._is_connected:
            return
        tabs = self.query_one("#org-tabs", TabbedContent)
        tabs.active = tab_id

    async def action_refresh(self) -> None:
        """Refresh all views."""
        if self._is_connected:
            self.notify("Refreshing...")
            await self._refresh_all_views()
        else:
            # Refresh org list
            self._refresh_org_list()

    async def on_mount(self) -> None:
        """Handle app mount."""
        # Set up real-time update polling (300ms interval)
        self.set_interval(0.3, self._poll_for_updates)

        # Discover available orgs
        await self._discover_and_show_orgs()

    async def _discover_and_show_orgs(self) -> None:
        """Discover orgs and update the no-org view."""
        available_orgs = discover_available_orgs(self.config.org_paths)

        # Build list for NoOrgView: (path, status)
        org_list = [(org.path, org.status) for org in available_orgs]

        # Update no-org view with discovered orgs
        no_org_view = self.query_one("#no-org-view", NoOrgView)
        no_org_view.available_orgs = org_list
        no_org_view.search_paths = self.config.org_paths
        no_org_view.refresh(recompose=True)

        # If we have a running org, auto-connect
        running_orgs = [org for org in available_orgs if org.status == "running"]
        if running_orgs:
            await self._connect_to_org(running_orgs[0].path)

    async def _connect_to_org(self, org_path: Path) -> None:
        """Connect to an organization, retrying with backoff if DB is locked."""
        max_retries = 3
        try:
            connection = await connect_with_retry(
                org_path,
                max_retries=max_retries,
                on_locked_retry=lambda attempt, total, delay: self.notify(
                    f"Database locked, retrying in {delay:.1f}s... ({attempt}/{total})"
                ),
            )
        except DatabaseLocked:
            self._show_connect_error(
                f"Database locked after {max_retries} retries", severity="error"
            )
            return
        except OrgNotFound:
            self._show_connect_error(f"Org not found at {org_path}", severity="error")
            return
        except DatabaseNotFound:
            self._show_connect_error(
                f"Org not initialized at {org_path}", severity="warning"
            )
            return
        except OrgConnectionError as e:
            self._show_connect_error(f"Connection failed: {e}", severity="error")
            return

        try:
            self._org_registry.add(org_path, connection)
            self._org_registry.activate(org_path)

            # Hide no-org view, show tabs and org tab bar
            self.query_one("#no-org-view").add_class("hidden")
            self.query_one("#org-tabs").remove_class("hidden")
            self.query_one("#org-tab-bar").remove_class("hidden")

            org_info = connection.get_org_info()
            self.notify(f"Connected to {org_info.name}")
            self.sub_title = f"Connected: {org_info.name}"

            self._update_org_tab_bar()
            configure_board_logging(org_path=org_path, verbose=False)

            logs_view = self.query_one("#logs-view", LogsView)
            logs_view.set_org_path(org_path)

            await self._refresh_all_views()

        except Exception as e:
            self._show_connect_error(f"Connection failed: {e}", severity="error")

    def _show_connect_error(self, error_msg: str, severity: str) -> None:
        self.notify(error_msg, severity=severity)
        no_org_view = self.query_one("#no-org-view", NoOrgView)
        no_org_view.show_error(error_msg)

    def _poll_for_updates(self) -> None:
        """Poll the active org connection for database changes (300ms tick)."""
        conn = self._org_registry.active
        if conn and conn.check_for_updates():
            self.call_later(self._refresh_all_views)

    async def _refresh_all_views(self) -> None:
        """Refresh all org views after connection or org switch."""
        if not self._is_connected:
            return

        dashboard = self.query_one("#dashboard-view", DashboardView)
        await dashboard.refresh_data()

        team = self.query_one("#team-view", TeamView)
        await team.refresh_workers()

        okrs = self.query_one("#okrs-view", OKRsView)
        okrs.refresh_okrs()

        messages = self.query_one("#messages-view", MessagesView)
        await messages.refresh_messages()

        logs = self.query_one("#logs-view", LogsView)
        await logs.refresh_logs()

        settings = self.query_one("#settings-view", SettingsView)
        await settings.refresh_settings()

    def _update_org_tab_bar(self) -> None:
        """Sync the OrgTabBar with the current registry state."""
        tab_bar = self.query_one("#org-tab-bar", OrgTabBar)

        orgs: dict[Path, str] = {}
        for path, conn in self._org_registry.items().items():
            try:
                orgs[path] = conn.get_org_info().name
            except Exception:
                orgs[path] = path.name  # fallback to folder name

        tab_bar.update_orgs(orgs, self._org_registry.active_path)

    def _disconnect_from_org(self, org_path: Optional[Path] = None) -> None:
        """Disconnect from an org (active org if `org_path` is None)."""
        if not self._org_registry.active_path and not org_path:
            return

        new_active = self._org_registry.disconnect(org_path)

        if new_active is not None:
            org_info = self._org_registry.active.get_org_info()
            self.sub_title = f"Connected: {org_info.name}"
            self._update_org_tab_bar()
        else:
            self.query_one("#no-org-view").remove_class("hidden")
            self.query_one("#org-tabs").add_class("hidden")
            self.query_one("#org-tab-bar").add_class("hidden")
            self.sub_title = "Organization Oversight"

        self.notify("Disconnected from org")

    def _refresh_org_list(self) -> None:
        """Refresh the list of available orgs."""
        available_orgs = discover_available_orgs(self.config.org_paths)
        org_list = [(org.path, org.status) for org in available_orgs]

        no_org_view = self.query_one("#no-org-view", NoOrgView)
        no_org_view.available_orgs = org_list
        no_org_view.search_paths = self.config.org_paths
        no_org_view.refresh(recompose=True)
        self.notify("Org list refreshed")

    # Message handlers for NoOrgView
    async def on_connect_to_org(self, message: ConnectToOrg) -> None:
        """Handle request to connect to an org."""
        await self._connect_to_org(message.org_path)

    async def on_start_org(self, message: StartOrg) -> None:
        """Handle request to start an org."""
        self.notify(f"Starting org at {message.org_path}...")
        result = start_org(message.org_path)
        if result.success:
            self.notify(result.message)
            # Connect after successful start
            await self._connect_to_org(message.org_path)
        else:
            error_msg = result.message
            self.notify(error_msg, severity="error")
            no_org_view = self.query_one("#no-org-view", NoOrgView)
            no_org_view.show_error(error_msg)

    async def on_show_new_org_wizard(self, message: ShowNewOrgWizard) -> None:
        """Handle request to show the new org wizard."""
        # Hide no-org view and show wizard
        no_org_view = self.query_one("#no-org-view", NoOrgView)
        wizard = self.query_one("#org-wizard", OrgInitWizard)

        no_org_view.add_class("hidden")
        wizard.remove_class("hidden")

    async def on_org_init_wizard_wizard_completed(
        self, message: OrgInitWizard.WizardCompleted
    ) -> None:
        """Handle wizard completion - create the org."""
        config = message.config
        self.notify(f"Creating org '{config.name}'...")

        # Create org using CLI
        await self._create_org_from_config(config)

    async def on_org_init_wizard_wizard_cancelled(
        self, message: OrgInitWizard.WizardCancelled
    ) -> None:
        """Handle wizard cancellation - go back to no-org view."""
        wizard = self.query_one("#org-wizard", OrgInitWizard)
        no_org_view = self.query_one("#no-org-view", NoOrgView)

        wizard.add_class("hidden")
        no_org_view.remove_class("hidden")

    async def _create_org_from_config(self, config: OrgConfig) -> None:
        """Create an org from wizard configuration via the shared init flow."""
        try:
            result = init_org_from_wizard(config)
            if not result.success:
                raise ValueError(result.error or "Failed to initialize organization")

            self.notify(
                f"Org '{config.name}' initialized at {config.path}",
                severity="information",
            )
            self._return_to_no_org_view()
            self._refresh_org_list()
        except CliCoreUnavailable:
            self.notify(
                "CLI module not available. Install quinnai or run from monorepo.",
                severity="error",
            )
            self._return_to_no_org_view()
        except Exception as e:
            error_msg = f"Failed to create org: {e}"
            self.notify(error_msg, severity="error")
            no_org_view = self._return_to_no_org_view()
            no_org_view.show_error(error_msg)

    def _return_to_no_org_view(self) -> NoOrgView:
        """Hide the wizard and show the no-org picker. Returns the no-org view."""
        wizard = self.query_one("#org-wizard", OrgInitWizard)
        no_org_view = self.query_one("#no-org-view", NoOrgView)
        wizard.add_class("hidden")
        no_org_view.remove_class("hidden")
        return no_org_view

    async def on_refresh_org_list(self, message: RefreshOrgList) -> None:
        """Handle request to refresh the org list."""
        self._refresh_org_list()

    # Message handlers for OrgTabBar
    async def on_org_tab_bar_org_selected(self, message: OrgTabBar.OrgSelected) -> None:
        """Handle org tab selection - switch to that org."""
        if message.org_path == self._org_registry.active_path:
            return  # already active

        self._org_registry.activate(message.org_path)
        self._update_org_tab_bar()

        if self.org_connection:
            org_info = self.org_connection.get_org_info()
            self.sub_title = f"Connected: {org_info.name}"

        await self._refresh_all_views()
        self.notify(f"Switched to {self.sub_title.replace('Connected: ', '')}")

    async def on_org_tab_bar_add_org_requested(
        self, message: OrgTabBar.AddOrgRequested
    ) -> None:
        """Handle request to add a new org connection."""
        # Show the no-org view for org selection (keeping tabs visible)
        no_org_view = self.query_one("#no-org-view", NoOrgView)
        no_org_view.remove_class("hidden")

        # Refresh the org list to show available orgs
        self._refresh_org_list()

    async def on_org_tab_bar_close_org_requested(
        self, message: OrgTabBar.CloseOrgRequested
    ) -> None:
        """Handle request to disconnect from an org."""
        self._disconnect_from_org(message.org_path)

    async def on_ceo_briefing_widget_briefing_queued(
        self, message: CEOBriefingWidget.BriefingQueued
    ) -> None:
        """Handle CEO briefing queued for delivery."""
        if not self._is_connected or not self.org_connection:
            self.notify("Cannot queue briefing: not connected to org", severity="error")
            return

        try:
            # Save briefing to config/ceo_briefing.md
            briefing_md = message.content.to_markdown()
            config_path = self.org_connection.org_path / "config" / "ceo_briefing.md"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(briefing_md)

            # If org is running, deliver briefing immediately
            org_info = self.org_connection.get_org_info()
            if org_info.status == OrgStatus.RUNNING:
                success = self.org_connection.send_ceo_briefing(briefing_md)
                if success:
                    self.notify("CEO briefing saved and delivered", severity="information")
                else:
                    self.notify("Briefing saved but delivery failed", severity="warning")
            else:
                self.notify("CEO briefing saved (will be delivered on org start)",
                           severity="information")
        except Exception as e:
            self.notify(f"Failed to save briefing: {e}", severity="error")

    def action_copy_current_view(self) -> None:
        """Copy current view content to clipboard or export to file."""
        if not self._is_connected:
            self.notify("No org connected - nothing to copy", severity="warning")
            return

        # Get active tab
        tabs = self.query_one("#org-tabs", TabbedContent)
        active_tab_id = tabs.active

        # Get the view widget for the active tab
        view = None
        try:
            if active_tab_id == "dashboard":
                view = self.query_one("#dashboard-view", DashboardView)
            elif active_tab_id == "okrs":
                view = self.query_one("#okrs-view", OKRsView)
            elif active_tab_id == "team":
                view = self.query_one("#team-view", TeamView)
            elif active_tab_id == "messages":
                view = self.query_one("#messages-view", MessagesView)
            elif active_tab_id == "logs":
                view = self.query_one("#logs-view", LogsView)
            elif active_tab_id == "settings":
                view = self.query_one("#settings-view", SettingsView)
        except Exception as e:
            self.notify(f"Failed to get view: {e}", severity="error")
            return

        if not view:
            self.notify("No active view to copy", severity="warning")
            return

        # Check if view has export_as_text method
        if not hasattr(view, "export_as_text"):
            self.notify(f"Copy not yet supported for {active_tab_id} view", severity="warning")
            return

        # Get content as text
        try:
            content = view.export_as_text()
        except Exception as e:
            self.notify(f"Failed to export view content: {e}", severity="error")
            return

        if not content:
            self.notify("View has no content to copy", severity="warning")
            return

        exporter = ClipboardExporter(self._org_registry.active_path)
        if exporter.copy(content):
            self.notify(
                f"Copied {len(content)} chars to clipboard", severity="information"
            )
        else:
            filepath = exporter.write_to_scratchpad(content, active_tab_id)
            self.notify(f"Saved to {filepath.name}", severity="information")
