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
        self._org_connection: Optional[QuinnAIOrgConnection] = None
        self._is_connected = False

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()

        # Start with no-org view, will be replaced when connected
        yield NoOrgView(id="no-org-view")

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

    @property
    def org_connection(self) -> Optional[QuinnAIOrgConnection]:
        """Get the current org connection if connected."""
        return self._org_connection if self._is_connected else None

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific tab."""
        if not self._is_connected:
            return
        tabs = self.query_one("#org-tabs", TabbedContent)
        tabs.active = tab_id

    def action_refresh(self) -> None:
        """Refresh all views."""
        if self._is_connected:
            self.notify("Refreshing...")
            # Views will implement their own refresh logic
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
            self._org_connection = QuinnAIOrgConnection(org_path)
            self._is_connected = True

            # Hide no-org view, show tabs
            self.query_one("#no-org-view").add_class("hidden")
            self.query_one("#org-tabs").remove_class("hidden")

            org_info = self._org_connection.get_org_info()
            self.notify(f"Connected to {org_info.name}")
            self.sub_title = f"Connected: {org_info.name}"

        except OrgNotFound:
            self.notify(f"Org not found at {org_path}", severity="error")
        except DatabaseNotFound:
            self.notify(f"Org not initialized at {org_path}", severity="warning")
        except OrgConnectionError as e:
            self.notify(f"Connection failed: {e}", severity="error")

    def _disconnect_from_org(self) -> None:
        """Disconnect from the current org."""
        if self._org_connection:
            self._org_connection.close()
            self._org_connection = None
        self._is_connected = False

        # Show no-org view, hide tabs
        self.query_one("#no-org-view").remove_class("hidden")
        self.query_one("#org-tabs").add_class("hidden")

        self.sub_title = "Organization Oversight"
        self.notify("Disconnected from org")

    def _refresh_org_list(self) -> None:
        """Refresh the list of available orgs."""
        available_orgs = discover_available_orgs(self.config.org_paths)
        org_list = [(org.path, org.status) for org in available_orgs]

        no_org_view = self.query_one("#no-org-view", NoOrgView)
        no_org_view.available_orgs = org_list
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
            self.notify(result.message, severity="error")

    async def on_show_new_org_wizard(self, message: ShowNewOrgWizard) -> None:
        """Handle request to show the new org wizard."""
        # TODO: Implement org init wizard
        self.notify("Org wizard coming soon", severity="warning")

    async def on_refresh_org_list(self, message: RefreshOrgList) -> None:
        """Handle request to refresh the org list."""
        self._refresh_org_list()
