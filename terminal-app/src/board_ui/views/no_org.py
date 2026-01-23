"""
No Org Connected view.

Displayed when the board launches but no org is connected.
Offers options to:
- Connect to a running org
- Start an available org
- Create a new org (init wizard)
"""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Center
from textual.widgets import Button, Label, ListItem, ListView, Static
from textual.widget import Widget


class OrgListItem(ListItem):
    """List item for an available org."""

    def __init__(self, org_path: Path, status: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.org_path = org_path
        self.org_status = status

    def compose(self) -> ComposeResult:
        status_class = "status-running" if self.org_status == "running" else "status-stopped"
        status_icon = "🟢" if self.org_status == "running" else "⚫"

        yield Label(f"{status_icon} {self.org_path.name}")
        yield Label(f"  {self.org_path}", classes="org-path")


class NoOrgView(Widget):
    """View shown when no org is connected."""

    DEFAULT_CSS = """
    NoOrgView {
        layout: vertical;
        align: center middle;
        height: 100%;
    }

    #no-org-container {
        width: 70;
        height: auto;
        border: solid $primary;
        padding: 2 4;
    }

    #no-org-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #no-org-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    #org-list {
        height: auto;
        max-height: 15;
        border: solid $secondary;
        margin-bottom: 2;
    }

    .org-path {
        color: $text-muted;
        text-style: italic;
    }

    #action-buttons {
        layout: horizontal;
        align: center middle;
        height: auto;
        margin-top: 1;
    }

    #action-buttons Button {
        margin: 0 1;
    }

    #scanning-label {
        text-align: center;
        color: $text-muted;
        margin: 1 0;
    }
    """

    def __init__(
        self,
        available_orgs: Optional[list[tuple[Path, str]]] = None,
        **kwargs,
    ) -> None:
        """Initialize the no-org view.

        Args:
            available_orgs: List of (path, status) tuples for available orgs
        """
        super().__init__(**kwargs)
        self.available_orgs = available_orgs or []

    def compose(self) -> ComposeResult:
        with Center():
            with Container(id="no-org-container"):
                yield Label("No Organization Connected", id="no-org-title")
                yield Label(
                    "Connect to an existing org or create a new one",
                    id="no-org-subtitle",
                )

                if self.available_orgs:
                    yield Label(
                        f"Found {len(self.available_orgs)} available org(s):",
                        id="scanning-label",
                    )
                    with ListView(id="org-list"):
                        for org_path, status in self.available_orgs:
                            yield OrgListItem(org_path, status)
                else:
                    yield Label(
                        "No orgs found. Create one to get started.",
                        id="scanning-label",
                    )

                with Container(id="action-buttons"):
                    if self.available_orgs:
                        yield Button(
                            "Connect",
                            id="connect-btn",
                            variant="primary",
                        )
                        yield Button(
                            "Start Selected",
                            id="start-btn",
                            variant="default",
                        )
                    yield Button(
                        "New Org",
                        id="new-org-btn",
                        variant="success" if not self.available_orgs else "default",
                    )
                    yield Button(
                        "Refresh",
                        id="refresh-btn",
                        variant="default",
                    )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "connect-btn":
            await self._connect_to_selected()
        elif event.button.id == "start-btn":
            await self._start_selected()
        elif event.button.id == "new-org-btn":
            await self._show_new_org_wizard()
        elif event.button.id == "refresh-btn":
            await self._refresh_org_list()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle org selection."""
        if isinstance(event.item, OrgListItem):
            # Enable connect button for running orgs
            connect_btn = self.query_one("#connect-btn", Button)
            start_btn = self.query_one("#start-btn", Button)

            if event.item.org_status == "running":
                connect_btn.disabled = False
                start_btn.disabled = True
            else:
                connect_btn.disabled = True
                start_btn.disabled = False

    async def _connect_to_selected(self) -> None:
        """Connect to the selected running org."""
        org_list = self.query_one("#org-list", ListView)
        if org_list.highlighted_child and isinstance(org_list.highlighted_child, OrgListItem):
            org_path = org_list.highlighted_child.org_path
            # Post message to app to connect
            self.post_message(ConnectToOrg(org_path))

    async def _start_selected(self) -> None:
        """Start the selected stopped org."""
        org_list = self.query_one("#org-list", ListView)
        if org_list.highlighted_child and isinstance(org_list.highlighted_child, OrgListItem):
            org_path = org_list.highlighted_child.org_path
            self.post_message(StartOrg(org_path))

    async def _show_new_org_wizard(self) -> None:
        """Show the new org wizard."""
        self.post_message(ShowNewOrgWizard())

    async def _refresh_org_list(self) -> None:
        """Refresh the list of available orgs."""
        self.post_message(RefreshOrgList())


# Custom messages for communication with parent app
from textual.message import Message


class ConnectToOrg(Message):
    """Request to connect to an org."""

    def __init__(self, org_path: Path) -> None:
        super().__init__()
        self.org_path = org_path


class StartOrg(Message):
    """Request to start an org."""

    def __init__(self, org_path: Path) -> None:
        super().__init__()
        self.org_path = org_path


class ShowNewOrgWizard(Message):
    """Request to show the new org wizard."""
    pass


class RefreshOrgList(Message):
    """Request to refresh the org list."""
    pass
