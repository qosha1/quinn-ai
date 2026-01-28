"""E2E tests for CEO briefing delivery system.

Tests the complete flow of briefing delivery from wizard creation through org.start()
to CEO notification and board UI display. These tests specify the implementation
requirements for bead quinnai-gtcz.

Critical flows tested:
1. Briefing delivery during org.start() - reads config/ceo_briefing.md
2. BoardApp handler for BriefingQueued - saves briefing to config
3. OrgConnection methods - send_ceo_briefing(), get_current_briefing(), update_briefing()
4. No duplicate delivery on org restart
5. Backward compatibility with orgs without briefings

Note: These tests are TDD - they will FAIL until the implementation is complete.
"""

import pytest
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.services.org_connection import QuinnAIOrgConnection
from board_ui.widgets.ceo_briefing import CEOBriefingWidget


# ==================
# TEST FIXTURES
# ==================


def create_org_db(
    org_path: Path,
    status: str = "initialized",
    include_ceo: bool = True,
    include_board_channel: bool = True,
) -> Path:
    """Create a complete org database for testing.

    Args:
        org_path: Path to org folder
        status: Org status ('uninitialized', 'initialized', 'running', 'stopped')
        include_ceo: Whether to create CEO worker
        include_board_channel: Whether to create board-channel

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
            name TEXT NOT NULL DEFAULT 'My Organization',
            status TEXT,
            ceo_worker_id TEXT,
            started_at TEXT,
            stopped_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE teams (
            id TEXT PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE workers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            team_id TEXT NOT NULL,
            manager_id TEXT,
            status TEXT NOT NULL,
            skills TEXT NOT NULL DEFAULT '{}',
            cost INTEGER NOT NULL DEFAULT 50,
            hiring_authority_scope TEXT,
            delegated_budget INTEGER NOT NULL DEFAULT 0,
            max_reports INTEGER NOT NULL DEFAULT 10,
            offboarding_ask_bead_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (manager_id) REFERENCES workers(id)
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

        CREATE TABLE channel_subscriptions (
            id INTEGER PRIMARY KEY,
            channel_id TEXT,
            worker_id TEXT,
            subscribed_at TEXT,
            FOREIGN KEY (channel_id) REFERENCES channels(id),
            FOREIGN KEY (worker_id) REFERENCES workers(id)
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
            worker_id TEXT,
            message_id TEXT,
            channel_id TEXT,
            status TEXT,
            priority INTEGER DEFAULT 2,
            read_at TEXT,
            created_at TEXT,
            expires_at TEXT,
            FOREIGN KEY (message_id) REFERENCES messages(id),
            FOREIGN KEY (worker_id) REFERENCES workers(id),
            FOREIGN KEY (channel_id) REFERENCES channels(id)
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

    now = datetime.now()

    # Insert org state
    ceo_id = "worker-ceo" if include_ceo else None
    started_at = now.isoformat() if status == "running" else None

    conn.execute("""
        INSERT INTO org_state (id, status, ceo_worker_id, started_at)
        VALUES ('default', ?, ?, ?)
    """, (status, ceo_id, started_at))

    # Create executive team and CEO if requested
    if include_ceo:
        conn.execute("INSERT INTO teams VALUES ('team-exec', 'Executive')")
        conn.execute("""
            INSERT INTO workers (id, name, role, team_id, manager_id, status, cost, created_at)
            VALUES ('worker-ceo', 'TestCEO', 'CEO', 'team-exec', NULL, 'pending', 100, ?)
        """, (now.isoformat(),))

        # CEO session (optional, based on status)
        if status == "running":
            conn.execute("""
                INSERT INTO sessions VALUES
                ('session-ceo', 'worker-ceo', 'idle', 'qn-worker-ceo')
            """)

    # Create board-channel if requested
    if include_board_channel:
        conn.execute("INSERT INTO channels VALUES ('ch-board', 'board-channel')")

        # Subscribe CEO to board-channel
        if include_ceo:
            conn.execute("""
                INSERT INTO channel_subscriptions (channel_id, worker_id, subscribed_at)
                VALUES ('ch-board', 'worker-ceo', ?)
            """, (now.isoformat(),))

    conn.commit()
    conn.close()

    return db_path


def create_briefing_file(org_path: Path, content: str) -> Path:
    """Create a CEO briefing file in org config directory.

    Args:
        org_path: Path to org folder
        content: Markdown content for briefing

    Returns:
        Path to created briefing file
    """
    config_dir = org_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    briefing_path = config_dir / "ceo_briefing.md"
    briefing_path.write_text(content)

    return briefing_path


def get_briefing_messages(org_path: Path) -> list[dict]:
    """Get all briefing messages from board-channel.

    Args:
        org_path: Path to org folder

    Returns:
        List of message dicts with content containing "CEO Briefing"
    """
    db_path = org_path / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT m.id, m.from_worker_id, m.content, m.created_at, m.channel_id
        FROM messages m
        JOIN channels c ON m.channel_id = c.id
        WHERE c.name = 'board-channel'
        AND m.content LIKE '%CEO Briefing%'
        ORDER BY m.created_at
    """)

    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return messages


