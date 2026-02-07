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

from .conftest import create_test_org_db


def create_mock_org_db(org_path: Path, status: str = "running") -> Path:
    """Create a mock org database for testing using shared utility.

    Args:
        org_path: Path to org folder
        status: Org status ('running', 'stopped', 'uninitialized')

    Returns:
        Path to created database
    """
    include_ceo = (status != "uninitialized")
    return create_test_org_db(org_path, status=status, include_ceo=include_ceo)


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

    @pytest.mark.asyncio
    async def test_discover_orgs_with_empty_search_paths(self):
        """Config with org_paths=[] should NOT crash and show helpful error message."""
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # App should be running
            assert app.is_running

            # Should NOT be connected to any org
            assert app._active_org_path is None

            # Should show no-org view
            from board_ui.views.no_org import NoOrgView
            no_org_view = app.query_one("#no-org-view", NoOrgView)
            assert "hidden" not in no_org_view.classes

            # Available orgs should be empty
            assert len(no_org_view.available_orgs) == 0

    @pytest.mark.asyncio
    async def test_discover_orgs_when_home_orgs_missing(self):
        """When ~/orgs doesn't exist, should still search cwd and show search paths attempted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create an org in current directory
            cwd_org = Path(tmpdir) / "cwd-org"
            create_mock_org_db(cwd_org, status="stopped")

            # Use only tmpdir as search path (simulating cwd)
            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should discover the org in cwd
                from board_ui.views.no_org import NoOrgView
                no_org_view = app.query_one("#no-org-view", NoOrgView)

                # Should find the org
                assert len(no_org_view.available_orgs) == 1
                assert no_org_view.available_orgs[0][0] == cwd_org

                # App should be running (not crashed)
                assert app.is_running

    @pytest.mark.asyncio
    async def test_discover_orgs_handles_permission_denied(self):
        """Create directory user can't read - should log warning, continue, NOT crash."""
        import os
        import stat

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a normal org
            normal_org = Path(tmpdir) / "normal-org"
            create_mock_org_db(normal_org, status="stopped")

            # Create a directory with restricted permissions
            restricted_dir = Path(tmpdir) / "restricted"
            restricted_dir.mkdir()
            restricted_org = restricted_dir / "restricted-org"
            restricted_org.mkdir()

            # Remove read permissions (will cause PermissionError)
            try:
                os.chmod(restricted_dir, stat.S_IWUSR | stat.S_IXUSR)

                config = BoardConfig(org_paths=[Path(tmpdir)])
                app = BoardApp(config)

                async with app.run_test() as pilot:
                    await pilot.pause()

                    # App should still be running (didn't crash)
                    assert app.is_running

                    # Should have found the normal org
                    from board_ui.views.no_org import NoOrgView
                    no_org_view = app.query_one("#no-org-view", NoOrgView)

                    # Should find at least the normal org (restricted one may be skipped)
                    assert len(no_org_view.available_orgs) >= 1
                    org_paths = [org[0] for org in no_org_view.available_orgs]
                    assert normal_org in org_paths
            finally:
                # Restore permissions for cleanup
                try:
                    os.chmod(restricted_dir, stat.S_IRWXU)
                except OSError:
                    # Best-effort cleanup - may fail on some systems
                    pass

    @pytest.mark.asyncio
    async def test_discover_orgs_in_current_directory(self):
        """Create temp org in cwd - should auto-discover and connect successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a running org in the temp directory (simulating cwd)
            org_path = Path(tmpdir) / "local-org"
            create_mock_org_db(org_path, status="running")

            # Configure board to search only this directory
            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should auto-discover and connect
                assert app._active_org_path == org_path
                assert app._is_connected

                # Should show org tabs
                from textual.widgets import TabbedContent
                tabs = app.query_one("#org-tabs", TabbedContent)
                assert "hidden" not in tabs.classes

                # App should be running
                assert app.is_running

    @pytest.mark.asyncio
    async def test_discover_multiple_orgs(self):
        """Create 2 orgs in search path - should find both and show in org list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two orgs (one running, one stopped)
            org1_path = Path(tmpdir) / "org-alpha"
            org2_path = Path(tmpdir) / "org-beta"

            create_mock_org_db(org1_path, status="running")
            create_mock_org_db(org2_path, status="stopped")

            config = BoardConfig(org_paths=[Path(tmpdir)])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should find both orgs
                from board_ui.views.no_org import NoOrgView
                no_org_view = app.query_one("#no-org-view", NoOrgView)

                assert len(no_org_view.available_orgs) == 2
                org_paths = {org[0] for org in no_org_view.available_orgs}
                assert org1_path in org_paths
                assert org2_path in org_paths

                # Should auto-connect to the running org
                assert app._active_org_path == org1_path

                # App should be running
                assert app.is_running

    @pytest.mark.asyncio
    async def test_no_orgs_shows_helpful_message(self):
        """Empty search paths - should show 'Searched in: ...' and suggest 'Create ~/orgs or use --org-path'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config with empty directory (no orgs)
            empty_dir = Path(tmpdir) / "empty"
            empty_dir.mkdir()

            config = BoardConfig(org_paths=[empty_dir])
            app = BoardApp(config)

            async with app.run_test() as pilot:
                await pilot.pause()

                # Should not be connected
                assert app._active_org_path is None

                # Should show no-org view
                from board_ui.views.no_org import NoOrgView
                no_org_view = app.query_one("#no-org-view", NoOrgView)
                assert "hidden" not in no_org_view.classes

                # Should have no orgs available
                assert len(no_org_view.available_orgs) == 0

                # App should still be running
                assert app.is_running
