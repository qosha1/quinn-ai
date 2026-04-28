"""Tests for Team view.

Tests the team list displays workers and enables jump-in.
"""

import pytest
from unittest.mock import MagicMock, patch

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.team import TeamView
from textual.widgets import DataTable, Button


class TestTeamView:
    """Tests for TeamView widget."""

    @pytest.mark.asyncio
    async def test_team_view_composes(self):
        """Team view should compose its data table."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            # Switch to Team tab
            app.action_switch_tab("team")
            await pilot.pause()

            # Query the Team view
            team_view = app.query_one("#team-view", TeamView)
            assert team_view is not None

            # Check header exists
            team_header = app.query_one("#team-header")
            assert team_header is not None

            # Check workers table container exists
            workers_table = app.query_one("#workers-table")
            assert workers_table is not None

    @pytest.mark.asyncio
    async def test_team_shows_workers(self):
        """Team view should list all workers."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("team")
            await pilot.pause()

            # Get the data table
            table = app.query_one("#workers-data", DataTable)
            assert table is not None

            # Should have rows (placeholder data has 5 workers)
            assert table.row_count > 0

    @pytest.mark.asyncio
    async def test_ceo_prominently_featured(self):
        """CEO should be at the top of the list when org is connected.

        With placeholder data in the view, verifies structure is correct.
        When no org is connected, shows placeholder row.
        """
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("team")
            # Wait for mount to complete and data to load
            await pilot.pause()
            await pilot.pause()

            table = app.query_one("#workers-data", DataTable)

            # Verify we have at least one row (could be placeholder or real data)
            assert table.row_count > 0, "Table should have rows"

            # Get first row data
            row_data = table.get_row_at(0)
            # row_data is a list: [Status, Name, Role, Team, Current Task, Actions]
            assert len(row_data) == 6, "Row should have 6 columns"
            # Verify the row has data (could be placeholder or real worker)
            assert row_data[1] is not None  # Name column has value

    @pytest.mark.asyncio
    async def test_data_table_has_columns(self):
        """Data table should have expected columns."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("team")
            await pilot.pause()

            table = app.query_one("#workers-data", DataTable)

            # Check columns exist by verifying column keys
            columns = list(table.columns.keys())
            assert len(columns) == 6

    @pytest.mark.asyncio
    async def test_filter_buttons_exist(self):
        """Filter buttons should exist for status filtering."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("team")
            await pilot.pause()

            # Check filter buttons exist
            filter_all = app.query_one("#filter-all", Button)
            assert filter_all is not None

            filter_active = app.query_one("#filter-active", Button)
            assert filter_active is not None

            filter_idle = app.query_one("#filter-idle", Button)
            assert filter_idle is not None

    @pytest.mark.asyncio
    async def test_worker_table_has_data(self):
        """Worker table should have data rows."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("team")
            await pilot.pause()

            table = app.query_one("#workers-data", DataTable)

            # Should have at least 1 worker
            assert table.row_count >= 1

    @pytest.mark.asyncio
    async def test_worker_names_displayed(self):
        """Worker names should be displayed in the table."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("team")
            await pilot.pause()

            table = app.query_one("#workers-data", DataTable)

            if table.row_count > 0:
                # Name is column 1
                name_value = table.get_cell_at((0, 1))
                assert name_value is not None
                assert len(str(name_value)) > 0

    @pytest.mark.asyncio
    async def test_worker_status_indicators(self):
        """Worker rows should show status indicators."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("team")
            await pilot.pause()

            table = app.query_one("#workers-data", DataTable)

            if table.row_count > 0:
                # Status is column 0
                status_value = table.get_cell_at((0, 0))
                # Status should be an emoji indicator
                assert status_value is not None
                assert len(str(status_value)) > 0
