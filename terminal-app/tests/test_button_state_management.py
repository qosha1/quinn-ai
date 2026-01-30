"""Test button state management for org lifecycle controls."""
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from textual.widgets import Button

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.dashboard import DashboardView
from board_ui.interfaces.org_connection import OrgStatus, OrgInfo


@pytest.mark.asyncio
async def test_button_states_running_org():
    """Test button states when org is running."""
    config = BoardConfig(org_paths=[])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Get dashboard view
        dashboard = app.query_one(DashboardView)

        # Mock org info as running
        dashboard._org_info = OrgInfo(
            path=Path("/tmp/test-org"),
            name="test-org",
            status=OrgStatus.RUNNING,
            ceo_worker_id="ceo-123",
            worker_count=1,
            active_session_count=1,
            started_at=datetime.now(),
            stopped_at=None,
        )

        # Update button states
        dashboard._update_org_action_buttons()
        await pilot.pause()

        # Check button states
        start_btn = dashboard.query_one("#start-org-btn", Button)
        stop_btn = dashboard.query_one("#stop-org-btn", Button)
        restart_btn = dashboard.query_one("#restart-org-btn", Button)

        assert start_btn.disabled is True, "Start button should be disabled when org is running"
        assert stop_btn.disabled is False, "Stop button should be enabled when org is running"
        assert restart_btn.disabled is False, "Restart button should be enabled when org is running"


@pytest.mark.asyncio
async def test_button_states_stopped_org():
    """Test button states when org is stopped."""
    config = BoardConfig(org_paths=[])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Get dashboard view
        dashboard = app.query_one(DashboardView)

        # Mock org info as stopped
        dashboard._org_info = OrgInfo(
            path=Path("/tmp/test-org"),
            name="test-org",
            status=OrgStatus.STOPPED,
            ceo_worker_id="ceo-123",
            worker_count=1,
            active_session_count=0,
            started_at=None,
            stopped_at=datetime.now(),
        )

        # Update button states
        dashboard._update_org_action_buttons()
        await pilot.pause()

        # Check button states
        start_btn = dashboard.query_one("#start-org-btn", Button)
        stop_btn = dashboard.query_one("#stop-org-btn", Button)
        restart_btn = dashboard.query_one("#restart-org-btn", Button)

        assert start_btn.disabled is False, "Start button should be enabled when org is stopped"
        assert stop_btn.disabled is True, "Stop button should be disabled when org is stopped"
        assert restart_btn.disabled is True, "Restart button should be disabled when org is stopped"


@pytest.mark.asyncio
async def test_button_states_initialized_org():
    """Test button states when org is initialized but not started."""
    config = BoardConfig(org_paths=[])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Get dashboard view
        dashboard = app.query_one(DashboardView)

        # Mock org info as initialized
        dashboard._org_info = OrgInfo(
            path=Path("/tmp/test-org"),
            name="test-org",
            status=OrgStatus.INITIALIZED,
            ceo_worker_id="ceo-123",
            worker_count=1,
            active_session_count=0,
            started_at=None,
            stopped_at=None,
        )

        # Update button states
        dashboard._update_org_action_buttons()
        await pilot.pause()

        # Check button states
        start_btn = dashboard.query_one("#start-org-btn", Button)
        stop_btn = dashboard.query_one("#stop-org-btn", Button)
        restart_btn = dashboard.query_one("#restart-org-btn", Button)

        assert start_btn.disabled is False, "Start button should be enabled when org is initialized"
        assert stop_btn.disabled is True, "Stop button should be disabled when org is initialized"
        assert restart_btn.disabled is True, "Restart button should be disabled when org is initialized"


@pytest.mark.asyncio
async def test_button_states_uninitialized_org():
    """Test button states when org is uninitialized."""
    config = BoardConfig(org_paths=[])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Get dashboard view
        dashboard = app.query_one(DashboardView)

        # Mock org info as uninitialized
        dashboard._org_info = OrgInfo(
            path=Path("/tmp/test-org"),
            name="test-org",
            status=OrgStatus.UNINITIALIZED,
            ceo_worker_id=None,
            worker_count=0,
            active_session_count=0,
            started_at=None,
            stopped_at=None,
        )

        # Update button states
        dashboard._update_org_action_buttons()
        await pilot.pause()

        # Check button states
        start_btn = dashboard.query_one("#start-org-btn", Button)
        stop_btn = dashboard.query_one("#stop-org-btn", Button)
        restart_btn = dashboard.query_one("#restart-org-btn", Button)

        assert start_btn.disabled is True, "Start button should be disabled when org is uninitialized"
        assert stop_btn.disabled is True, "Stop button should be disabled when org is uninitialized"
        assert restart_btn.disabled is True, "Restart button should be disabled when org is uninitialized"


@pytest.mark.asyncio
async def test_button_states_update_on_status_change():
    """Test that button states update when org status changes."""
    config = BoardConfig(org_paths=[])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Get dashboard view
        dashboard = app.query_one(DashboardView)

        # Start with stopped org
        dashboard._org_info = OrgInfo(
            path=Path("/tmp/test-org"),
            name="test-org",
            status=OrgStatus.STOPPED,
            ceo_worker_id="ceo-123",
            worker_count=1,
            active_session_count=0,
            started_at=None,
            stopped_at=datetime.now(),
        )
        dashboard._update_org_action_buttons()
        await pilot.pause()

        start_btn = dashboard.query_one("#start-org-btn", Button)
        stop_btn = dashboard.query_one("#stop-org-btn", Button)
        restart_btn = dashboard.query_one("#restart-org-btn", Button)

        # Verify stopped state
        assert start_btn.disabled is False
        assert stop_btn.disabled is True
        assert restart_btn.disabled is True

        # Change to running
        dashboard._org_info = OrgInfo(
            path=Path("/tmp/test-org"),
            name="test-org",
            status=OrgStatus.RUNNING,
            ceo_worker_id="ceo-123",
            worker_count=1,
            active_session_count=1,
            started_at=datetime.now(),
            stopped_at=None,
        )
        dashboard._update_org_action_buttons()
        await pilot.pause()

        # Verify running state
        assert start_btn.disabled is True
        assert stop_btn.disabled is False
        assert restart_btn.disabled is False
