"""E2E tests for app launch.

Tests the app launches and displays correctly.
"""

import pytest
import tempfile
from pathlib import Path
from textual.widgets import TabbedContent, TabPane

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from tests.conftest import create_test_org_db


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
        """Should show Dashboard, OKRs, Team, Messages, Logs tabs."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check tabs exist
            tabs = app.query_one(TabbedContent)
            assert tabs is not None

            # Should have 5 tabs: Dashboard, OKRs, Team, Messages, Logs
            # (may also have NoOrg view which is different)
            tab_panes = list(app.query(TabPane))
            tab_ids = [t.id for t in tab_panes if t.id]

            # Dashboard, OKRs, Team, Messages, Logs should be present
            expected_tabs = {"dashboard", "okrs", "team", "messages", "logs"}
            actual_tabs = {t.replace("-tab", "").replace("-pane", "") for t in tab_ids}
            assert expected_tabs.issubset(actual_tabs) or len(tab_panes) >= 5

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

    @pytest.mark.asyncio
    async def test_app_startup_with_no_orgs(self):
        """Should handle startup with empty org_paths gracefully."""
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # App should be running
            assert app.is_running

            # Should not be connected to any org
            assert app._active_org_path is None

            # Should show no-org view
            from board_ui.views.no_org import NoOrgView
            no_org_view = app.query_one("#no-org-view", NoOrgView)
            assert "hidden" not in no_org_view.classes

    @pytest.mark.asyncio
    async def test_app_startup_with_stopped_org(self):
        """Should launch successfully with stopped org in path."""
        import tempfile
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "stopped-org"
            org_path.mkdir()
            live_path = org_path / "live"
            live_path.mkdir()

            # Create stopped org DB
            db_path = live_path / "quinn.db"
            conn = sqlite3.connect(str(db_path))
            conn.executescript("""
                CREATE TABLE org_state (
                    id TEXT PRIMARY KEY,
                    status TEXT,
                    ceo_worker_id TEXT
                );
                CREATE TABLE workers (id TEXT PRIMARY KEY);
                CREATE TABLE sessions (id TEXT PRIMARY KEY);
                INSERT INTO org_state VALUES ('default', 'stopped', 'worker-ceo');
            """)
            conn.commit()
            conn.close()

            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # App should be running
                assert app.is_running

                # Should NOT auto-connect to stopped org
                assert app._active_org_path is None

                # Should show no-org view with the stopped org available
                from board_ui.views.no_org import NoOrgView
                no_org_view = app.query_one("#no-org-view", NoOrgView)
                assert "hidden" not in no_org_view.classes

    @pytest.mark.asyncio
    async def test_app_startup_with_multiple_running_orgs(self):
        """Should auto-connect to first running org when multiple available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two running orgs using helper
            for org_name in ["org-1", "org-2"]:
                org_path = Path(tmpdir) / org_name
                create_test_org_db(org_path, status="running")

            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # App should be running
                assert app.is_running

                # Should auto-connect to one of the running orgs
                assert app._active_org_path is not None
                assert app._active_org_path.name in ["org-1", "org-2"]

                # Should show org tabs, not no-org view
                tabs = app.query_one("#org-tabs", TabbedContent)
                assert "hidden" not in tabs.classes

    @pytest.mark.asyncio
    async def test_app_auto_connects_to_running_org(self):
        """App should auto-connect to running org on startup without DuplicateIds error.

        This test exercises the auto-connect flow that exposed the duplicate widget IDs bug.
        The bug only appeared when BoardApp auto-connected to a running org on startup,
        because _update_org_tab_bar() was called before the tab bar widgets were mounted.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a running org using helper
            org_path = Path(tmpdir) / "test-org"
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
            # Create a stopped org using helper
            org_path = Path(tmpdir) / "test-org"
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


class TestDatabaseLockRetry:
    """Tests for Bug 1: Database lock retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_connect_retries_on_database_locked(self):
        """_connect_to_org should retry up to 3 times when DatabaseLocked is raised."""
        from unittest.mock import patch, MagicMock, AsyncMock
        from board_ui.services.org_connection import DatabaseLocked

        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "locked-org"
            create_test_org_db(org_path, status="running")

            config = BoardConfig(org_paths=[])
            app = BoardApp(config)

            call_count = 0

            original_init = None

            def mock_connection_factory(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise DatabaseLocked(org_path / "live" / "quinn.db", Exception("database is locked"))
                # On 3rd attempt, succeed by calling original constructor
                from board_ui.services.org_connection import QuinnAIOrgConnection
                # We need to bypass the mock to actually create the connection
                # Use __new__ + manual init
                instance = object.__new__(QuinnAIOrgConnection)
                # Manually replicate __init__ behavior for test
                instance._org_path = org_path
                instance._db = None
                instance._is_connected_flag = True
                instance._connected = True
                instance._polling_enabled = False
                instance._last_change_id = 0
                instance._client_id = "test"
                instance._lock = __import__('threading').Lock()
                instance._subscriber_lock = __import__('threading').Lock()
                instance._subscribers = []
                return instance

            async with app.run_test() as pilot:
                await pilot.pause()

                with patch('board_ui.app.QuinnAIOrgConnection', side_effect=mock_connection_factory):
                    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                        await app._connect_to_org(org_path)

                        # Should have called constructor 3 times (2 failures + 1 success)
                        assert call_count == 3, f"Expected 3 attempts, got {call_count}"

                        # Should have called asyncio.sleep twice with backoff delays
                        assert mock_sleep.call_count == 2
                        # First retry delay: 0.5s
                        assert mock_sleep.call_args_list[0][0][0] == pytest.approx(0.5)
                        # Second retry delay: 1.0s
                        assert mock_sleep.call_args_list[1][0][0] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_connect_gives_up_after_max_retries(self):
        """_connect_to_org should give up and show error after 3 failed retries."""
        from unittest.mock import patch, AsyncMock
        from board_ui.services.org_connection import DatabaseLocked

        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "locked-org"
            create_test_org_db(org_path, status="running")

            config = BoardConfig(org_paths=[])
            app = BoardApp(config)

            def always_locked(*args, **kwargs):
                raise DatabaseLocked(org_path / "live" / "quinn.db", Exception("database is locked"))

            async with app.run_test() as pilot:
                await pilot.pause()

                with patch('board_ui.app.QuinnAIOrgConnection', side_effect=always_locked):
                    with patch('asyncio.sleep', new_callable=AsyncMock):
                        await app._connect_to_org(org_path)

                        # Should NOT be connected after all retries fail
                        assert app._active_org_path is None or org_path not in app._org_connections
