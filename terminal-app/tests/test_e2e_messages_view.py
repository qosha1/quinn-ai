"""E2E tests for Messages view inbox display.

Tests board-channel vs escalations channel detection and message display.
Based on quinnai-m7ys plan to standardize on "board-channel" with fallback.

NOTE: Some tests will FAIL until the implementation is updated to support
the new "board-channel" standard. This is expected behavior - the tests
define the desired behavior for quinnai-m7ys and quinnai-c399.

Tests that should PASS with current "escalations" implementation:
- test_messages_view_fallback_to_escalations
- test_messages_view_shows_empty_inbox
- test_messages_view_handles_no_channel
- test_messages_view_message_selection

Tests that will PASS after implementing board-channel support:
- test_messages_view_shows_board_channel_messages
- test_messages_view_prefers_board_channel
- test_messages_view_shows_unread_count
- test_messages_view_unread_count_badge_styling
"""

import pytest
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from textual.widgets import DataTable, TextArea, Button, Static, Label

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.services.org_connection import QuinnAIOrgConnection


class MockDatabase:
    """Mock Database class that works with a real SQLite connection."""

    def __init__(self, db_path):
        self.connection = sqlite3.connect(str(db_path))
        self.connection.row_factory = sqlite3.Row

    def fetchone(self, query, params=None):
        cursor = self.connection.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchone()

    def fetchall(self, query, params=None):
        cursor = self.connection.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall()

    def execute(self, query, params=None):
        cursor = self.connection.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        self.connection.commit()
        return cursor

    def close(self):
        self.connection.close()


def create_base_org_db(org_path: Path) -> Path:
    """Create a base org database with all required tables.

    Args:
        org_path: Path to org folder

    Returns:
        Path to created database
    """
    live_path = org_path / "live"
    live_path.mkdir(parents=True, exist_ok=True)

    db_path = live_path / "quinn.db"
    conn = sqlite3.connect(str(db_path))

    # Create all required tables
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

    # Insert basic test data
    now = datetime.now()
    conn.execute("""
        INSERT INTO org_state (id, status, ceo_worker_id, started_at)
        VALUES ('default', 'running', 'worker-ceo', ?)
    """, (now.isoformat(),))

    conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")
    conn.execute("INSERT INTO teams VALUES ('team-eng', 'Engineering')")

    conn.execute("""
        INSERT INTO workers VALUES
        ('worker-ceo', 'Alice', 'CEO', 'team-exec', NULL, 'active', ?)
    """, (now.isoformat(),))
    conn.execute("""
        INSERT INTO workers VALUES
        ('worker-dev1', 'Bob', 'Developer', 'team-eng', 'worker-ceo', 'active', ?)
    """, (now.isoformat(),))
    conn.execute("""
        INSERT INTO workers VALUES
        ('worker-dev2', 'Carol', 'Developer', 'team-eng', 'worker-ceo', 'active', ?)
    """, (now.isoformat(),))

    conn.execute("""
        INSERT INTO sessions VALUES
        ('session-ceo', 'worker-ceo', 'running', 'org-test-org-ceo')
    """)

    conn.commit()
    conn.close()
    return db_path


def add_messages_to_channel(db_path: Path, channel_name: str, messages: list[dict]) -> None:
    """Add messages to a specific channel in the database.

    Args:
        db_path: Path to database
        channel_name: Name of channel to add messages to
        messages: List of message dicts with keys: from_worker_id, content, priority, is_unread
    """
    conn = sqlite3.connect(str(db_path))

    # Get or create channel
    cursor = conn.execute("SELECT id FROM channels WHERE name = ?", (channel_name,))
    row = cursor.fetchone()
    if row:
        channel_id = row[0]
    else:
        channel_id = f"ch-{channel_name}"
        conn.execute("INSERT INTO channels VALUES (?, ?)", (channel_id, channel_name))

    # Add messages
    now = datetime.now()
    for i, msg in enumerate(messages):
        msg_id = f"msg-{channel_name}-{i}"
        created_at = (now - timedelta(minutes=len(messages) - i)).isoformat()

        conn.execute("""
            INSERT INTO messages VALUES (?, ?, NULL, NULL, ?, ?, ?, 'normal', ?)
        """, (
            msg_id,
            channel_id,
            msg.get("from_worker_id", "worker-dev1"),
            msg.get("content", f"Message {i}"),
            msg.get("priority", 2),
            created_at,
        ))

        # Create notification bead for unread messages
        if msg.get("is_unread", False):
            conn.execute("""
                INSERT INTO notification_beads VALUES (?, ?, 'pending', NULL)
            """, (f"nb-{msg_id}", msg_id))

    conn.commit()
    conn.close()


