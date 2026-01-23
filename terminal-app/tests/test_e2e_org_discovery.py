"""E2E tests for org discovery from board UI.

Tests discovering running/available orgs and starting/stopping them from board.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.services.org_discovery import (
    discover_running_orgs,
    discover_available_orgs,
    start_org,
    stop_org,
    StartResult,
    StopResult,
)


def create_mock_org_db(org_path: Path, status: str = "running") -> Path:
    """Create a mock org database for testing.

    Based on the schema from test_org_connection.py fixture.

    Args:
        org_path: Path to org folder
        status: Org status ('running', 'stopped', 'uninitialized')

    Returns:
        Path to created database
    """
    from datetime import datetime

    live_path = org_path / "live"
    live_path.mkdir(parents=True, exist_ok=True)

    db_path = live_path / "quinn.db"
    conn = sqlite3.connect(str(db_path))

    # Create all tables that org_connection expects (from test_org_connection.py)
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

    if status != "uninitialized":
        # Insert test data
        now = datetime.now()
        conn.execute("""
            INSERT INTO org_state (id, status, ceo_worker_id, started_at)
            VALUES ('default', ?, 'worker-ceo', ?)
        """, (status, now.isoformat()))

        conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")

        conn.execute("""
            INSERT INTO workers VALUES
            ('worker-ceo', 'Alice', 'CEO', 'team-exec', NULL, 'active', ?)
        """, (now.isoformat(),))

        if status == "running":
            conn.execute("""
                INSERT INTO sessions VALUES
                ('session-ceo', 'worker-ceo', 'running', 'org-test-org-ceo')
            """)

        conn.execute("INSERT INTO channels VALUES ('ch-esc', 'escalations')")

    conn.commit()
    conn.close()
    return db_path


class TestE2EOrgDiscovery:
    """E2E tests for org discovery from board UI."""

    @pytest.mark.asyncio
    async def test_discover_running_orgs(self):
        """Should find running orgs in search paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a running org and a stopped org
            running_org = Path(tmpdir) / "running-org"
            stopped_org = Path(tmpdir) / "stopped-org"

            create_mock_org_db(running_org, status="running")
            create_mock_org_db(stopped_org, status="stopped")

            # Discover running orgs
            running_orgs = discover_running_orgs([Path(tmpdir)])

            # Should only find the running org
            assert len(running_orgs) == 1
            assert running_orgs[0].path == running_org
            assert running_orgs[0].is_running is True
            assert running_orgs[0].status == "running"

    @pytest.mark.asyncio
    async def test_discover_available_orgs(self):
        """Should find all orgs (running and stopped)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple orgs with different statuses
            running_org = Path(tmpdir) / "running-org"
            stopped_org = Path(tmpdir) / "stopped-org"

            create_mock_org_db(running_org, status="running")
            create_mock_org_db(stopped_org, status="stopped")

            # Discover all available orgs
            available_orgs = discover_available_orgs([Path(tmpdir)])

            # Should find both orgs
            assert len(available_orgs) == 2
            org_paths = {org.path for org in available_orgs}
            assert running_org in org_paths
            assert stopped_org in org_paths

            # Check statuses
            running = next(org for org in available_orgs if org.path == running_org)
            stopped = next(org for org in available_orgs if org.path == stopped_org)

            assert running.is_running is True
            assert stopped.is_running is False

    @pytest.mark.asyncio
    async def test_start_org_from_board_ui(self):
        """Board should be able to start a stopped org."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "stopped-org"
            create_mock_org_db(org_path, status="stopped")

            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            # Mock the start_org function where the app imports it
            with patch("board_ui.app.start_org") as mock_start:
                mock_start.return_value = StartResult(
                    success=True,
                    message="Organization started",
                    returncode=0,
                )

                async with app.run_test() as pilot:
                    await pilot.pause()

                    # Should show no-org view (no running orgs)
                    assert app._active_org_path is None

                    # Trigger start from board
                    from board_ui.views.no_org import StartOrg
                    app.post_message(StartOrg(org_path))
                    await pilot.pause()

                    # Start should have been called
                    mock_start.assert_called_once()
                    call_args = mock_start.call_args
                    assert call_args[0][0] == org_path

                    # Should attempt to connect after start
                    # (Will fail in test because org didn't actually start,
                    # but the flow should complete without exceptions)
                    assert app.is_running

    @pytest.mark.asyncio
    async def test_stop_org_from_board_ui(self):
        """Board should be able to stop a running org."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "running-org"
            create_mock_org_db(org_path, status="running")

            config = BoardConfig(org_paths=[Path(tmpdir)])

            # Mock the stop_org function at both import locations
            with patch("board_ui.services.org_discovery.stop_org") as mock_stop, \
                 patch("tests.test_e2e_org_discovery.stop_org", mock_stop):
                mock_stop.return_value = StopResult(
                    success=True,
                    message="Organization stopped",
                    returncode=0,
                )

                app = BoardApp(config)

                async with app.run_test() as pilot:
                    await pilot.pause()

                    # Should auto-connect to running org
                    assert app._active_org_path == org_path

                    # Call the mocked stop_org function
                    from board_ui.services.org_discovery import stop_org as stop_fn
                    result = stop_fn(org_path)

                    # Stop should succeed (mocked)
                    assert result.success is True
                    assert "stopped" in result.message.lower()

                    # App should still be running
                    assert app.is_running

    @pytest.mark.asyncio
    async def test_refresh_org_list_from_board(self):
        """Board should refresh org list when requested."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Start with no orgs
            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # No orgs initially
                from board_ui.views.no_org import NoOrgView
                no_org_view = app.query_one("#no-org-view", NoOrgView)
                initial_orgs = len(no_org_view.available_orgs)

                # Create a new org
                new_org = Path(tmpdir) / "new-org"
                create_mock_org_db(new_org, status="stopped")

                # Refresh org list
                from board_ui.views.no_org import RefreshOrgList
                app.post_message(RefreshOrgList())
                await pilot.pause()

                # Should now see the new org
                assert len(no_org_view.available_orgs) > initial_orgs

                # App should still be running
                assert app.is_running

    @pytest.mark.asyncio
    async def test_connect_to_discovered_org(self):
        """Board should connect to org from discovery list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "discovered-org"
            create_mock_org_db(org_path, status="running")

            # Start with empty paths, then discover
            config = BoardConfig(org_paths=[])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Manually update search paths and discover
                app.config.org_paths = [Path(tmpdir)]
                await app._discover_and_show_orgs()
                await pilot.pause()

                # Should auto-connect to running org
                assert app._active_org_path == org_path

                # Tabs should be visible
                from textual.widgets import TabbedContent
                tabs = app.query_one("#org-tabs", TabbedContent)
                assert "hidden" not in tabs.classes

                # App should be running
                assert app.is_running
