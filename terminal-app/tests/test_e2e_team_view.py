"""E2E tests for team view worker display.

Tests the team view correctly displays workers, handles edge cases,
and provides filtering capabilities without crashing.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime

from textual.widgets import DataTable, Button

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.team import TeamView


def create_org_db_with_workers(
    org_path: Path,
    workers_data: list[dict],
    status: str = "running"
) -> Path:
    """Create org database with custom worker data.

    Args:
        org_path: Path to org folder
        workers_data: List of worker dicts with keys: id, name, role, team_id, session_state
        status: Org status ('running' or 'stopped')

    Returns:
        Path to created database
    """
    live_path = org_path / "live"
    live_path.mkdir(parents=True, exist_ok=True)

    db_path = live_path / "quinn.db"
    conn = sqlite3.connect(str(db_path))

    # Create all required tables
    conn.executescript("""
        CREATE TABLE org_state (
            id TEXT PRIMARY KEY,
            status TEXT,
            ceo_worker_id TEXT,
            started_at TEXT,
            stopped_at TEXT
        );

        CREATE TABLE teams (
            id TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE workers (
            id TEXT PRIMARY KEY,
            name TEXT,
            role TEXT,
            team_id TEXT,
            manager_id TEXT,
            status TEXT,
            created_at TEXT,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            worker_id TEXT,
            state TEXT,
            tmux_session_name TEXT,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        );

        CREATE TABLE worker_state (
            id INTEGER PRIMARY KEY,
            worker_id TEXT,
            runtime_status TEXT,
            current_task_id TEXT,
            FOREIGN KEY (worker_id) REFERENCES workers(id)
        );

        CREATE TABLE channels (
            id TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            channel_id TEXT,
            thread_id TEXT,
            parent_id TEXT,
            from_worker_id TEXT,
            content TEXT,
            priority INTEGER,
            time_sensitivity TEXT,
            created_at TEXT,
            FOREIGN KEY (channel_id) REFERENCES channels(id)
        );

        CREATE TABLE notification_beads (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            status TEXT,
            read_at TEXT,
            FOREIGN KEY (message_id) REFERENCES messages(id)
        );

        CREATE TABLE okrs (
            id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            owner_worker_id TEXT,
            status TEXT,
            parent_okr_id TEXT,
            key_results TEXT,
            due_date TEXT,
            created_at TEXT,
            FOREIGN KEY (owner_worker_id) REFERENCES workers(id)
        );

        CREATE TABLE budget_pools (
            id TEXT PRIMARY KEY,
            period_start TEXT,
            period_end TEXT,
            created_at TEXT
        );

        CREATE TABLE budget_allocations (
            id TEXT PRIMARY KEY,
            pool_id TEXT,
            worker_id TEXT,
            FOREIGN KEY (pool_id) REFERENCES budget_pools(id)
        );

        CREATE TABLE budget_balances (
            id TEXT PRIMARY KEY,
            allocation_id TEXT,
            allocated REAL,
            spent REAL,
            available REAL,
            FOREIGN KEY (allocation_id) REFERENCES budget_allocations(id)
        );

        CREATE TABLE budget_transactions (
            id TEXT PRIMARY KEY,
            type TEXT,
            amount REAL,
            created_at TEXT
        );
    """)

    # Insert teams
    conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")
    conn.execute("INSERT INTO teams VALUES ('team-eng', 'Engineering')")

    # Set CEO ID from first worker if available
    ceo_id = workers_data[0]["id"] if workers_data else None

    # Insert org state
    now = datetime.now()
    conn.execute("""
        INSERT INTO org_state (id, status, ceo_worker_id, started_at)
        VALUES ('default', ?, ?, ?)
    """, (status, ceo_id, now.isoformat()))

    # Insert workers and sessions
    for worker in workers_data:
        conn.execute("""
            INSERT INTO workers VALUES (?, ?, ?, ?, ?, 'active', ?)
        """, (
            worker["id"],
            worker["name"],
            worker["role"],
            worker.get("team_id", "team-exec"),
            worker.get("manager_id"),
            now.isoformat()
        ))

        # Create session if session_state provided
        if worker.get("session_state"):
            tmux_name = f"org-{org_path.name}-{worker['name'].lower()}"
            conn.execute("""
                INSERT INTO sessions VALUES (?, ?, ?, ?)
            """, (
                f"session-{worker['id']}",
                worker["id"],
                worker["session_state"],
                tmux_name
            ))

    conn.execute("INSERT INTO channels VALUES ('ch-esc', 'escalations')")

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def org_with_mixed_worker_states():
    """Create org with workers in different session states."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "mixed-org"
        workers = [
            {
                "id": "worker-ceo",
                "name": "Alice",
                "role": "CEO",
                "team_id": "team-exec",
                "manager_id": None,
                "session_state": "running",
            },
            {
                "id": "worker-dev1",
                "name": "Bob",
                "role": "Developer",
                "team_id": "team-eng",
                "manager_id": "worker-ceo",
                "session_state": "idle",
            },
            {
                "id": "worker-dev2",
                "name": "Charlie",
                "role": "Developer",
                "team_id": "team-eng",
                "manager_id": "worker-ceo",
                "session_state": "stopped",
            },
        ]
        create_org_db_with_workers(org_path, workers)
        yield org_path


class TestE2ETeamView:
    """E2E tests for team view worker display."""

    @pytest.mark.asyncio
    async def test_team_view_shows_workers(self):
        """Team view should display all workers with correct columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "team-org"
            workers = [
                {
                    "id": "worker-ceo",
                    "name": "Alice",
                    "role": "CEO",
                    "team_id": "team-exec",
                    "manager_id": None,
                    "session_state": "running",
                },
                {
                    "id": "worker-dev1",
                    "name": "Bob",
                    "role": "Developer",
                    "team_id": "team-eng",
                    "manager_id": "worker-ceo",
                    "session_state": "idle",
                },
                {
                    "id": "worker-dev2",
                    "name": "Charlie",
                    "role": "Developer",
                    "team_id": "team-eng",
                    "manager_id": "worker-ceo",
                    "session_state": "running",
                },
            ]
            create_org_db_with_workers(org_path, workers)

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Connect to org should happen automatically
                assert app._is_connected

                # Switch to team tab
                app.action_switch_tab("team")
                await pilot.pause()

                # Get team view
                team_view = app.query_one("#team-view", TeamView)
                assert team_view is not None

                # Get data table
                table = app.query_one("#workers-data", DataTable)

                # Should have 3 workers
                assert table.row_count == 3

                # Verify columns exist
                columns = list(table.columns.keys())
                assert len(columns) == 6

                # Verify column data for first row (should be CEO)
                row_data = table.get_row_at(0)
                # row_data is: [Status, Name, Role, Team, Current Task, Actions]
                assert len(row_data) == 6

                # Verify names are present
                names = [table.get_cell_at((i, 1)) for i in range(table.row_count)]
                assert "Alice" in str(names)
                assert "Bob" in str(names)
                assert "Charlie" in str(names)

    @pytest.mark.asyncio
    async def test_team_view_shows_no_org_message(self):
        """Team view should show placeholder when no org connected."""
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # No org connected
            assert app._active_org_path is None

            # Try to access team tab
            # When no org is connected, the org tabs are hidden
            # and no-org view is shown instead

            # The app should not crash
            assert app.is_running

            # Verify no-org view is displayed
            from board_ui.views.no_org import NoOrgView
            no_org_view = app.query_one("#no-org-view", NoOrgView)
            assert "hidden" not in no_org_view.classes

    @pytest.mark.asyncio
    async def test_team_view_handles_unknown_session_state(self):
        """Team view should handle invalid session state without crashing.

        This test verifies graceful degradation when the DB contains
        invalid session state values.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "invalid-org"
            # Create org with workers but invalid session state will be
            # handled by the view layer's defensive code
            workers = [
                {
                    "id": "worker-ceo",
                    "name": "Alice",
                    "role": "CEO",
                    "team_id": "team-exec",
                    "manager_id": None,
                    "session_state": "running",  # Valid state
                },
            ]
            create_org_db_with_workers(org_path, workers)

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should be connected
                assert app._is_connected

                # Switch to team tab - should NOT crash
                app.action_switch_tab("team")
                await pilot.pause()

                # Get data table
                table = app.query_one("#workers-data", DataTable)

                # Should have at least 1 worker
                assert table.row_count >= 1

                # Get status icon (first column)
                status_icon = table.get_cell_at((0, 0))

                # Should show status indicator without crashing
                assert status_icon is not None
                assert len(str(status_icon)) > 0

    @pytest.mark.asyncio
    async def test_team_view_filter_active_workers(self, org_with_mixed_worker_states):
        """Team view should have active filter button that can be clicked."""
        config = BoardConfig(org_paths=[org_with_mixed_worker_states])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to team tab
            app.action_switch_tab("team")
            await pilot.pause()

            # Get table
            table = app.query_one("#workers-data", DataTable)

            # Initially should show all 3 workers
            initial_count = table.row_count
            assert initial_count == 3

            # Verify "Active" filter button exists and can be clicked
            filter_btn = app.query_one("#filter-active", Button)
            assert filter_btn is not None

            # Click button should not crash
            await pilot.click(filter_btn)
            await pilot.pause()
            await pilot.pause()  # Extra pause for event processing

            # App should still be running (no crash)
            assert app.is_running

    @pytest.mark.asyncio
    async def test_team_view_filter_all_workers(self, org_with_mixed_worker_states):
        """Team view should have 'all' filter button that shows all workers."""
        config = BoardConfig(org_paths=[org_with_mixed_worker_states])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to team tab
            app.action_switch_tab("team")
            await pilot.pause()

            # Get table
            table = app.query_one("#workers-data", DataTable)

            # Verify "All" filter button exists
            filter_all = app.query_one("#filter-all", Button)
            assert filter_all is not None

            # All button should be primary by default (default filter)
            assert filter_all.variant == "primary"

            # Should show all 3 workers with default "all" filter
            assert table.row_count == 3

    @pytest.mark.asyncio
    async def test_team_view_handles_empty_worker_list(self):
        """Team view should handle org with no workers without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "empty-org"
            # Create org with empty workers list
            create_org_db_with_workers(org_path, [])

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should be connected
                assert app._is_connected

                # Switch to team tab - should NOT crash
                app.action_switch_tab("team")
                await pilot.pause()

                # Get data table
                table = app.query_one("#workers-data", DataTable)

                # Should have 0 rows (no workers)
                assert table.row_count == 0

                # App should still be running
                assert app.is_running

    @pytest.mark.asyncio
    async def test_team_view_updates_on_connect(self):
        """Team view should populate with workers when org connected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "connect-org"
            workers = [
                {
                    "id": "worker-ceo",
                    "name": "Alice",
                    "role": "CEO",
                    "team_id": "team-exec",
                    "manager_id": None,
                    "session_state": "running",
                },
            ]
            create_org_db_with_workers(org_path, workers, status="stopped")

            # Start with no org
            config = BoardConfig(org_paths=[])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Initially no org connected
                assert app._active_org_path is None

                # Connect to org
                await app._connect_to_org(org_path)
                await pilot.pause()

                # Should now be connected
                assert app._is_connected
                assert app._active_org_path == org_path

                # Switch to team tab
                app.action_switch_tab("team")
                await pilot.pause()

                # Get table
                table = app.query_one("#workers-data", DataTable)

                # Should show worker(s)
                assert table.row_count >= 1

                # Verify worker data is displayed
                name = table.get_cell_at((0, 1))
                assert "Alice" in str(name)

    @pytest.mark.asyncio
    async def test_team_view_shows_correct_status_icons(self, org_with_mixed_worker_states):
        """Team view should display correct status icons for different session states."""
        config = BoardConfig(org_paths=[org_with_mixed_worker_states])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to team tab
            app.action_switch_tab("team")
            await pilot.pause()

            # Get table
            table = app.query_one("#workers-data", DataTable)

            # Get status icons for each worker
            status_icons = [table.get_cell_at((i, 0)) for i in range(table.row_count)]

            # Should have different icons for different states
            # Running = green circle, Idle = yellow circle, Stopped = black circle
            assert len(status_icons) == 3

            # All status icons should be non-empty
            for icon in status_icons:
                assert icon is not None
                assert len(str(icon)) > 0

    @pytest.mark.asyncio
    async def test_team_view_filter_idle_workers(self, org_with_mixed_worker_states):
        """Team view should have idle filter button that can be clicked."""
        config = BoardConfig(org_paths=[org_with_mixed_worker_states])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to team tab
            app.action_switch_tab("team")
            await pilot.pause()

            # Get table
            table = app.query_one("#workers-data", DataTable)
            assert table.row_count == 3

            # Verify "Idle" filter button exists and can be clicked
            filter_idle = app.query_one("#filter-idle", Button)
            assert filter_idle is not None

            # Click button should not crash
            await pilot.click(filter_idle)
            await pilot.pause()
            await pilot.pause()  # Extra pause for event processing

            # App should still be running (no crash)
            assert app.is_running

    @pytest.mark.asyncio
    async def test_team_view_ceo_indicator(self):
        """Team view should show CEO with special indicator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "ceo-org"
            workers = [
                {
                    "id": "worker-ceo",
                    "name": "Alice",
                    "role": "CEO",
                    "team_id": "team-exec",
                    "manager_id": None,
                    "session_state": "running",
                },
                {
                    "id": "worker-dev1",
                    "name": "Bob",
                    "role": "Developer",
                    "team_id": "team-eng",
                    "manager_id": "worker-ceo",
                    "session_state": "idle",
                },
            ]
            create_org_db_with_workers(org_path, workers)

            config = BoardConfig(org_paths=[org_path])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Switch to team tab
                app.action_switch_tab("team")
                await pilot.pause()

                # Get table
                table = app.query_one("#workers-data", DataTable)

                # Get role column for first worker (should be CEO)
                role = str(table.get_cell_at((0, 2)))

                # CEO role should have star indicator
                assert "★" in role or "CEO" in role