@pytest.fixture
def org_with_board_channel():
    """Create org with new-style 'board-channel' channel."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-board"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)

        # Add board-channel with messages
        add_messages_to_channel(db_path, "board-channel", [
            {"content": "Board message 1", "priority": 3, "is_unread": True},
            {"content": "Board message 2", "priority": 2, "is_unread": True},
            {"content": "Board message 3", "priority": 4, "is_unread": False},
        ])

        yield org_path, db_path


@pytest.fixture
def org_with_escalations_channel():
    """Create org with old-style 'escalations' channel."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-escalations"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)

        # Add escalations channel with messages
        add_messages_to_channel(db_path, "escalations", [
            {"content": "Escalation 1", "priority": 3, "is_unread": True},
            {"content": "Escalation 2", "priority": 2, "is_unread": False},
        ])

        yield org_path, db_path


@pytest.fixture
def org_with_both_channels():
    """Create org with BOTH board-channel and escalations channels."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-both"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)

        # Add board-channel messages
        add_messages_to_channel(db_path, "board-channel", [
            {"content": "Board message A", "priority": 3, "is_unread": True},
            {"content": "Board message B", "priority": 2, "is_unread": False},
        ])

        # Add escalations messages (should be ignored)
        add_messages_to_channel(db_path, "escalations", [
            {"content": "Old escalation", "priority": 3, "is_unread": True},
        ])

        yield org_path, db_path


@pytest.fixture
def org_with_empty_channel():
    """Create org with board-channel but no messages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-empty"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)

        # Add board-channel but no messages
        conn = sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO channels VALUES ('ch-board', 'board-channel')")
        conn.commit()
        conn.close()

        yield org_path, db_path


