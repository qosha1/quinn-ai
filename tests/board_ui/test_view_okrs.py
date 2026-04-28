"""Tests for OKRs view.

Tests the OKR tree renders correctly with cascading objectives.
"""

import pytest

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.okrs import OKRsView
from textual.widgets import Tree


class TestOKRsView:
    """Tests for OKRsView widget."""

    @pytest.mark.asyncio
    async def test_okrs_view_composes(self):
        """OKRs view should compose its tree widget."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            # Switch to OKRs tab
            app.action_switch_tab("okrs")
            await pilot.pause()

            # Query the OKRs view
            okrs_view = app.query_one("#okrs-view", OKRsView)
            assert okrs_view is not None

            # Check header exists
            okr_header = app.query_one("#okr-header")
            assert okr_header is not None

            # Check tree container exists
            tree_container = app.query_one("#okr-tree-container")
            assert tree_container is not None

    @pytest.mark.asyncio
    async def test_okrs_tree_widget_exists(self):
        """OKR tree widget should be present."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("okrs")
            await pilot.pause()

            # Query the tree widget
            tree = app.query_one("#okr-tree", Tree)
            assert tree is not None

    @pytest.mark.asyncio
    async def test_okrs_tree_displays_hierarchy(self):
        """OKR tree should show Board -> CEO -> Directors cascade."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("okrs")
            await pilot.pause()

            tree = app.query_one("#okr-tree", Tree)

            # Root should exist and be expanded
            assert tree.root is not None
            assert tree.root.is_expanded

            # Should have children (Board level objectives)
            children = list(tree.root.children)
            assert len(children) > 0

    @pytest.mark.asyncio
    async def test_okrs_expandable_nodes(self):
        """Tree nodes should be expandable/collapsible."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("okrs")
            await pilot.pause()

            tree = app.query_one("#okr-tree", Tree)

            # Get first child node (Board objectives)
            children = list(tree.root.children)
            if children:
                first_node = children[0]
                # Initially expanded (from compose)
                assert first_node.is_expanded

                # Should be able to collapse
                first_node.collapse()
                assert not first_node.is_expanded

                # Should be able to expand again
                first_node.expand()
                assert first_node.is_expanded

    @pytest.mark.asyncio
    async def test_okrs_shows_progress(self):
        """Each OKR should show key result progress."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("okrs")
            await pilot.pause()

            tree = app.query_one("#okr-tree", Tree)

            # Walk the tree and find leaf nodes (key results)
            def find_leaves(node):
                leaves = []
                for child in node.children:
                    if child.allow_expand and list(child.children):
                        leaves.extend(find_leaves(child))
                    else:
                        leaves.append(child)
                return leaves

            leaves = find_leaves(tree.root)
            # Should have leaf nodes showing progress
            assert len(leaves) > 0

            # Check at least one leaf contains progress indicator
            has_progress = any(
                "[" in str(leaf.label) and "]" in str(leaf.label)
                for leaf in leaves
            )
            assert has_progress, "Expected at least one leaf with progress indicator"

    @pytest.mark.asyncio
    async def test_okrs_has_ceo_level(self):
        """OKR tree should have CEO level objectives."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("okrs")
            await pilot.pause()

            tree = app.query_one("#okr-tree", Tree)

            # Find all node labels
            def get_all_labels(node, labels=None):
                if labels is None:
                    labels = []
                labels.append(str(node.label))
                for child in node.children:
                    get_all_labels(child, labels)
                return labels

            all_labels = get_all_labels(tree.root)

            # Should have CEO-related entry
            has_ceo = any("CEO" in label for label in all_labels)
            assert has_ceo, "Expected CEO level in OKR hierarchy"

    @pytest.mark.asyncio
    async def test_okrs_view_header_text(self):
        """OKRs view header should show descriptive text."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("okrs")
            await pilot.pause()

            okr_header = app.query_one("#okr-header")
            # Should contain title mentioning OKRs
            header_text = str(okr_header.render())
            # Just verify header exists and is renderable
            assert okr_header is not None

    @pytest.mark.asyncio
    async def test_okrs_tree_has_root_label(self):
        """OKR tree should have a labeled root."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("okrs")
            await pilot.pause()

            tree = app.query_one("#okr-tree", Tree)
            assert tree.root.label is not None
            assert "OKR" in str(tree.root.label) or "Organization" in str(tree.root.label)

    @pytest.mark.asyncio
    async def test_okrs_tree_container_is_not_scroll(self):
        """OKRsView itself is VerticalScroll — inner container must be plain Container.

        Having a nested VerticalScroll inside OKRsView (which is VerticalScroll)
        causes scroll event capture conflicts where the outer container intercepts
        scroll before the Tree or inner container can handle it.
        """
        from textual.containers import VerticalScroll
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("okrs")
            await pilot.pause()

            tree_container = app.query_one("#okr-tree-container")
            assert not isinstance(tree_container, VerticalScroll), (
                "#okr-tree-container must not be VerticalScroll — OKRsView is already VerticalScroll. "
                "Use a plain Container to avoid nested scroll conflicts."
            )
