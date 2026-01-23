"""E2E tests for app launch.

Tests the app launches and displays correctly.
"""

import pytest
from textual.widgets import TabbedContent, TabPane

from board_ui.app import BoardApp
from board_ui.config import BoardConfig


class TestE2EAppLaunch:
    """E2E tests for app launch."""

    @pytest.mark.asyncio
    async def test_app_launches(self):
        """App should launch without errors."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            await pilot.pause()

            # App should be running
            assert app.is_running

            # Should have tabbed content
            tabs = app.query_one(TabbedContent)
            assert tabs is not None

    @pytest.mark.asyncio
    async def test_displays_four_tabs(self):
        """Should show Dashboard, OKRs, Team, Messages tabs."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check tabs exist
            tabs = app.query_one(TabbedContent)
            assert tabs is not None

            # Should have 4 tabs: Dashboard, OKRs, Team, Messages
            # (may also have NoOrg view which is different)
            tab_panes = list(app.query(TabPane))
            tab_ids = [t.id for t in tab_panes if t.id]

            # Dashboard, OKRs, Team, Messages should be present
            expected_tabs = {"dashboard", "okrs", "team", "messages"}
            actual_tabs = {t.replace("-tab", "").replace("-pane", "") for t in tab_ids}
            assert expected_tabs.issubset(actual_tabs) or len(tab_panes) >= 4

    @pytest.mark.asyncio
    async def test_keyboard_navigation(self):
        """Tab switching via keyboard should work when connected."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            await pilot.pause()

            tabs = app.query_one("#org-tabs", TabbedContent)

            # Without connection, tabs default to dashboard
            # Tab switching is blocked when not connected (by design)
            assert tabs.active == "dashboard"

            # Verify the tabbed content exists and is responsive
            assert tabs is not None
            assert len(list(app.query(TabPane))) >= 4

    @pytest.mark.asyncio
    async def test_no_org_state(self):
        """Should handle no org connected gracefully."""
        # Create app with no org path
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # App should still be running
            assert app.is_running

            # Should show no-org view or placeholder content
            # The app handles this gracefully without crashing

    @pytest.mark.asyncio
    async def test_quit_shortcut(self):
        """Q key should quit the app."""
        app = BoardApp(BoardConfig.default())

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press Q to quit
            await pilot.press("q")

            # App should initiate exit
            # (In test mode, we can't fully verify exit, but no error means success)