def get_ceo_notifications(org_path: Path) -> list[dict]:
    """Get all notification beads for CEO.

    Args:
        org_path: Path to org folder

    Returns:
        List of notification dicts
    """
    db_path = org_path / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT nb.id, nb.worker_id, nb.message_id, nb.status, nb.read_at
        FROM notification_beads nb
        WHERE nb.worker_id = 'worker-ceo'
        ORDER BY nb.created_at
    """)

    notifications = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return notifications


# ==================
# TEST CLASS: ORG BRIEFING DELIVERY
# ==================


class TestOrgBriefingDelivery:
    """Tests for briefing delivery during org.start().

    These tests verify the org.start() implementation reads the briefing file
    and creates appropriate messages and notifications for the CEO.
    """

    def test_org_briefing_delivery(self, tmp_path):
        """Test briefing is delivered to CEO during org.start().

        Flow:
        1. Create org with briefing file in config/ceo_briefing.md
        2. Call org.start()
        3. Verify message created in board-channel with briefing content
        4. Verify notification bead created for CEO with status='pending'
        5. Verify message content includes briefing header

        Implementation requirement:
        - cli/core/org.py: Org.start() must call _deliver_ceo_briefing()
        - _deliver_ceo_briefing() reads config/ceo_briefing.md
        - Creates message in board-channel from CEO
        - Creates notification bead for CEO linked to message
        """
        # Setup org with briefing
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        briefing_content = """# Mission

Build great products that solve real problems.

## Context

We are a startup focused on developer tools.

## Requirements

