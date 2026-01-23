"""
Messages view - async board inbox.

Shows:
- Messages escalated to board awaiting response
- Each message: sender, timestamp, priority, preview
- Expand to read full message and compose reply
- Reply is async - worker gets notification when board responds
- Mark as resolved
- Filter by priority/sender
"""

from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Static, TextArea
from textual.widget import Widget

from ..interfaces.org_connection import Message


class MessagesView(Widget):
    """Messages inbox view for async board responses."""

    DEFAULT_CSS = """
    MessagesView {
        layout: horizontal;
        height: 100%;
    }

    #message-list {
        width: 50%;
        border-right: solid $secondary;
    }

    #message-list-header {
        height: auto;
        padding: 1;
        border-bottom: solid $secondary;
    }

    #message-detail {
        width: 50%;
        padding: 1;
    }

    #message-content {
        height: 1fr;
        border: solid $secondary;
        padding: 1;
        margin-bottom: 1;
    }

    #reply-area {
        height: auto;
    }

    #reply-input {
        height: 5;
        margin-bottom: 1;
    }

    .priority-high {
        color: $error;
        text-style: bold;
    }

    .priority-medium {
        color: $warning;
    }

    .priority-low {
        color: $text-muted;
    }

    .unread-badge {
        background: $primary;
        color: $background;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._messages: list[Message] = []
        self._selected_message: Optional[Message] = None

    def compose(self) -> ComposeResult:
        with Container(id="message-list"):
            with Container(id="message-list-header"):
                yield Label("Board Inbox", classes="panel-title")
                yield Label("-- messages", id="unread-label", classes="metric-label")

            table = DataTable(id="messages-table")
            table.add_columns("Pri", "From", "Preview", "Time")
            yield table

        with Container(id="message-detail"):
            yield Label("Select a message", id="detail-header", classes="panel-title")

            with Container(id="message-content"):
                yield Static(
                    "Click on a message in the list to view its contents.",
                    id="message-body",
                )

            with Container(id="reply-area"):
                yield Label("Reply (async - worker will be notified)")
                yield TextArea(id="reply-input", disabled=True)
                with Horizontal():
                    yield Button("Send Reply", id="send-reply-btn", variant="primary", disabled=True)
                    yield Button("Mark Resolved", id="resolve-btn", disabled=True)

    async def on_mount(self) -> None:
        """Load messages when view mounts."""
        await self.refresh_messages()

    async def refresh_messages(self) -> None:
        """Refresh messages from org connection."""
        table = self.query_one("#messages-table", DataTable)
        table.clear()

        if hasattr(self.app, 'org_connection') and self.app.org_connection:
            self._messages = self.app.org_connection.get_board_messages()
            unread_count = self.app.org_connection.get_unread_count()
            self._populate_table_from_connection()
            self._update_unread_label(unread_count)
        else:
            self._populate_placeholder_data()

    def _populate_table_from_connection(self) -> None:
        """Populate table with real message data."""
        table = self.query_one("#messages-table", DataTable)

        for msg in self._messages:
            # Priority icon
            if msg.priority >= 4:
                pri = "🔴"
            elif msg.priority >= 3:
                pri = "🟠"
            else:
                pri = "🔵"

            # Format time relative
            time_str = self._format_relative_time(msg.created_at)

            # Preview of content (first 30 chars)
            preview = msg.content[:30] + "..." if len(msg.content) > 30 else msg.content
            preview = preview.replace("\n", " ")

            table.add_row(
                pri,
                msg.from_worker_name,
                preview,
                time_str,
                key=msg.id,
            )

    def _populate_placeholder_data(self) -> None:
        """Populate table with placeholder data."""
        table = self.query_one("#messages-table", DataTable)
        table.add_row("-", "No Org Connected", "Connect to see messages", "-")
        self._update_unread_label(0)

    def _update_unread_label(self, count: int) -> None:
        """Update unread count label."""
        label = self.query_one("#unread-label", Label)
        if count == 0:
            label.update("No unread messages")
        elif count == 1:
            label.update("1 unread message")
        else:
            label.update(f"{count} unread messages")

    def _format_relative_time(self, dt: datetime) -> str:
        """Format datetime as relative time string."""
        now = datetime.now()
        diff = now - dt

        if diff.total_seconds() < 60:
            return "just now"
        if diff.total_seconds() < 3600:
            mins = int(diff.total_seconds() / 60)
            return f"{mins}m ago"
        if diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"{hours}h ago"
        days = int(diff.total_seconds() / 86400)
        return f"{days}d ago"

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle message selection."""
        table = self.query_one("#messages-table", DataTable)
        row_key = event.row_key

        # Find message by ID
        self._selected_message = next(
            (m for m in self._messages if m.id == row_key), None
        )

        if not self._selected_message:
            return

        # Update detail view
        header = self.query_one("#detail-header", Label)
        header.update(f"From: {self._selected_message.from_worker_name}")

        body = self.query_one("#message-body", Static)
        time_str = self._selected_message.created_at.strftime("%Y-%m-%d %H:%M")
        body.update(
            f"Priority: {'High' if self._selected_message.priority >= 3 else 'Normal'}\n"
            f"Time: {time_str}\n\n"
            f"{self._selected_message.content}"
        )

        # Enable reply controls
        self.query_one("#reply-input", TextArea).disabled = False
        self.query_one("#send-reply-btn", Button).disabled = False
        self.query_one("#resolve-btn", Button).disabled = False

        # Mark as read if connected
        if hasattr(self.app, 'org_connection') and self.app.org_connection:
            self.app.org_connection.mark_message_read(self._selected_message.id)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "send-reply-btn":
            await self._send_reply()
        elif event.button.id == "resolve-btn":
            await self._mark_resolved()

    async def _send_reply(self) -> None:
        """Send async reply to selected message."""
        if not self._selected_message:
            return

        reply_input = self.query_one("#reply-input", TextArea)
        reply_text = reply_input.text

        if not reply_text.strip():
            self.app.notify("Please enter a reply", severity="warning")
            return

        # Send via org connection
        if hasattr(self.app, 'org_connection') and self.app.org_connection:
            success = self.app.org_connection.send_board_response(
                self._selected_message.id,
                reply_text,
            )
            if success:
                self.app.notify("Reply sent! Worker will be notified.")
                reply_input.clear()
                await self.refresh_messages()
            else:
                self.app.notify("Failed to send reply", severity="error")
        else:
            self.app.notify("Not connected to org", severity="error")

    async def _mark_resolved(self) -> None:
        """Mark the selected message as resolved."""
        if not self._selected_message:
            return

        # Mark via org connection (same as marking read)
        if hasattr(self.app, 'org_connection') and self.app.org_connection:
            self.app.org_connection.mark_message_read(self._selected_message.id)
            self.app.notify("Message marked as resolved")
            await self.refresh_messages()
        else:
            self.app.notify("Not connected to org", severity="error")
