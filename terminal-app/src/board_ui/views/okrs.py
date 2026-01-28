"""
OKRs view - cascading objectives display.

Shows:
- Tree view of OKRs cascading Board -> CEO -> Directors -> Managers -> Workers
- Each objective shows title, key results with progress, owner
- Expandable/collapsible hierarchy
- Visual progress indicators
"""

import logging
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Label, Static, Tree
from textual.widget import Widget

if TYPE_CHECKING:
    from ..interfaces.org_connection import OKRInfo

logger = logging.getLogger(__name__)


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
        self.refresh_okrs()

    def refresh_okrs(self) -> None:
        """Refresh OKRs from org connection."""
        logger.info("refresh_okrs called")

        if not hasattr(self.app, 'org_connection') or self.app.org_connection is None:
            logger.warning("No org connection - keeping placeholder data")
            return  # Keep placeholder data

        try:
            conn = self.app.org_connection
            logger.info(f"Fetching OKRs from org connection: {conn.org_path}")
            okrs = conn.get_okrs()
            logger.info(f"Found {len(okrs)} OKRs")

            if not okrs:
                logger.info("No OKRs found - showing empty state")
                self._show_empty_state()
                return

            # Build hierarchy
            okr_dict = {okr.id: okr for okr in okrs}
            root_okrs = [okr for okr in okrs if okr.parent_id is None]
            logger.info(f"Found {len(root_okrs)} root OKRs")

            # Clear tree and rebuild
            tree = self.query_one(Tree)
            logger.info("Clearing tree and rebuilding with real OKRs")
            tree.clear()
            tree.root.expand()

            for root_okr in root_okrs:
                logger.info(f"Adding OKR: {root_okr.title}")
                self._add_okr_to_tree(tree.root, root_okr, okr_dict)

            logger.info("OKR tree rebuilt successfully")

        except Exception as e:
            logger.error(f"Error loading OKRs: {e}", exc_info=True)

    def _add_okr_to_tree(self, parent_node, okr: "OKRInfo", okr_dict: dict) -> None:
        """Recursively add OKR and its children to tree.

        Args:
            parent_node: Parent tree node
            okr: OKR to add
            okr_dict: Dictionary of all OKRs by ID for lookup
        """
        # Format OKR label
        label = self._format_okr_label(okr)

        # Check if this OKR has children
        has_children = okr.children_count > 0 or any(
            child_okr.parent_id == okr.id for child_okr in okr_dict.values()
        )

        if has_children:
            # Add as branch node (expandable)
            node = parent_node.add(label, expand=True)

            # Add key results as leaves under this OKR
            if okr.key_results:
                for kr in okr.key_results:
                    kr_label = self._format_key_result(kr)
                    node.add_leaf(kr_label)

            # Add children OKRs
            for child_okr in okr_dict.values():
                if child_okr.parent_id == okr.id:
                    self._add_okr_to_tree(node, child_okr, okr_dict)
        else:
            # No children - add key results inline or as expandable
            if okr.key_results:
                # Add OKR as branch with KRs as leaves
                node = parent_node.add(label, expand=True)
                for kr in okr.key_results:
                    kr_label = self._format_key_result(kr)
                    node.add_leaf(kr_label)
            else:
                # No children, no KRs - just add as leaf
                parent_node.add_leaf(label)

    def _format_okr_label(self, okr: "OKRInfo") -> str:
        """Format OKR label for tree display.

        Format: "Title [X/Y KRs] (Owner)"

        Args:
            okr: OKR to format

        Returns:
            Formatted label string
        """
        # Calculate progress
        completed, total = self._calculate_progress(okr)

        # Build label
        label_parts = [okr.title]

        if total > 0:
            label_parts.append(f"[{completed}/{total} KRs]")

        label_parts.append(f"({okr.owner_name})")

        return " ".join(label_parts)

    def _format_key_result(self, kr: dict) -> str:
        """Format key result for display.

        Format: "Description [current/target unit]"

        Args:
            kr: Key result dict with metric/description, current, target, unit

        Returns:
            Formatted key result string
        """
        # Support both 'metric' (database) and 'description' (legacy)
        description = kr.get("metric", kr.get("description", ""))
        current = kr.get("current", 0)
        target = kr.get("target", 0)
        unit = kr.get("unit", "")

        # Format progress indicator
        if unit:
            progress = f"[{current}/{target} {unit}]"
        else:
            progress = f"[{current}/{target}]"

        return f"{description} {progress}"

    def _calculate_progress(self, okr: "OKRInfo") -> tuple[int, int]:
        """Calculate progress from key results.

        Args:
            okr: OKR with key_results

        Returns:
            Tuple of (completed_count, total_count)
        """
        if not okr.key_results:
            return (0, 0)

        total = len(okr.key_results)
        completed = sum(
            1 for kr in okr.key_results
            if kr.get("current", 0) >= kr.get("target", 0)
        )

        return (completed, total)

    def _show_empty_state(self) -> None:
        """Show helpful message when no OKRs exist."""
        tree = self.query_one(Tree)
        tree.clear()
        tree.root.expand()
        tree.root.add_leaf("No OKRs found. Create OKRs to track organizational objectives.")