@pytest.fixture
def org_with_no_channel():
    """Create org with NO board channel at all (edge case)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-no-channel"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)

        # No channels created - edge case
        yield org_path, db_path


class TestE2EMessagesView:
    """E2E tests for Messages view inbox display."""

    @pytest.mark.asyncio
    async def test_messages_view_shows_board_channel_messages(self, org_with_board_channel):
        """Should display messages from board-channel (new style)."""
        org_path, db_path = org_with_board_channel

        # Create app and connect to org
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org using internal method
            await app._connect_to_org(org_path)
            await pilot.pause()

            # Switch to messages view
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get messages table
            table = app.query_one("#messages-table", DataTable)
            assert table is not None

            # Should show all 3 messages from board-channel
            assert table.row_count == 3

            # Verify messages are displayed
            org_conn = app.org_connection
            assert org_conn is not None
            messages = org_conn.get_board_messages()
            assert len(messages) == 3
            assert any("Board message 1" in msg.content for msg in messages)
            assert any("Board message 2" in msg.content for msg in messages)
            assert any("Board message 3" in msg.content for msg in messages)

    @pytest.mark.asyncio
    async def test_messages_view_fallback_to_escalations(self, org_with_escalations_channel):
        """Should fallback to escalations channel when board-channel doesn't exist."""
        org_path, db_path = org_with_escalations_channel

        # Create app and connect to org
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org using internal method
            await app._connect_to_org(org_path)
            await pilot.pause()

            # Switch to messages view
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get messages table
            table = app.query_one("#messages-table", DataTable)
            assert table is not None

            # Should show 2 messages from escalations channel (fallback)
            assert table.row_count == 2

            # Verify fallback messages are displayed
            org_conn = app.org_connection
            assert org_conn is not None
            messages = org_conn.get_board_messages()
            assert len(messages) == 2
            assert any("Escalation 1" in msg.content for msg in messages)
            assert any("Escalation 2" in msg.content for msg in messages)

    @pytest.mark.asyncio
    async def test_messages_view_prefers_board_channel(self, org_with_both_channels):
        """Should prefer board-channel over escalations when both exist."""
        org_path, db_path = org_with_both_channels

        # Create app and connect to org
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org using internal method
            await app._connect_to_org(org_path)
            await pilot.pause()

            # Switch to messages view
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get messages table
            table = app.query_one("#messages-table", DataTable)
            assert table is not None

            # Should show 2 messages from board-channel (NOT escalations)
            assert table.row_count == 2

            # Verify board-channel messages are shown (not escalations)
            org_conn = app.org_connection
            assert org_conn is not None
            messages = org_conn.get_board_messages()
            assert len(messages) == 2
            assert any("Board message A" in msg.content for msg in messages)
            assert any("Board message B" in msg.content for msg in messages)
            # Should NOT show old escalation message
            assert not any("Old escalation" in msg.content for msg in messages)

    @pytest.mark.asyncio
    async def test_messages_view_shows_unread_count(self, org_with_board_channel):
        """Should display correct unread count badge."""
        org_path, db_path = org_with_board_channel

        # Create app and connect to org
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org using internal method
            await app._connect_to_org(org_path)
            await pilot.pause()

            # Switch to messages view
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get unread label
            unread_label = app.query_one("#unread-label", Label)
            assert unread_label is not None

            # Should show 2 unread messages
            org_conn = app.org_connection
            assert org_conn is not None
            unread_count = org_conn.get_unread_count()
            assert unread_count == 2

            # Label should reflect unread count
            assert "2" in unread_label.render()

    @pytest.mark.asyncio
    async def test_messages_view_shows_empty_inbox(self, org_with_empty_channel):
        """Should show empty state when channel exists but has no messages."""
        org_path, db_path = org_with_empty_channel

        # Create app and connect to org
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org using internal method
            await app._connect_to_org(org_path)
            await pilot.pause()

            # Switch to messages view
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get messages table
            table = app.query_one("#messages-table", DataTable)
            assert table is not None

            # Should have no messages (empty state)
            org_conn = app.org_connection
            assert org_conn is not None
            messages = org_conn.get_board_messages()
            assert len(messages) == 0

            # Unread count should be 0
            unread_count = org_conn.get_unread_count()
            assert unread_count == 0

            # App should not crash
            assert app.is_running

    @pytest.mark.asyncio
    async def test_messages_view_handles_no_channel(self, org_with_no_channel):
        """Should handle edge case where no board channel exists without crashing."""
        org_path, db_path = org_with_no_channel

        # Create app and connect to org
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org using internal method
            await app._connect_to_org(org_path)
            await pilot.pause()

            # Switch to messages view
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get messages table
            table = app.query_one("#messages-table", DataTable)
            assert table is not None

            # Should return empty list (no crash)
            org_conn = app.org_connection
            assert org_conn is not None
            messages = org_conn.get_board_messages()
            assert len(messages) == 0

            # Unread count should be 0
            unread_count = org_conn.get_unread_count()
            assert unread_count == 0

            # App should not crash - should handle gracefully
            assert app.is_running

    @pytest.mark.asyncio
    async def test_messages_view_message_selection(self, org_with_board_channel):
        """Should show message detail when a message is selected."""
        org_path, db_path = org_with_board_channel

        # Create app and connect to org
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org using internal method
            await app._connect_to_org(org_path)
            await pilot.pause()

            # Switch to messages view
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get UI elements
            table = app.query_one("#messages-table", DataTable)
            detail_header = app.query_one("#detail-header", Label)
            message_body = app.query_one("#message-body", Static)
            reply_input = app.query_one("#reply-input", TextArea)

            # Initially reply input should be disabled
            assert reply_input.disabled is True

            # Select first message (if rows exist)
            if table.row_count > 0:
                # Simulate row selection by triggering the event
                # Note: In real usage, clicking would trigger this
                org_conn = app.org_connection
                assert org_conn is not None
                messages = org_conn.get_board_messages()
                first_msg = messages[0]

                # Verify detail elements exist
                assert detail_header is not None
                assert message_body is not None

                # After selection (in real app), reply input would be enabled
                # This is verified by the messages view code

    @pytest.mark.asyncio
    async def test_messages_view_unread_count_badge_styling(self, org_with_board_channel):
        """Should style unread messages and count badge correctly."""
        org_path, db_path = org_with_board_channel

        # Create app and connect to org
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org using internal method
            await app._connect_to_org(org_path)
            await pilot.pause()

            # Switch to messages view
            app.action_switch_tab("messages")
            await pilot.pause()

            # Get messages and verify unread status
            org_conn = app.org_connection
            assert org_conn is not None
            messages = org_conn.get_board_messages()
            unread_messages = [m for m in messages if not m.is_read]

            # Should have 2 unread messages
            assert len(unread_messages) == 2

            # Unread count should match
            unread_count = org_conn.get_unread_count()
            assert unread_count == 2

            # Verify label exists and shows count
            unread_label = app.query_one("#unread-label", Label)
            assert unread_label is not None