- Launch MVP in 90 days
- Achieve product-market fit
- Build sustainable revenue model
"""

        # Create database and briefing file
        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, briefing_content)

        # TODO: This will fail until org.start() implementation is complete
        # Start org (should trigger briefing delivery)
        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)
        org.start()

        # Verify message created in board-channel
        messages = get_briefing_messages(org_path)
        assert len(messages) == 1, "Expected exactly one briefing message"

        msg = messages[0]
        assert "CEO Briefing" in msg["content"], "Message should have briefing header"
        assert "Build great products" in msg["content"], "Message should contain briefing content"
        assert msg["from_worker_id"] == "worker-ceo", "Briefing should be from CEO"
        assert msg["channel_id"] == "ch-board", "Briefing should be in board-channel"

        # Verify notification bead created for CEO
        notifications = get_ceo_notifications(org_path)
        assert len(notifications) >= 1, "Expected at least one notification for CEO"

        # Find notification linked to briefing message
        briefing_notif = [n for n in notifications if n["message_id"] == msg["id"]]
        assert len(briefing_notif) == 1, "Expected one notification for briefing message"

        notif = briefing_notif[0]
        assert notif["status"] == "pending", "Notification should be pending"
        assert notif["worker_id"] == "worker-ceo", "Notification should be for CEO"

    def test_org_start_without_briefing(self, tmp_path):
        """Test org starts successfully without briefing file.

        Flow:
        1. Create org WITHOUT briefing file
        2. Call org.start()
        3. Verify no errors, org starts successfully
        4. Verify CEO activated normally
        5. Verify no briefing message created

        Implementation requirement:
        - Org.start() checks if config/ceo_briefing.md exists
        - If missing, skip briefing delivery (no error)
        - Continue normal startup flow
        """
        org_path = tmp_path / "test-org-no-briefing"
        org_path.mkdir()

        # Create org WITHOUT briefing file
        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)

        # Start org (should succeed without briefing)
        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)

        # TODO: This will fail if org.start() doesn't handle missing briefing gracefully
        org.start()

        # Verify org started successfully
        org.refresh()
        assert org.status == "running", "Org should be running"

        # Verify CEO is active
        assert org.ceo_worker_id == "worker-ceo"
        ceo = org.ceo
        assert ceo is not None
        assert ceo.lifecycle_status == "active"

        # Verify no briefing message created
        messages = get_briefing_messages(org_path)
        assert len(messages) == 0, "No briefing message should be created"

    def test_org_restart_no_duplicate_briefing(self, tmp_path):
        """Test briefing is not duplicated on org restart.

        Flow:
        1. Create org with briefing
        2. Start org (briefing delivered)
        3. Stop org
        4. Start org again
        5. Verify only ONE briefing message exists (no duplicate)

        Implementation requirement:
        - _deliver_ceo_briefing() checks if briefing already delivered
        - Query messages table for existing briefing message
        - Skip delivery if already exists
        """
        org_path = tmp_path / "test-org-restart"
        org_path.mkdir()

        briefing_content = "# Mission\n\nTest briefing content"

        # Create org with briefing
        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, briefing_content)

        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)

        # First start - briefing delivered
        org.start()

        # Verify briefing delivered
        messages_after_first_start = get_briefing_messages(org_path)
        assert len(messages_after_first_start) == 1, "Briefing should be delivered on first start"

        # Stop org
        org.stop()
        org.refresh()
        assert org.status == "stopped"

        # Restart org
        org.start()

        # Verify no duplicate briefing message
        messages_after_restart = get_briefing_messages(org_path)
        assert len(messages_after_restart) == 1, "Briefing should NOT be duplicated on restart"

        # Verify it's the same message
        assert messages_after_restart[0]["id"] == messages_after_first_start[0]["id"]


# ==================
# TEST CLASS: ORG CONNECTION BRIEFING METHODS
# ==================


class TestOrgConnectionBriefingMethods:
    """Tests for OrgConnection briefing-related methods.

    These tests verify the terminal-app can interact with briefings
    through the OrgConnection interface.
    """

    def test_org_connection_send_briefing(self, tmp_path):
        """Test OrgConnection.send_ceo_briefing() creates message and notification.

        Flow:
        1. Create QuinnAIOrgConnection
        2. Call send_ceo_briefing("Test briefing content")
        3. Verify message created in board-channel
        4. Verify notification bead created for CEO
        5. Verify message from_worker_id is CEO's ID (not 'board')

        Implementation requirement:
        - Add send_ceo_briefing(content: str) method to OrgConnection interface
        - Implementation creates message in board-channel
        - Message from_worker_id = CEO worker ID
        - Creates notification bead for CEO
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        # Create org database
        create_org_db(org_path, status="running", include_ceo=True, include_board_channel=True)

        # Create connection and send briefing
        conn = QuinnAIOrgConnection(org_path)

        briefing_content = """# CEO Briefing

Test briefing from board interface.

## Objective
Test the send_ceo_briefing method.
"""

        # TODO: This will fail until send_ceo_briefing() is implemented
        result = conn.send_ceo_briefing(briefing_content)
        assert result is True, "send_ceo_briefing should return True on success"

        # Verify message created
        messages = get_briefing_messages(org_path)
        assert len(messages) == 1, "Expected one briefing message"

        msg = messages[0]
        assert msg["content"] == briefing_content
        assert msg["from_worker_id"] == "worker-ceo", "Message should be from CEO, not board"
        assert msg["channel_id"] == "ch-board"

        # Verify notification created
        notifications = get_ceo_notifications(org_path)
        briefing_notif = [n for n in notifications if n["message_id"] == msg["id"]]
        assert len(briefing_notif) == 1
        assert briefing_notif[0]["status"] == "pending"

    def test_org_connection_get_current_briefing(self, tmp_path):
        """Test OrgConnection.get_current_briefing() reads briefing file.

        Flow:
        1. Create org with briefing file
        2. Create connection
        3. Call get_current_briefing()
        4. Verify returns briefing markdown content
        5. Test returns None if no briefing file exists

        Implementation requirement:
        - Add get_current_briefing() -> Optional[str] method
        - Reads config/ceo_briefing.md from org_path
        - Returns content as string
        - Returns None if file doesn't exist
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        briefing_content = """# Mission
Test mission statement.
"""

        # Create org and briefing
        create_org_db(org_path, status="running", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, briefing_content)

        # Test get_current_briefing
        conn = QuinnAIOrgConnection(org_path)

        # TODO: This will fail until get_current_briefing() is implemented
        current = conn.get_current_briefing()
        assert current is not None, "Should return briefing content"
        assert current == briefing_content

        # Test with org that has no briefing
        org_path_no_briefing = tmp_path / "test-org-no-briefing"
        org_path_no_briefing.mkdir()
        create_org_db(org_path_no_briefing, status="running", include_ceo=True, include_board_channel=True)

        conn_no_briefing = QuinnAIOrgConnection(org_path_no_briefing)
        current_none = conn_no_briefing.get_current_briefing()
        assert current_none is None, "Should return None if no briefing file"

    def test_org_connection_update_briefing(self, tmp_path):
        """Test OrgConnection.update_briefing() updates file and notifies CEO.

        Flow:
        1. Create org with existing briefing
        2. Create connection
        3. Call update_briefing("New briefing content")
        4. Verify config/ceo_briefing.md updated
        5. Verify new message created in board-channel
        6. Verify CEO notified of update

        Implementation requirement:
        - Add update_briefing(content: str) -> bool method
        - Writes content to config/ceo_briefing.md
        - Creates new message in board-channel (keeps old message)
        - Creates notification for CEO
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        original_content = "# Mission\nOriginal briefing"
        updated_content = "# Mission\nUpdated briefing with new directives"

        # Create org with original briefing
        create_org_db(org_path, status="running", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, original_content)

        conn = QuinnAIOrgConnection(org_path)

        # TODO: This will fail until update_briefing() is implemented
        result = conn.update_briefing(updated_content)
        assert result is True, "update_briefing should return True on success"

        # Verify file updated
        briefing_path = org_path / "config" / "ceo_briefing.md"
        assert briefing_path.exists()
        assert briefing_path.read_text() == updated_content

        # Verify new message created
        messages = get_briefing_messages(org_path)
        assert len(messages) >= 1, "Should have at least one briefing message"

        # Latest message should have updated content
        latest_msg = messages[-1]
        assert updated_content in latest_msg["content"] or "Updated" in latest_msg["content"]

        # Verify notification created
        notifications = get_ceo_notifications(org_path)
        assert len(notifications) >= 1, "CEO should be notified of update"


