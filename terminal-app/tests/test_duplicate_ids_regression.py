"""E2E regression tests for duplicate widget IDs bug (quinnai-qljh).

These tests would have caught the duplicate widget IDs bug that occurred when:
1. BoardApp auto-connected to a running org on startup
2. _update_org_tab_bar() was called during mount (before widgets were ready)
3. Hash-based IDs caused duplicate IDs when reconnecting to the same org

The fix uses a counter-based ID system that guarantees unique IDs.
"""

import pytest
import tempfile
from pathlib import Path
from textual.widgets import TabbedContent

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from tests.conftest import create_test_org_db


class TestDuplicateIDsRegression:
    """Regression tests for duplicate widget IDs bug."""

    @pytest.mark.asyncio
    async def test_app_auto_connects_to_running_org(self):
        """App should auto-connect to running org on startup without DuplicateIds error.

        This test exercises the auto-connect flow that exposed the duplicate widget IDs bug.
        The bug only appeared when BoardApp auto-connected to a running org on startup,
        because _update_org_tab_bar() was called before the tab bar widgets were mounted.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock org with running status
            org_path = Path(tmpdir) / "test-org"
            org_path.mkdir()

            # Create complete org database with all required tables
            create_test_org_db(org_path, status="running")

            # Create config with this org path
            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            # Launch app - should auto-discover and connect without DuplicateIds error
            async with app.run_test() as pilot:
                await pilot.pause()

                # App should be connected
                assert app._is_connected
                assert app._active_org_path == org_path

                # Org tab bar should be visible
                from board_ui.views.org_tabs import OrgTabBar
                tab_bar = app.query_one("#org-tab-bar", OrgTabBar)
                assert "hidden" not in tab_bar.classes

                # Org tabs (main content) should be visible
                org_tabs = app.query_one("#org-tabs", TabbedContent)
                assert "hidden" not in org_tabs.classes

                # No-org view should be hidden
                from board_ui.views.no_org import NoOrgView
                no_org_view = app.query_one("#no-org-view", NoOrgView)
                assert "hidden" in no_org_view.classes

    @pytest.mark.asyncio
    async def test_app_reconnects_to_same_org_twice(self):
        """App should handle disconnect and reconnect to same org without duplicate IDs.

        This test specifically exercises the scenario that caused duplicate IDs with hash-based IDs:
        1. Connect to org (creates tab with ID based on org path hash)
        2. Disconnect from org (removes tab)
        3. Reconnect to same org (would create tab with SAME hash-based ID -> duplicate!)

        With counter-based IDs, each reconnect gets a new unique ID.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock org
            org_path = Path(tmpdir) / "test-org"
            org_path.mkdir()

            # Create complete org database (stopped status since we manually connect)
            create_test_org_db(org_path, status="stopped")

            # Create app with no auto-connect (empty org_paths)
            config = BoardConfig(org_paths=[])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Connect to org
                await app._connect_to_org(org_path)
                await pilot.pause()

                assert app._is_connected
                assert org_path in app._org_connections

                # Disconnect from org
                app._disconnect_from_org(org_path)
                await pilot.pause()

                assert not app._is_connected
                assert org_path not in app._org_connections

                # Reconnect to same org - this should NOT raise DuplicateIds error
                await app._connect_to_org(org_path)
                await pilot.pause()

                assert app._is_connected
                assert org_path in app._org_connections

                # Should have org tab bar visible with tab for this org
                from board_ui.views.org_tabs import OrgTabBar
                tab_bar = app.query_one("#org-tab-bar", OrgTabBar)
                assert "hidden" not in tab_bar.classes
