"""Tests for Logs view.

Tests the logs view renders correctly and handles log viewing features.
Uses mocked LogReader for isolation.

Following TDD: Write FAILING tests, then implement to make them PASS.
"""

import pytest
from datetime import datetime, date
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
from textual.app import App

from board_ui.config import BoardConfig


# Import will FAIL until we implement the view
try:
    from board_ui.views.logs import LogsView
except ImportError:
    LogsView = None


class _TestApp(App):
    """Helper app for testing LogsView in isolation."""
    def compose(self):
        yield LogsView(id="logs-view")


@pytest.mark.skipif(LogsView is None, reason="LogsView not implemented yet")
class TestLogsView:
    """Tests for LogsView widget."""

    @pytest.mark.asyncio
    async def test_logs_view_composes(self):
        """Logs view should compose its child widgets."""
        app = _TestApp()
        async with app.run_test() as pilot:
            # Query the logs view
            logs_view = app.query_one("#logs-view", LogsView)
            assert logs_view is not None

            # Check filter controls exist
            component_filter = app.query_one("#log-component-filter")
            assert component_filter is not None

            level_filter = app.query_one("#log-level-filter")
            assert level_filter is not None

    @pytest.mark.asyncio
    async def test_log_list_container_exists(self):
        """Should have a container for displaying logs."""
        app = _TestApp()
        async with app.run_test() as pilot:
            # Check log list container exists
            log_list = app.query_one("#log-entries-container")
            assert log_list is not None

    @pytest.mark.asyncio
    async def test_search_input_exists(self):
        """Should have a search input box."""
        app = _TestApp()
        async with app.run_test() as pilot:
            # Check search input exists
            search_input = app.query_one("#log-search-input")
            assert search_input is not None

    @pytest.mark.asyncio
    async def test_auto_refresh_toggle_exists(self):
        """Should have an auto-refresh toggle."""
        app = _TestApp()
        async with app.run_test() as pilot:
            # Check auto-refresh toggle exists
            auto_refresh = app.query_one("#auto-refresh-toggle")
            assert auto_refresh is not None

    @pytest.mark.asyncio
    async def test_log_entries_display_with_formatting(self):
        """Log entries should display with proper formatting."""
        app = _TestApp()

        # Mock LogReader to return sample logs
        sample_logs = [
            {
                "timestamp": "2026-01-28T10:15:23Z",
                "level": "INFO",
                "component": "worker",
                "subcomponent": "lifecycle",
                "message": "Worker wrkr-abc started",
                "context": {"worker_id": "wrkr-abc"}
            },
            {
                "timestamp": "2026-01-28T10:15:24Z",
                "level": "DEBUG",
                "component": "session",
                "message": "Spawning claude-code session",
                "context": {}
            }
        ]

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            # Mock the log reader
            with patch.object(logs_view, "_log_reader") as mock_reader:
                mock_reader.tail_logs.return_value = sample_logs

                # Refresh logs
                await logs_view.refresh_logs()

                # Verify log entries are displayed
                # Check that log container has children
                log_container = app.query_one("#log-entries-container")
                assert len(log_container.children) == 2

    @pytest.mark.asyncio
    async def test_component_filter_works(self):
        """Filtering by component should work."""
        app = _TestApp()

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            # Mock log reader
            with patch.object(logs_view, "_log_reader") as mock_reader:
                mock_reader.read_logs.return_value = []

                # Change component filter
                component_filter = app.query_one("#log-component-filter")
                # Simulate selecting "worker" component
                component_filter.value = "worker"

                # Trigger filter change
                await logs_view._apply_filters()

                # Verify read_logs was called with component filter
                mock_reader.read_logs.assert_called()
                call_args = mock_reader.read_logs.call_args
                assert call_args.kwargs.get("component") == "worker"

    @pytest.mark.asyncio
    async def test_level_filter_works(self):
        """Filtering by log level should work."""
        app = _TestApp()

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            # Mock log reader
            with patch.object(logs_view, "_log_reader") as mock_reader:
                mock_reader.read_logs.return_value = []

                # Change level filter
                level_filter = app.query_one("#log-level-filter")
                level_filter.value = "ERROR"

                # Trigger filter change
                await logs_view._apply_filters()

                # Verify read_logs was called with level filter
                mock_reader.read_logs.assert_called()
                call_args = mock_reader.read_logs.call_args
                assert call_args.kwargs.get("level") == "ERROR"

    @pytest.mark.asyncio
    async def test_search_filters_logs(self):
        """Search input should filter logs by keyword."""
        app = _TestApp()

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            # Mock log reader
            with patch.object(logs_view, "_log_reader") as mock_reader:
                mock_reader.search_logs.return_value = []

                # Enter search query
                search_input = app.query_one("#log-search-input")
                search_input.value = "lifecycle"

                # Trigger search
                await logs_view._perform_search()

                # Verify search_logs was called with query
                mock_reader.search_logs.assert_called()
                call_args = mock_reader.search_logs.call_args
                assert call_args.kwargs.get("query") == "lifecycle"

    @pytest.mark.asyncio
    async def test_pagination_controls_exist(self):
        """Should have pagination controls."""
        app = _TestApp()

        async with app.run_test() as pilot:
            # Check pagination buttons exist
            prev_btn = app.query_one("#log-prev-page")
            assert prev_btn is not None

            next_btn = app.query_one("#log-next-page")
            assert next_btn is not None

            page_label = app.query_one("#log-page-label")
            assert page_label is not None

    @pytest.mark.asyncio
    async def test_pagination_navigates_pages(self):
        """Pagination buttons should navigate between pages."""
        app = _TestApp()

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            # Mock log reader with many logs
            many_logs = [
                {
                    "timestamp": f"2026-01-28T10:15:{i:02d}Z",
                    "level": "INFO",
                    "component": "test",
                    "message": f"Log entry {i}",
                    "context": {}
                }
                for i in range(150)  # More than one page
            ]

            with patch.object(logs_view, "_log_reader") as mock_reader:
                mock_reader.read_logs.return_value = many_logs

                # Initial page
                assert logs_view._current_page == 1

                # Click next page
                next_btn = app.query_one("#log-next-page")
                await pilot.click(next_btn)

                # Page should increment
                assert logs_view._current_page == 2

                # Click previous page
                prev_btn = app.query_one("#log-prev-page")
                await pilot.click(prev_btn)

                # Page should decrement
                assert logs_view._current_page == 1

    @pytest.mark.asyncio
    async def test_auto_refresh_toggles(self):
        """Auto-refresh toggle should enable/disable automatic refresh."""
        app = _TestApp()

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            # Initial state
            assert logs_view._auto_refresh is True

            # Toggle off
            toggle = app.query_one("#auto-refresh-toggle")
            await pilot.click(toggle)

            # Should be disabled
            assert logs_view._auto_refresh is False

            # Toggle on
            await pilot.click(toggle)

            # Should be enabled
            assert logs_view._auto_refresh is True

    @pytest.mark.asyncio
    async def test_log_entry_syntax_highlighting(self):
        """Log entries should have syntax highlighting by level."""
        app = _TestApp()

        sample_logs = [
            {"timestamp": "2026-01-28T10:15:23Z", "level": "INFO", "component": "test", "message": "Info message", "context": {}},
            {"timestamp": "2026-01-28T10:15:24Z", "level": "ERROR", "component": "test", "message": "Error message", "context": {}},
            {"timestamp": "2026-01-28T10:15:25Z", "level": "DEBUG", "component": "test", "message": "Debug message", "context": {}},
        ]

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            with patch.object(logs_view, "_log_reader") as mock_reader:
                mock_reader.tail_logs.return_value = sample_logs

                await logs_view.refresh_logs()

                # Verify log entries have appropriate CSS classes
                log_entries = app.query(".log-entry")
                assert len(log_entries) == 3

                # Check for level-specific classes
                info_entry = log_entries[0]
                assert "level-info" in info_entry.classes or "INFO" in str(info_entry)

                error_entry = log_entries[1]
                assert "level-error" in error_entry.classes or "ERROR" in str(error_entry)

    @pytest.mark.asyncio
    async def test_empty_logs_shows_message(self):
        """Should show a message when no logs are available."""
        app = _TestApp()

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            with patch.object(logs_view, "_log_reader") as mock_reader:
                mock_reader.tail_logs.return_value = []

                await logs_view.refresh_logs()

                # Should show empty state message
                empty_message = app.query_one("#log-empty-message")
                assert empty_message is not None
                assert "No logs" in str(empty_message.renderable)

    @pytest.mark.asyncio
    async def test_refresh_logs_method_exists(self):
        """Should have a refresh_logs method for polling."""
        app = _TestApp()

        async with app.run_test() as pilot:
            logs_view = app.query_one("#logs-view", LogsView)

            # Method should exist
            assert hasattr(logs_view, "refresh_logs")
            assert callable(logs_view.refresh_logs)

            # Should not raise exception when called
            with patch.object(logs_view, "_log_reader") as mock_reader:
                mock_reader.tail_logs.return_value = []
                await logs_view.refresh_logs()