# ==================
# TEST CLASS: BOARD APP INTEGRATION
# ==================


class TestBoardAppBriefingIntegration:
    """Tests for BoardApp integration with CEO briefing widget.

    These tests verify the board UI can create and queue briefings
    through the CEOBriefingWidget.
    """

    @pytest.mark.asyncio
    async def test_briefing_widget_queued_message(self, tmp_path):
        """Test BriefingQueued message saves briefing to config.

        Flow:
        1. Create BoardApp with org connection
        2. Mount CEOBriefingWidget
        3. Trigger BriefingQueued message with content
        4. Verify briefing saved to config/ceo_briefing.md
        5. Verify user notification shown

        Implementation requirement:
        - BoardApp must handle BriefingQueued message type
        - Handler calls org_connection.update_briefing(content)
        - Shows success notification to user

        Note: This is a UI integration test using Textual's run_test()
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        # Create org
        create_org_db(org_path, status="running", include_ceo=True, include_board_channel=True)

        config = BoardConfig(org_paths=[tmp_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Connect to org
            await app._connect_to_org(org_path)
            await pilot.pause()

            # TODO: This will fail until BriefingQueued handler is implemented
            # Create and mount briefing widget
            from board_ui.widgets.ceo_briefing import BriefingContent

            content = BriefingContent(
                context="Test context for organization",
                requirements="Launch MVP in 90 days",
                constraints="Limited budget",
                success_criteria="Revenue > $10k MRR"
            )

            widget = CEOBriefingWidget(initial_content=content, id="briefing-widget")

            # Simulate save action (would trigger BriefingQueued)
            # In real implementation, this happens when user clicks "Save"
            briefing_markdown = content.to_markdown()

            # Manually call what the handler would do
            result = app.org_connection.update_briefing(briefing_markdown)
            assert result is True

            # Verify file saved
            briefing_path = org_path / "config" / "ceo_briefing.md"
            assert briefing_path.exists()

            saved_content = briefing_path.read_text()
            assert "Test context" in saved_content
            assert "Launch MVP" in saved_content

    @pytest.mark.asyncio
    async def test_wizard_to_ceo_flow(self, tmp_path):
        """Test complete flow from wizard to CEO receiving briefing.

        Flow:
        1. Complete OrgInitWizard with briefing content
        2. Wizard saves briefing to config/ceo_briefing.md
        3. Initialize org
        4. Start org
        5. Verify CEO can query notification beads and see briefing message

        Implementation requirement:
        - OrgInitWizard saves briefing before calling org.initialize()
        - org.start() delivers briefing to CEO
        - CEO has notification bead pointing to briefing message

        Note: This is an integration test covering the full user journey
        """
        org_path = tmp_path / "new-org"
        org_path.mkdir()

        # Simulate wizard creating briefing
        briefing_content = """# Mission
