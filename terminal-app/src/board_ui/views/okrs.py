"""
OKRs view - cascading objectives display.

Shows:
- Tree view of OKRs cascading Board -> CEO -> Directors -> Managers -> Workers
- Each objective shows title, key results with progress, owner
- Expandable/collapsible hierarchy
- Visual progress indicators
"""

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Label, Static, Tree
from textual.widget import Widget


class OKRsView(Widget):
    """OKRs view with cascading objectives."""

    DEFAULT_CSS = """
    OKRsView {
        layout: vertical;
        height: 100%;
    }

    #okr-header {
        height: auto;
        padding: 1;
        border-bottom: solid $secondary;
    }

    #okr-tree-container {
        height: 1fr;
    }

    Tree {
        height: 100%;
    }

    .okr-progress {
        color: $success;
    }

    .okr-owner {
        color: $text-muted;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="okr-header"):
            yield Label("Objectives & Key Results", classes="panel-title")
            yield Label("Board -> CEO -> Directors -> Managers -> Workers", classes="metric-label")

        with VerticalScroll(id="okr-tree-container"):
            tree: Tree = Tree("Organization OKRs", id="okr-tree")
            tree.root.expand()

            # Placeholder OKRs - will be populated from org connection
            board = tree.root.add("Board Objectives", expand=True)
            board.add_leaf("Q1: Ship v1.0 product [2/3 KRs complete]")
            board.add_leaf("Q1: Achieve $10k MRR [0/2 KRs complete]")

            ceo = board.add("CEO: Deliver MVP", expand=True)
            ceo.add_leaf("KR: Complete core features by Feb 15 [In Progress]")
            ceo.add_leaf("KR: Pass security audit [Not Started]")

            eng = ceo.add("VP-Eng: Technical Delivery", expand=True)
            eng.add_leaf("KR: API endpoints complete [8/10]")
            eng.add_leaf("KR: Test coverage > 80% [72%]")

            yield tree

    async def on_mount(self) -> None:
        """Load OKRs when view mounts."""
        # TODO: Load from org connection
        pass

    def refresh_okrs(self) -> None:
        """Refresh OKRs from org connection."""
        # TODO: Implement
        pass
