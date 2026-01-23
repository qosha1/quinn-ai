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
        margin-right: 1;
        min-width: 12;
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

        # Add tabs for each org (before the add button)
        for path, name in self._orgs.items():
            is_active = path == self._active_path
            # Use counter for unique ID each time (avoid duplicate ID errors)
            self._tab_counter += 1
            tab = Button(
                f"{name} ×",
                id=f"org-tab-{self._tab_counter}",
                classes=f"org-tab {'org-tab-active' if is_active else 'org-tab-inactive'}",
            )
            tab._org_path = path  # Store path on button
            container.mount(tab, before=add_btn)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle tab button presses."""
        if event.button.id == "add-org-btn":
            self.post_message(self.AddOrgRequested())
            return

        # Check if it's an org tab
        if hasattr(event.button, "_org_path"):
            org_path = event.button._org_path

            # If clicked on the "×" part (button text ends with ×)
            # TODO: Implement separate close button per tab
            # For now, clicking the tab switches to it
            if org_path != self._active_path:
                self.post_message(self.OrgSelected(org_path))
