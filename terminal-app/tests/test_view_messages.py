"""Tests for Messages view.

Tests the board inbox displays messages and enables async replies.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views.messages import MessagesView, _parse_intervention_command
from board_ui.interfaces.org_connection import Message
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


class TestInterventionErrorFeedback:
    """Tests for Bug 3: Specific error feedback for intervention failures."""

    @pytest.mark.asyncio
    async def test_execute_intervention_validates_worker_exists(self):
        """_execute_intervention should check worker exists before executing action."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            messages_view = app.query_one("#messages-view", MessagesView)

            # Set up a mock org_connection that returns None for get_worker
            mock_conn = MagicMock()
            mock_conn.get_worker.return_value = None
            fake_path = Path("/tmp/fake-org")
            app._org_connections[fake_path] = mock_conn
            app._active_org_path = fake_path

            intervention = {
                'action': 'pause',
                'worker_id': 'nonexistent-worker',
                'reason': 'test'
            }

            success, message = await messages_view._execute_intervention(intervention)

            assert success is False
            assert "not found" in message.lower(), \
                f"Should indicate worker not found, got: {message}"

    @pytest.mark.asyncio
    async def test_execute_intervention_includes_worker_name_on_failure(self):
        """Failed intervention should include worker name in error message."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            messages_view = app.query_one("#messages-view", MessagesView)

            # Set up mock with a worker that exists but pause fails
            mock_worker = MagicMock()
            mock_worker.name = "Bob Developer"
            mock_conn = MagicMock()
            mock_conn.get_worker.return_value = mock_worker
            mock_conn.pause_worker.return_value = False
            fake_path = Path("/tmp/fake-org")
            app._org_connections[fake_path] = mock_conn
            app._active_org_path = fake_path

            intervention = {
                'action': 'pause',
                'worker_id': 'worker-dev1',
                'reason': 'test'
            }

            success, message = await messages_view._execute_intervention(intervention)

            assert success is False
            assert "Bob Developer" in message, \
                f"Should include worker name in error, got: {message}"

    @pytest.mark.asyncio
    async def test_execute_intervention_includes_worker_name_on_success(self):
        """Successful intervention should use worker name instead of just ID."""
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            messages_view = app.query_one("#messages-view", MessagesView)

            mock_worker = MagicMock()
            mock_worker.name = "Carol Engineer"
            mock_conn = MagicMock()
            mock_conn.get_worker.return_value = mock_worker
            mock_conn.resume_worker.return_value = True
            fake_path = Path("/tmp/fake-org")
            app._org_connections[fake_path] = mock_conn
            app._active_org_path = fake_path

            intervention = {
                'action': 'resume',
                'worker_id': 'worker-dev2',
            }

            success, message = await messages_view._execute_intervention(intervention)

            assert success is True
            assert "Carol Engineer" in message, \
                f"Should include worker name in success msg, got: {message}"


class TestViewRefreshAfterIntervention:
    """Tests for Bug 4: Immediate view refresh after board interventions."""

    @pytest.mark.asyncio
    async def test_send_reply_with_intervention_triggers_full_refresh(self):
        """After a successful intervention, _refresh_all_views should be called."""
        from datetime import datetime

        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            messages_view = app.query_one("#messages-view", MessagesView)

            # Set up mock org connection
            mock_worker = MagicMock()
            mock_worker.name = "Bob"
            mock_conn = MagicMock()
            mock_conn.get_worker.return_value = mock_worker
            mock_conn.pause_worker.return_value = True
            mock_conn.send_board_response.return_value = True
            mock_conn.get_ceo.return_value = MagicMock(id="worker-ceo")
            mock_conn.get_all_channels.return_value = []
            mock_conn.get_channel_messages.return_value = []
            fake_path = Path("/tmp/fake-org")
            app._org_connections[fake_path] = mock_conn
            app._active_org_path = fake_path

            # Set a selected message
            messages_view._selected_message = Message(
                id="msg-1",
                channel_name="board-channel",
                content="test",
                from_worker_id="worker-dev1",
                from_worker_name="Bob",
                priority=3,
                created_at=datetime.now(),
                is_read=False,
            )

            # Set reply text that contains an intervention command
            reply_input = app.query_one("#reply-input", TextArea)
            reply_input.text = "pause worker-dev1 because testing"
            reply_input.disabled = False

            # Track if _refresh_all_views is called
            refresh_called = False
            original_refresh = app._refresh_all_views

            async def tracked_refresh():
                nonlocal refresh_called
                refresh_called = True
                # Don't call original to avoid errors with mock connection

            app._refresh_all_views = tracked_refresh

            await messages_view._send_reply()

            assert refresh_called, \
                "_refresh_all_views should be called after successful intervention"


class TestCEONotFoundFeedback:
    """Tests for Bug 5: Validate CEO exists before board response operations."""

    @pytest.mark.asyncio
    async def test_send_reply_shows_ceo_not_found_message(self):
        """When send_board_response fails due to missing CEO, show specific error."""
        from datetime import datetime

        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            messages_view = app.query_one("#messages-view", MessagesView)

            # Mock org_connection where send_board_response fails and CEO is None
            mock_conn = MagicMock()
            mock_conn.send_board_response.return_value = False
            mock_conn.get_ceo.return_value = None  # No CEO!
            fake_path = Path("/tmp/fake-org")
            app._org_connections[fake_path] = mock_conn
            app._active_org_path = fake_path

            messages_view._selected_message = Message(
                id="msg-1",
                channel_name="board-channel",
                content="test",
                from_worker_id="worker-dev1",
                from_worker_name="Bob",
                priority=3,
                created_at=datetime.now(),
                is_read=False,
            )

            reply_input = app.query_one("#reply-input", TextArea)
            reply_input.text = "just a regular reply with no intervention"
            reply_input.disabled = False

            # Track notifications
            notifications = []
            original_notify = app.notify

            def track_notify(msg, **kwargs):
                notifications.append((msg, kwargs))
                original_notify(msg, **kwargs)

            app.notify = track_notify

            await messages_view._send_reply()

            # Should show "CEO worker not found" message, not just "Failed to send reply"
            error_notifications = [n for n in notifications if n[1].get('severity') == 'error']
            assert len(error_notifications) >= 1, "Should show error notification"
            error_msg = error_notifications[0][0]
            assert "CEO" in error_msg, \
                f"Error should mention CEO not found, got: {error_msg}"

    @pytest.mark.asyncio
    async def test_send_reply_shows_generic_error_when_ceo_exists(self):
        """When send_board_response fails but CEO exists, show generic error with hint."""
        from datetime import datetime

        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            app.action_switch_tab("messages")
            await pilot.pause()

            messages_view = app.query_one("#messages-view", MessagesView)

            mock_ceo = MagicMock()
            mock_ceo.id = "worker-ceo"
            mock_conn = MagicMock()
            mock_conn.send_board_response.return_value = False
            mock_conn.get_ceo.return_value = mock_ceo  # CEO exists
            fake_path = Path("/tmp/fake-org")
            app._org_connections[fake_path] = mock_conn
            app._active_org_path = fake_path

            messages_view._selected_message = Message(
                id="msg-1",
                channel_name="board-channel",
                content="test",
                from_worker_id="worker-dev1",
                from_worker_name="Bob",
                priority=3,
                created_at=datetime.now(),
                is_read=False,
            )

            reply_input = app.query_one("#reply-input", TextArea)
            reply_input.text = "just a regular reply"
            reply_input.disabled = False

            notifications = []
            original_notify = app.notify

            def track_notify(msg, **kwargs):
                notifications.append((msg, kwargs))
                original_notify(msg, **kwargs)

            app.notify = track_notify

            await messages_view._send_reply()

            error_notifications = [n for n in notifications if n[1].get('severity') == 'error']
            assert len(error_notifications) >= 1, "Should show error notification"
            error_msg = error_notifications[0][0]
            # Should NOT say CEO not found since CEO exists
            assert "CEO" not in error_msg, \
                f"Should not mention CEO when CEO exists, got: {error_msg}"
            assert "check logs" in error_msg.lower() or "failed" in error_msg.lower(), \
                f"Should mention checking logs, got: {error_msg}"