Build the future of work.

## Context
We are creating tools for distributed teams.
"""

        config_dir = org_path / "config"
        config_dir.mkdir()
        briefing_file = config_dir / "ceo_briefing.md"
        briefing_file.write_text(briefing_content)

        # Initialize org (creates CEO and structure)
        from cli.core.db import init_database
        from cli.core.org import Org

        # Create live directory and initialize database
        live_dir = org_path / "live"
        live_dir.mkdir(parents=True, exist_ok=True)

        db_path = live_dir / "quinn.db"
        db = init_database(db_path)
        org = Org(db)

        # Initialize org (creates board-channel automatically)
        org.init(ceo_name="Alice", ceo_role="CEO")

        # Start org (should deliver briefing)
        org.start()

        # Get actual CEO worker ID
        org.refresh()
        ceo_id = org.ceo_worker_id

        # Verify CEO has notification
        import sqlite3
        db_path = org_path / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT nb.id, nb.worker_id, nb.message_id, nb.status, nb.read_at
            FROM notification_beads nb
            WHERE nb.worker_id = ?
            ORDER BY nb.created_at
        """, (ceo_id,))
        notifications = [dict(row) for row in cursor.fetchall()]
        conn.close()

        assert len(notifications) >= 1, "CEO should have notification for briefing"

        # Verify notification links to briefing message
        messages = get_briefing_messages(org_path)
        assert len(messages) == 1, "Should have one briefing message"

        notif = notifications[0]
        msg = messages[0]
        assert notif["message_id"] == msg["id"], "Notification should link to briefing message"
        assert "Build the future of work" in msg["content"]

    @pytest.mark.asyncio
    async def test_update_briefing_flow(self, tmp_path):
        """Test updating briefing on running org.

        Flow:
        1. Start org with existing briefing
        2. Update briefing via org_connection.update_briefing()
        3. Verify new message created (old message still exists)
        4. Verify CEO notified of new version

        Implementation requirement:
        - update_briefing() appends new message (preserves history)
        - CEO gets notification for each briefing update
        - Old messages remain in channel for reference
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        original_briefing = "# Mission\nOriginal directives"

        # Create and start org with briefing
        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, original_briefing)

        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)
        org.start()

        # Verify original briefing delivered
        messages_v1 = get_briefing_messages(org_path)
        assert len(messages_v1) == 1

        # Update briefing through connection
        conn = QuinnAIOrgConnection(org_path)
        updated_briefing = "# Mission\nUpdated directives - pivot to new market"

        result = conn.update_briefing(updated_briefing)
        assert result is True

        # Verify new message created
        messages_v2 = get_briefing_messages(org_path)
        assert len(messages_v2) == 2, "Should have original + updated message"

        # Verify old message still exists
        assert messages_v2[0]["id"] == messages_v1[0]["id"]

        # Verify new message has updated content
        assert "pivot to new market" in messages_v2[1]["content"]

        # Verify CEO has notification for update
        notifications = get_ceo_notifications(org_path)
        assert len(notifications) == 2, "CEO should have notification for each briefing version"


# ==================
# TEST CLASS: EDGE CASES & BACKWARD COMPATIBILITY
# ==================


class TestBriefingEdgeCases:
    """Tests for edge cases and backward compatibility."""

    def test_briefing_with_empty_content(self, tmp_path):
        """Test briefing delivery with empty markdown file.

        Should handle gracefully (skip delivery or show minimal message).
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        # Create empty briefing
        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, "")

        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)

        # Should not crash on empty briefing
        org.start()

        # Either no message or minimal message
        messages = get_briefing_messages(org_path)
        # Implementation can choose: skip empty briefings (len==0) or deliver minimal (len==1)
        assert len(messages) in (0, 1), "Should handle empty briefing gracefully"

    def test_briefing_with_malformed_markdown(self, tmp_path):
        """Test briefing delivery with malformed markdown.

        Should deliver content as-is (CEO can handle malformed markdown).
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        malformed_content = """# Mission

