"""
Org tabs bar - multi-org switcher.

Shows connected organizations as tabs with:
- Active org highlighted
- Click to switch between orgs
- [+] button to add new org
- [x] button to disconnect from org
"""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Static
from textual.widget import Widget


class OrgTabBar(Widget):
    """Horizontal bar showing connected orgs with tab switching."""

    DEFAULT_CSS = """
    OrgTabBar {
        height: 3;
        dock: top;
        background: $surface-darken-1;
        padding: 0 1;
    }

    OrgTabBar.hidden {
        display: none;
    }

    #org-tabs-container {
        width: 100%;
        height: 100%;
        align: left middle;
    }

    .org-tab {
        min-width: 12;
    }

    .org-tab-close {
        min-width: 3;
        margin-right: 1;
    }

    .org-tab-active {
        background: $primary;
        color: $text;
    }

    .org-tab-inactive {
        background: $surface;
        color: $text-muted;
    }

    .org-tab-inactive:hover {
        background: $surface-lighten-1;
    }

    .org-tab-close:hover {
        background: $error;
    }

    #add-org-btn {
        min-width: 5;
        margin-left: 1;
    }
    """

    class OrgSelected(Message):
        """Message sent when user selects an org tab."""

        def __init__(self, org_path: Path) -> None:
            super().__init__()
            self.org_path = org_path

    class AddOrgRequested(Message):
        """Message sent when user clicks the [+] button."""
        pass

    class CloseOrgRequested(Message):
        """Message sent when user wants to disconnect from an org."""

        def __init__(self, org_path: Path) -> None:
            super().__init__()
            self.org_path = org_path

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._orgs: dict[Path, str] = {}  # path -> org name
        self._active_path: Optional[Path] = None
        self._tab_counter = 0  # Counter for unique tab IDs

    def compose(self) -> ComposeResult:
        with Horizontal(id="org-tabs-container"):
            yield Button("+", id="add-org-btn", variant="default")

    def update_orgs(
        self,
        orgs: dict[Path, str],
        active_path: Optional[Path] = None,
    ) -> None:
        """Update the org tabs display.

        Args:
            orgs: Dict of org_path -> org_name for connected orgs
            active_path: Path of the currently active org
        """
        self._orgs = orgs
        self._active_path = active_path
        self._rebuild_tabs()

    def _rebuild_tabs(self) -> None:
        """Rebuild the tab buttons."""
        container = self.query_one("#org-tabs-container", Horizontal)

        # Get the add button (always keep it)
        add_btn = self.query_one("#add-org-btn", Button)

        # Remove all org tabs (keep add button)
        for child in list(container.children):
            if child.id != "add-org-btn":
                child.remove()

        # Add tabs for each org (before the add button). Each org becomes
        # TWO buttons: the name (selects the tab) and a separate × button
        # (disconnects). Sharing one widget for both meant a click on the
        # × switched tabs instead of closing — quinn-ai-dl3.
        for path, name in self._orgs.items():
            is_active = path == self._active_path
            self._tab_counter += 1
            select_btn = Button(
                name,
                id=f"org-tab-{self._tab_counter}",
                classes=f"org-tab {'org-tab-active' if is_active else 'org-tab-inactive'}",
            )
            select_btn._org_path = path
            select_btn._tab_action = "select"
            close_btn = Button(
                "×",
                id=f"org-tab-close-{self._tab_counter}",
                classes=f"org-tab-close {'org-tab-active' if is_active else 'org-tab-inactive'}",
            )
            close_btn._org_path = path
            close_btn._tab_action = "close"
            container.mount(select_btn, before=add_btn)
            container.mount(close_btn, before=add_btn)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle tab button presses."""
        if event.button.id == "add-org-btn":
            self.post_message(self.AddOrgRequested())
            return

        if hasattr(event.button, "_org_path"):
            org_path = event.button._org_path
            action = getattr(event.button, "_tab_action", "select")

            if action == "close":
                self.post_message(self.CloseOrgRequested(org_path))
            elif action == "select" and org_path != self._active_path:
                self.post_message(self.OrgSelected(org_path))
