"""
Smoke test for board UI launch.

Verifies that qn board ui can launch without crashing and shows proper no-org state.
"""

import pytest
from textual.pilot import Pilot

from board_ui.app import BoardApp
from board_ui.config import BoardConfig


class TestBoardSmoke:
    """Smoke tests for board launch."""

    @pytest.mark.asyncio
    async def test_board_launches_without_crash(self):
        """Verify board app launches without crashing."""
        config = BoardConfig(
            org_paths=[],
            preferred_terminal=None,
        )

        app = BoardApp(config)

        async with app.run_test() as pilot:
            # If we get here, app launched successfully
            assert app is not None

            # Wait a moment for views to mount
            await pilot.pause(0.1)

            # App should be running
            assert app.is_running

    @pytest.mark.asyncio
    async def test_board_shows_no_org_view_initially(self):
        """Verify board shows no-org view when no orgs are available."""
        config = BoardConfig(
            org_paths=[],
            preferred_terminal=None,
        )

        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause(0.2)

            # No-org view should be visible
            no_org_view = app.query_one("#no-org-view")
            assert not no_org_view.has_class("hidden")

            # Org tabs should be hidden
            org_tabs = app.query_one("#org-tabs")
            assert org_tabs.has_class("hidden")

    @pytest.mark.asyncio
    async def test_board_keyboard_shortcuts_work(self):
        """Verify basic keyboard shortcuts don't crash."""
        config = BoardConfig(
            org_paths=[],
            preferred_terminal=None,
        )

        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Press 'r' for refresh - should not crash
            await pilot.press("r")
            await pilot.pause(0.1)

            # App should still be running
            assert app.is_running
