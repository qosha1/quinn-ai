"""
Messages view - channel-based messaging interface.

Shows:
- All channels with channel selector
- Messages from selected channel
- Each message: sender, timestamp, priority, preview
- Expand to read full message and compose reply
- Reply is async - worker gets notification when board responds
- Mark as resolved
- Filter by priority/sender
"""

from datetime import datetime
from typing import Optional
import re

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TextArea
from textual.widget import Widget

from ..interfaces.org_connection import Message


def _parse_intervention_command(text: str) -> Optional[dict]:
    """Parse intervention commands from reply text.

    Returns:
        Dict with {action, worker_id, reason} or None
    """
    # Patterns: "pause worker-123 because XYZ", "fire worker-abc: reason", "resume worker-xyz"
    patterns = [
        (r'pause\s+([a-zA-Z0-9-]+)(?:\s+(?:because|reason:?)\s+(.+))?', 'pause'),
        (r'fire\s+([a-zA-Z0-9-]+)(?:\s*:?\s*(.+))?', 'fire'),
        (r'resume\s+([a-zA-Z0-9-]+)', 'resume'),
    ]

    for pattern, action in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            worker_id = match.group(1)
            reason = match.group(2) if len(match.groups()) > 1 else None
            return {
                'action': action,
                'worker_id': worker_id,
                'reason': reason or f"Board intervention via message reply"
            }

    return None


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
        self._channels: list[dict] = []
        self._current_channel_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Container(id="message-list"):
            with Container(id="message-list-header"):
                yield Label("Messages", classes="panel-title")
                yield Select(
                    [("Loading channels...", "")],
                    id="channel-selector",
                    allow_blank=False,
                )
                yield Label("-- messages", id="unread-label", classes="metric-label")

            table = DataTable(id="messages-table", cursor_type="row")
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
                yield Static("No messages. Select a message from the list to reply.", id="reply-placeholder")
                yield TextArea(id="reply-input", disabled=True, classes="hidden")
                with Horizontal(classes="hidden", id="reply-buttons"):
                    yield Button("Send Reply", id="send-reply-btn", variant="primary", disabled=True)
                    yield Button("Mark Resolved", id="resolve-btn", disabled=True)

    async def on_mount(self) -> None:
        """Load messages when view mounts."""
        await self.refresh_messages()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle channel selector change."""
        if event.select.id == "channel-selector":
            new_channel_id = event.value
            if new_channel_id and new_channel_id != self._current_channel_id:
                self._current_channel_id = new_channel_id
                await self._load_channel_messages()

    async def _load_channel_messages(self) -> None:
        """Load messages for the currently selected channel."""
        if not self._current_channel_id or not hasattr(self.app, 'org_connection') or not self.app.org_connection:
            return

        table = self.query_one("#messages-table", DataTable)
        table.clear()

        self._messages = self.app.org_connection.get_channel_messages(
            self._current_channel_id
        )
        self._populate_table_from_connection()

        # Update unread count
        current_channel = next(
            (c for c in self._channels if c["id"] == self._current_channel_id),
            None
        )
        unread_count = current_channel["unread_count"] if current_channel else 0
        self._update_unread_label(unread_count)

    async def refresh_messages(self) -> None:
        """Refresh channels and messages from org connection."""
        if hasattr(self.app, 'org_connection') and self.app.org_connection:
            # Load channels
            self._channels = self.app.org_connection.get_all_channels()
            self._update_channel_selector()

            # Load messages from current channel (or first channel if none selected)
            if not self._current_channel_id and self._channels:
                self._current_channel_id = self._channels[0]["id"]

            if self._current_channel_id:
                self._messages = self.app.org_connection.get_channel_messages(
                    self._current_channel_id
                )
                self._populate_table_from_connection()

                # Update unread count for current channel
                current_channel = next(
                    (c for c in self._channels if c["id"] == self._current_channel_id),
                    None
                )
                unread_count = current_channel["unread_count"] if current_channel else 0
                self._update_unread_label(unread_count)
            else:
                table = self.query_one("#messages-table", DataTable)
                table.clear()
                self._update_unread_label(0)
        else:
            self._populate_placeholder_data()

    def _update_channel_selector(self) -> None:
        """Update channel selector with available channels."""
        selector = self.query_one("#channel-selector", Select)

        if not self._channels:
            selector.set_options([("No channels", "")])
            return

        # Build options: "#channel-name (unread count)"
        options = []
        for channel in self._channels:
            unread_badge = f" ({channel['unread_count']})" if channel['unread_count'] > 0 else ""
            label = f"#{channel['name']}{unread_badge}"
            options.append((label, channel["id"]))

        selector.set_options(options)

        # Select current channel
        if self._current_channel_id:
            selector.value = self._current_channel_id

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

        # Show and enable reply controls
        self.query_one("#reply-placeholder", Static).add_class("hidden")
        reply_input = self.query_one("#reply-input", TextArea)
        reply_input.remove_class("hidden")
        reply_input.disabled = False
        self.query_one("#reply-buttons").remove_class("hidden")
        self.query_one("#send-reply-btn", Button).disabled = False
        self.query_one("#resolve-btn", Button).disabled = False

        # Mark as read if connected
        if hasattr(self.app, 'org_connection') and self.app.org_connection:
            self.app.org_connection.mark_message_read(self._selected_message.id)

    async def _execute_intervention(self, intervention: dict) -> tuple[bool, str]:
        """Execute board intervention.

        Returns:
            (success, message)
        """
        if not hasattr(self.app, 'org_connection') or not self.app.org_connection:
            return False, "Not connected to org"

        action = intervention['action']
        worker_id = intervention['worker_id']
        reason = intervention.get('reason', '')

        try:
            if action == 'pause':
                success = self.app.org_connection.pause_worker(worker_id, reason)
                return success, f"Worker {worker_id} paused" if success else "Pause failed"
            elif action == 'resume':
                success = self.app.org_connection.resume_worker(worker_id)
                return success, f"Worker {worker_id} resumed" if success else "Resume failed"
            elif action == 'fire':
                success = self.app.org_connection.fire_worker(worker_id, reason)
                return success, f"Worker {worker_id} terminated" if success else "Termination failed"
            else:
                return False, f"Unknown action: {action}"
        except Exception as e:
            return False, str(e)

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
        reply_text = reply_input.text.strip()

        if not reply_text:
            self.app.notify("Please enter a reply", severity="warning")
            return

        # Parse for intervention commands
        intervention = _parse_intervention_command(reply_text)

        if intervention:
            # Execute intervention
            success, message = await self._execute_intervention(intervention)
            if success:
                self.app.notify(message, severity="information")
                # Also send the reply as a message for audit trail
                # ... fall through to send message ...
            else:
                self.app.notify(f"Intervention failed: {message}", severity="error")
                return

        # Send reply (existing logic continues)
        if hasattr(self.app, 'org_connection') and self.app.org_connection:
            success = self.app.org_connection.send_board_response(
                self._selected_message.id,
                reply_text,
            )
            if success:
                self.app.notify("Reply sent successfully", severity="information")
                reply_input.text = ""
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

    def export_as_text(self) -> str:
        """Export messages view content as plain text.

        Returns:
            Formatted text representation of messages
        """
        lines = []
        lines.append("=" * 60)
        lines.append("QUINNAI BOARD - MESSAGES")
        lines.append("=" * 60)
        lines.append("")

        # Current channel info
        current_channel = next(
            (c for c in self._channels if c["id"] == self._current_channel_id),
            None
        )
        if current_channel:
            lines.append(f"Channel: #{current_channel['name']}")
            lines.append(f"Unread Messages: {current_channel['unread_count']}")
            lines.append("")

        # Messages
        if not self._messages:
            lines.append("No messages in this channel")
        else:
            lines.append(f"Messages ({len(self._messages)} total):")
            lines.append("")

            for msg in self._messages:
                lines.append("-" * 60)
                lines.append(f"From: {msg.from_worker_name}")
                lines.append(f"Time: {msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                priority_label = "High" if msg.priority >= 4 else "Medium" if msg.priority >= 3 else "Low"
                lines.append(f"Priority: {priority_label}")
                lines.append("")
                lines.append(msg.content)
                lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
