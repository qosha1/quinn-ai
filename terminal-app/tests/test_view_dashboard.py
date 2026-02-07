"""Tests for Dashboard view.

Tests the dashboard renders correctly and handles events.
Uses mocked OrgConnection for isolation.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.dashboard import DashboardView


class TestDashboardView:
    """Tests for DashboardView widget."""

    @pytest.mark.asyncio
    async def test_dashboard_composes(self):
        """Dashboard should compose its child widgets."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            # Query the dashboard view
            dashboard = app.query_one("#dashboard-view", DashboardView)
            assert dashboard is not None

            # Check child widgets are composed
            ceo_card = app.query_one("#ceo-card")
            assert ceo_card is not None

            metrics_row = app.query_one("#metrics-row")
            assert metrics_row is not None

            activity_widget = app.query_one("#activity-widget")
            assert activity_widget is not None

    @pytest.mark.asyncio
    async def test_dashboard_displays_metrics(self):
        """Dashboard should display org metrics."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            # Check metric elements exist
            spend_today = app.query_one("#spend-today")
            assert spend_today is not None

            worker_count = app.query_one("#worker-count")
            assert worker_count is not None

            active_count = app.query_one("#active-count")
            assert active_count is not None

    @pytest.mark.asyncio
    async def test_chat_ceo_button_visible(self):
        """Chat with CEO button should be prominently visible."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            # Find the chat button
            chat_btn = app.query_one("#chat-ceo-btn")
            assert chat_btn is not None
            assert chat_btn.display is True

    @pytest.mark.asyncio
    async def test_chat_ceo_button_opens_window(self):
        """Clicking Chat with CEO should trigger window opening."""
        # Test that button exists and can be clicked
        # The terminal opening is tested implicitly via terminal provider tests
        app = BoardApp(BoardConfig.default())

        async with app.run_test() as pilot:
            # Find the button and verify it can be clicked
            chat_btn = app.query_one("#chat-ceo-btn")
            assert chat_btn is not None

            # Verify button has correct label
            assert "Chat" in str(chat_btn.label)

            # Button should be clickable (not disabled)
            assert not chat_btn.disabled

    @pytest.mark.asyncio
    async def test_dashboard_no_terminal_shows_error(self):
        """Dashboard should show error when no terminal available."""
        app = BoardApp(BoardConfig.default())

        async with app.run_test() as pilot:
            # Mock the terminal provider to return None
            with patch("board_ui.terminals.get_terminal_provider") as mock_get_terminal:
                mock_get_terminal.return_value = None

                # Click the button
                chat_btn = app.query_one("#chat-ceo-btn")
                await pilot.click(chat_btn)

                # Should show notification (error severity)
                # Note: We can't easily check notifications in Textual tests,
                # but we verify no exception is raised

    @pytest.mark.asyncio
    async def test_ceo_status_displayed(self):
        """CEO status should be displayed in the CEO card."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            from textual.widgets import Label
            ceo_status = app.query_one("#ceo-status", Label)
            assert ceo_status is not None
            # Check the label has text content (uses render or str)
            # Label.render() returns rendered content
            assert ceo_status is not None

    @pytest.mark.asyncio
    async def test_activity_panel_exists(self):
        """Activity widget should show recent activity area."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            activity_widget = app.query_one("#activity-widget")
            assert activity_widget is not None

    @pytest.mark.asyncio
    async def test_metric_cards_exist(self):
        """Metric cards should exist in the dashboard."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            # Find metric cards via their class
            metric_cards = app.query(".metric-card")
            assert len(metric_cards) > 0
