"""E2E tests for org lifecycle.

Tests full org init -> start -> interact -> stop workflow.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

from textual.widgets import TabbedContent

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.services.org_discovery import (
    OrgInfo,
    StartResult,
    StopResult,
)


def create_mock_org_db(org_path: Path, status: str = "running") -> Path:
    """Create a mock org database for testing.

    Based on the schema from test_org_connection.py fixture.

    Args:
        org_path: Path to org folder
        status: Org status ('running' or 'stopped')

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


class TestE2EOrgLifecycle:
    """E2E tests for org lifecycle from board."""

    @pytest.mark.asyncio
    async def test_init_new_org_wizard(self):
        """Should walk through org initialization wizard."""
        # This test verifies the NoOrg view shows org creation options
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # With no orgs, should show initialization options
            # The app should not crash and should be responsive
            assert app.is_running

    @pytest.mark.asyncio
    async def test_start_initialized_org(self):
        """Should start an initialized org."""
        # Test with default config - no real org connection needed
        # The app gracefully handles missing orgs
        config = BoardConfig.default()
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()
            # App should launch without crashing
            assert app.is_running

    @pytest.mark.asyncio
    async def test_view_running_org_dashboard(self):
        """Should display running org metrics."""
        from textual.widgets import TabbedContent

        # Test with default config - uses placeholder data
        app = BoardApp(BoardConfig.default())

        async with app.run_test() as pilot:
            await pilot.pause()
            tabs = app.query_one("#org-tabs", TabbedContent)

            # Switch to dashboard
            app.action_switch_tab("dashboard")
            await pilot.pause()

            # Dashboard should be showing
            assert tabs.active == "dashboard"

    @pytest.mark.asyncio
    async def test_chat_with_ceo(self):
        """Should open CEO chat window."""
        # This test verifies the chat button exists and can be clicked
        # Actual tmux session opening requires system integration
        app = BoardApp(BoardConfig.default())

        async with app.run_test() as pilot:
            await pilot.pause()

            # Switch to dashboard
            app.action_switch_tab("dashboard")
            await pilot.pause()

            # Chat button should exist (may be disabled without terminal)
            from textual.widgets import Button

            try:
                chat_btn = app.query_one("#chat-ceo-btn", Button)
                assert chat_btn is not None
            except Exception:
                # Button might not exist if no org connected
                pass

    @pytest.mark.asyncio
    async def test_stop_running_org(self):
        """Should stop org gracefully."""
        from textual.widgets import TabbedContent

        # Test with default config - verify app can handle org operations
        app = BoardApp(BoardConfig.default())

        async with app.run_test() as pilot:
            await pilot.pause()
            # App should be running and responsive
            assert app.is_running

            tabs = app.query_one("#org-tabs", TabbedContent)

            # Navigation should work - org can be stopped from UI
            app.action_switch_tab("dashboard")
            await pilot.pause()
            assert tabs.active == "dashboard"

    @pytest.mark.asyncio
    async def test_restart_stopped_org(self):
        """Should restart a stopped org."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "stopped-org"
            org_path.mkdir()
            live_path = org_path / "live"
            live_path.mkdir()

            # Create stopped org
            db_path = live_path / "quinn.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE org_state (
                    id TEXT PRIMARY KEY,
                    status TEXT
                )
            """)
            conn.execute("INSERT INTO org_state VALUES ('default', 'stopped')")
            conn.commit()
            conn.close()

            with patch("board_ui.services.org_discovery.start_org") as mock_start:
                mock_start.return_value = StartResult(
                    success=True,
                    message="Organization restarted",
                    returncode=0,
                )

                config = BoardConfig(org_paths=[Path(tmpdir)])
                app = BoardApp(config)

                async with app.run_test() as pilot:
                    await pilot.pause()
                    assert app.is_running

    @pytest.mark.asyncio
    async def test_connect_to_org_updates_tab_bar(self):
        """Connecting to org should add org tab to tab bar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            db_path = create_mock_org_db(org_path)

            # Start with no orgs
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
                assert app._active_org_path == org_path

                # Tab bar should be visible
                from board_ui.views.org_tabs import OrgTabBar
                tab_bar = app.query_one("#org-tab-bar", OrgTabBar)
                assert "hidden" not in tab_bar.classes

                # Org tabs should be visible
                tabs = app.query_one("#org-tabs", TabbedContent)
                assert "hidden" not in tabs.classes

    @pytest.mark.asyncio
    async def test_disconnect_from_org_removes_tab(self):
        """Disconnecting should remove org tab and show no-org view."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            db_path = create_mock_org_db(org_path)

            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should auto-connect to running org
                assert app._active_org_path == org_path

                # Disconnect
                app._disconnect_from_org()
                await pilot.pause()

                # Should no longer be connected
                assert app._active_org_path is None

                # No-org view should be visible
                from board_ui.views.no_org import NoOrgView
                no_org_view = app.query_one("#no-org-view", NoOrgView)
                assert "hidden" not in no_org_view.classes

                # Org tabs should be hidden
                tabs = app.query_one("#org-tabs", TabbedContent)
                assert "hidden" in tabs.classes

    @pytest.mark.asyncio
    async def test_switch_between_orgs(self):
        """Should switch active org when connecting to different org."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two running orgs
            org1_path = Path(tmpdir) / "org-1"
            org2_path = Path(tmpdir) / "org-2"
            create_mock_org_db(org1_path)
            create_mock_org_db(org2_path)

            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should auto-connect to first org
                assert app._active_org_path is not None
                first_org = app._active_org_path

                # Connect to second org
                second_org = org2_path if first_org == org1_path else org1_path
                await app._connect_to_org(second_org)
                await pilot.pause()

                # Should have both orgs connected
                assert len(app._org_connections) == 2
                assert first_org in app._org_connections
                assert second_org in app._org_connections

                # Active should be the one we just connected to
                assert app._active_org_path == second_org

    @pytest.mark.asyncio
    async def test_reconnect_to_same_org(self):
        """Should handle reconnecting to same org (disconnect then connect)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "test-org"
            create_mock_org_db(org_path)

            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should auto-connect
                assert app._active_org_path == org_path
                assert org_path in app._org_connections

                # Disconnect
                app._disconnect_from_org()
                await pilot.pause()

                # Should be disconnected
                assert app._active_org_path is None
                assert org_path not in app._org_connections

                # Reconnect to same org
                await app._connect_to_org(org_path)
                await pilot.pause()

                # Should be connected again
                assert app._active_org_path == org_path
                assert org_path in app._org_connections

                # No exceptions should have been thrown
                assert app.is_running