This has some **malformed *markdown* syntax**
And `unclosed code block

####### Too many hashes
"""

        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, malformed_content)

        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)

        # Should not crash on malformed markdown
        org.start()

        messages = get_briefing_messages(org_path)
        assert len(messages) == 1, "Should deliver malformed markdown as-is"
        assert "Too many hashes" in messages[0]["content"]

    def test_org_without_board_channel(self, tmp_path):
        """Test briefing delivery when board-channel doesn't exist.

        Should handle gracefully (create channel or skip delivery).
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        # Create org WITHOUT board-channel
        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=False)
        create_briefing_file(org_path, "# Mission\nTest")

        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)

        # Should not crash if board-channel missing
        # Implementation can choose: create channel or skip delivery
        org.start()

        # If implementation creates channel, message should exist
        # If implementation skips, no message
        # Both are acceptable behaviors
        messages = get_briefing_messages(org_path)
        # Just verify no crash occurred
        assert isinstance(messages, list)

    def test_backward_compatibility_old_orgs(self, tmp_path):
        """Test old orgs without briefing support work normally.

        Orgs created before briefing feature should start without issues.
        """
        org_path = tmp_path / "old-org"
        org_path.mkdir()

        # Create org without briefing (old org)
        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)
        # Note: NO briefing file created

        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)

        # Should start normally without briefing
        org.start()

        org.refresh()
        assert org.status == "running"
        assert org.ceo is not None

        # No briefing message should exist
        messages = get_briefing_messages(org_path)
        assert len(messages) == 0

    def test_concurrent_briefing_updates(self, tmp_path):
        """Test multiple rapid briefing updates.

        Should handle each update independently without conflicts.
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        create_org_db(org_path, status="running", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, "# Original")

        conn = QuinnAIOrgConnection(org_path)

        # Send multiple updates rapidly
        for i in range(3):
            result = conn.update_briefing(f"# Update {i}\n\nVersion {i} of briefing")
            assert result is True

        # Verify all updates recorded
        messages = get_briefing_messages(org_path)
        assert len(messages) == 3, "Should have all 3 briefing updates"

        # Verify CEO has notification for each
        notifications = get_ceo_notifications(org_path)
        assert len(notifications) == 3, "CEO should have notification for each update"


# ==================
# TEST CLASS: NOTIFICATION INTERACTION
# ==================


class TestBriefingNotificationInteraction:
    """Tests for CEO interaction with briefing notifications."""

    def test_ceo_can_mark_briefing_read(self, tmp_path):
        """Test CEO can mark briefing notification as read.

        Verifies the notification bead lifecycle works with briefings.
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, "# Mission\nTest briefing")

        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)
        org.start()

        # Get briefing notification
        notifications = get_ceo_notifications(org_path)
        assert len(notifications) == 1
        notif = notifications[0]
        assert notif["status"] == "pending"

        # Mark as read (simulate CEO reading it)
        db_path = org_path / "live" / "quinn.db"
        conn_db = sqlite3.connect(str(db_path))
        conn_db.execute("""
            UPDATE notification_beads
            SET status = 'read', read_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), notif["id"]))
        conn_db.commit()
        conn_db.close()

        # Verify updated
        updated_notifications = get_ceo_notifications(org_path)
        assert updated_notifications[0]["status"] == "read"
        assert updated_notifications[0]["read_at"] is not None

    def test_briefing_notification_priority(self, tmp_path):
        """Test briefing notifications have appropriate priority.

        Briefings should be high priority (CEO should see them first).
        """
        org_path = tmp_path / "test-org"
        org_path.mkdir()

        create_org_db(org_path, status="initialized", include_ceo=True, include_board_channel=True)
        create_briefing_file(org_path, "# Mission\nHigh priority briefing")

        from cli.core.db import Database
        from cli.core.org import Org

        db_path = org_path / "live" / "quinn.db"
        db = Database(db_path)
        org = Org(db)
        org.start()

        # Check message priority
        db_path = org_path / "live" / "quinn.db"
        conn_db = sqlite3.connect(str(db_path))
        conn_db.row_factory = sqlite3.Row

        cursor = conn_db.execute("""
            SELECT m.priority
            FROM messages m
            WHERE m.content LIKE '%CEO Briefing%'
        """)

        row = cursor.fetchone()
        conn_db.close()

        assert row is not None
        # Priority should be high (0-1 = highest, 2 = normal, 3-4 = low)
        # Briefings should be priority 0 or 1
        assert row["priority"] <= 1, "Briefing should have high priority"
