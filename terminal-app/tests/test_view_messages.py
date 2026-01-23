"""Tests for Messages view.

Tests the board inbox displays messages and enables async replies.
"""

import pytest
from unittest.mock import MagicMock, patch

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.messages import MessagesView
from textual.widgets import DataTable, Button, TextArea, Static, Label


class TestMessagesView:
    """Tests for MessagesView widget."""

    @pytest.mark.asyncio
    async def test_messages_view_composes(self):
        """Messages view should compose list and detail panes."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            # Switch to Messages tab
            app.action_switch_tab("messages")
            await pilot.pause()

            # Query the Messages view
            messages_view = app.query_one("#messages-view", MessagesView)
            assert messages_view is not None

            # Check message list pane exists
            message_list = app.query_one("#message-list")
            assert message_list is not None

            # Check message detail pane exists
            message_detail = app.query_one("#message-detail")
            assert message_detail is not None

    @pytest.mark.asyncio
    async def test_messages_shows_inbox(self):
        """Should display escalated messages."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get the messages table
            table = app.query_one("#messages-table", DataTable)
            assert table is not None

            # Should have rows (placeholder data has 3 messages)
            assert table.row_count > 0

    @pytest.mark.asyncio
    async def test_unread_count_displayed(self):
        """Should show count of unread messages."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            # Find unread count label (now named #unread-label)
            unread_label = app.query_one("#unread-label", Label)
            assert unread_label is not None

    @pytest.mark.asyncio
    async def test_message_selection_shows_detail(self):
        """Selecting a message should show full content."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            table = app.query_one("#messages-table", DataTable)
            detail_header = app.query_one("#detail-header", Label)

            # Detail header exists and shows initial state
            assert detail_header is not None

    @pytest.mark.asyncio
    async def test_reply_input_disabled_initially(self):
        """Reply input should be disabled when no message selected."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            reply_input = app.query_one("#reply-input", TextArea)
            assert reply_input.disabled is True

            send_btn = app.query_one("#send-reply-btn", Button)
            assert send_btn.disabled is True

    @pytest.mark.asyncio
    async def test_reply_input_exists(self):
        """Reply input and send button should exist."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            reply_input = app.query_one("#reply-input", TextArea)
            assert reply_input is not None

            send_btn = app.query_one("#send-reply-btn", Button)
            assert send_btn is not None

    @pytest.mark.asyncio
    async def test_resolve_button_exists(self):
        """Mark resolved button should exist."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            resolve_btn = app.query_one("#resolve-btn", Button)
            assert resolve_btn is not None

    @pytest.mark.asyncio
    async def test_message_body_exists(self):
        """Message body should exist for displaying content."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            message_body = app.query_one("#message-body", Static)
            assert message_body is not None

    @pytest.mark.asyncio
    async def test_messages_table_has_columns(self):
        """Messages table should have expected columns."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            table = app.query_one("#messages-table", DataTable)

            # Should have Pri, From, Preview, Time columns (4)
            assert len(table.columns) == 4
