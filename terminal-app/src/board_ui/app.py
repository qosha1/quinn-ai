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
from .services import (
    QuinnAIOrgConnection,
    OrgConnectionError,
    OrgNotFound,
    DatabaseNotFound,
    discover_available_orgs,
    start_org,
)


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

    CSS = """
    Screen {
        background: $surface;
    }

    TabbedContent {
        height: 100%;
    }

    TabPane {
        padding: 1 2;
        height: 1fr;
    }

    .panel {
        border: solid $primary;
        padding: 1 2;
        margin: 1 0;
    }

    .panel-title {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    .metric-value {
        text-style: bold;
        color: $success;
    }

    .metric-label {
        color: $text-muted;
    }

    .status-running {
        color: $success;
    }

    .status-stopped {
        color: $warning;
    }

    .status-error {
        color: $error;
    }

    .worker-ceo {
        text-style: bold;
        color: $primary;
    }

    .worker-active {
        color: $success;
    }

    .worker-idle {
        color: $text-muted;
    }

    .message-unread {
        text-style: bold;
    }

    .message-priority-high {
        color: $error;
    }

    .action-button {
        margin: 0 1;
    }

    #no-org-panel {
        align: center middle;
        height: 100%;
    }

    #no-org-content {
        width: 60;
        height: auto;
        border: solid $primary;
        padding: 2 4;
    }

    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("d", "switch_tab('dashboard')", "Dashboard", show=True),
        Binding("o", "switch_tab('okrs')", "OKRs", show=True),
        Binding("t", "switch_tab('team')", "Team", show=True),
        Binding("m", "switch_tab('messages')", "Messages", show=True),
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
        # Multi-org support: store connections by path
        self._org_connections: dict[Path, QuinnAIOrgConnection] = {}
        self._active_org_path: Optional[Path] = None

    @property
    def org_connection(self) -> Optional[QuinnAIOrgConnection]:
        """Get the current org connection for backward compatibility."""
        if self._active_org_path:
            return self._org_connections.get(self._active_org_path)
        return None

    @property
    def _is_connected(self) -> bool:
        """Check if connected to any org."""
        return self._active_org_path is not None

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
        """Connect to an organization.

        Args:
            org_path: Path to the org folder
        """
        try:
            # Create connection and store in multi-org dict
            connection = QuinnAIOrgConnection(org_path)
            self._org_connections[org_path] = connection
            self._active_org_path = org_path

            # Hide no-org view, show tabs and org tab bar
            self.query_one("#no-org-view").add_class("hidden")
            self.query_one("#org-tabs").remove_class("hidden")
            self.query_one("#org-tab-bar").remove_class("hidden")

            org_info = connection.get_org_info()
            self.notify(f"Connected to {org_info.name}")
            self.sub_title = f"Connected: {org_info.name}"

            # Update org tab bar
            self._update_org_tab_bar()

            # Refresh all views with new connection data
            await self._refresh_all_views()

        except OrgNotFound:
            error_msg = f"Org not found at {org_path}"
            self.notify(error_msg, severity="error")
            no_org_view = self.query_one("#no-org-view", NoOrgView)
            no_org_view.show_error(error_msg)
        except DatabaseNotFound:
            error_msg = f"Org not initialized at {org_path}"
            self.notify(error_msg, severity="warning")
            no_org_view = self.query_one("#no-org-view", NoOrgView)
            no_org_view.show_error(error_msg)
        except OrgConnectionError as e:
            error_msg = f"Connection failed: {e}"
            self.notify(error_msg, severity="error")
            no_org_view = self.query_one("#no-org-view", NoOrgView)
            no_org_view.show_error(error_msg)

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

    def _update_org_tab_bar(self) -> None:
        """Update the org tab bar with current connections."""
        tab_bar = self.query_one("#org-tab-bar", OrgTabBar)

        # Build org dict: path -> name
        orgs: dict[Path, str] = {}
        for path, conn in self._org_connections.items():
            try:
                info = conn.get_org_info()
                orgs[path] = info.name
            except Exception:
                orgs[path] = path.name  # Fallback to folder name

        tab_bar.update_orgs(orgs, self._active_org_path)

    def _disconnect_from_org(self, org_path: Optional[Path] = None) -> None:
        """Disconnect from an org (or current org if not specified).

        Args:
            org_path: Path to disconnect. If None, disconnects active org.
        """
        path_to_disconnect = org_path or self._active_org_path
        if not path_to_disconnect:
            return

        # Close and remove connection
        if path_to_disconnect in self._org_connections:
            self._org_connections[path_to_disconnect].close()
            del self._org_connections[path_to_disconnect]

        # If disconnecting active org, switch to another or go to no-org view
        if path_to_disconnect == self._active_org_path:
            if self._org_connections:
                # Switch to another connected org
                self._active_org_path = next(iter(self._org_connections.keys()))
                org_info = self.org_connection.get_org_info()
                self.sub_title = f"Connected: {org_info.name}"
                self._update_org_tab_bar()
            else:
                # No more orgs connected
                self._active_org_path = None
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
        """Create an org from wizard configuration.

        Uses the shared org_init module to ensure CLI and wizard
        create orgs identically.
        """
        # Lazy import: cli module may not be available when terminal-app
        # is installed as a standalone package
        try:
            from cli.core.org_init import (
                OrgInitConfig,
                ProviderConfig,
                ObjectiveConfig,
                KeyResultConfig,
                CEOBriefingConfig,
                init_org,
            )
        except ModuleNotFoundError:
            self.notify(
                "CLI module not available. Install quinnai-cli or run from monorepo.",
                severity="error",
            )
            # Go back to no-org view
            wizard = self.query_one("#org-wizard", OrgInitWizard)
            no_org_view = self.query_one("#no-org-view", NoOrgView)
            wizard.add_class("hidden")
            no_org_view.remove_class("hidden")
            return

        try:
            if not config.path:
                raise ValueError("Org path is required")

            # Convert wizard config to shared OrgInitConfig
            init_config = OrgInitConfig(
                path=config.path,
                name=config.name,
                ceo_name="CEO",
                ceo_role="CEO",
                providers=[
                    ProviderConfig(
                        id=p.id,
                        enabled=p.enabled,
                        api_key=p.api_key,
                    )
                    for p in config.providers
                    if p.enabled
                ],
                objectives=[
                    ObjectiveConfig(
                        title=obj.title,
                        key_results=[
                            KeyResultConfig(
                                metric=kr.metric,
                                target=kr.target,
                                unit=kr.unit,
                            )
                            for kr in obj.key_results
                        ],
                    )
                    for obj in config.objectives
                ],
                ceo_briefing=CEOBriefingConfig(
                    context=config.ceo_briefing.context,
                    goals=config.ceo_briefing.requirements,  # Map requirements to goals
                    constraints=config.ceo_briefing.constraints,
                    initial_action=config.ceo_briefing.success_criteria,  # Map success_criteria to initial_action
                ) if config.ceo_briefing else None,
            )

            # Initialize the org using shared module
            result = init_org(init_config)

            if not result.success:
                raise ValueError(result.error or "Failed to initialize organization")

            self.notify(
                f"Org '{config.name}' initialized at {config.path}",
                severity="information"
            )

            # Hide wizard and show no-org view with new org
            wizard = self.query_one("#org-wizard", OrgInitWizard)
            wizard.add_class("hidden")

            # Refresh to show the new org, then auto-connect
            self._refresh_org_list()

            # Don't auto-start - user can click "Start" when ready
            no_org_view = self.query_one("#no-org-view", NoOrgView)
            no_org_view.remove_class("hidden")

        except Exception as e:
            error_msg = f"Failed to create org: {e}"
            self.notify(error_msg, severity="error")
            # Go back to no-org view
            wizard = self.query_one("#org-wizard", OrgInitWizard)
            no_org_view = self.query_one("#no-org-view", NoOrgView)
            wizard.add_class("hidden")
            no_org_view.remove_class("hidden")
            no_org_view.show_error(error_msg)

    async def on_refresh_org_list(self, message: RefreshOrgList) -> None:
        """Handle request to refresh the org list."""
        self._refresh_org_list()

    # Message handlers for OrgTabBar
    async def on_org_tab_bar_org_selected(self, message: OrgTabBar.OrgSelected) -> None:
        """Handle org tab selection - switch to that org."""
        if message.org_path == self._active_org_path:
            return  # Already active

        self._active_org_path = message.org_path
        self._update_org_tab_bar()

        # Update subtitle
        if self.org_connection:
            org_info = self.org_connection.get_org_info()
            self.sub_title = f"Connected: {org_info.name}"

        # Refresh views with new org's data
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
            from cli.core.constants import OrgStatus
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
