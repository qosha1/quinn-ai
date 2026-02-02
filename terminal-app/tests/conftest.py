"""Shared test fixtures and utilities for board UI tests.

This module provides a centralized location for common test fixtures,
particularly database setup with the complete production schema.
"""

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest


def get_production_schema() -> str:
    """Get the complete production database schema.

    Filters out sqlite_sequence table which is auto-managed by SQLite.

    Returns:
        SQL schema string
    """
    schema_file = Path(__file__).parent / "fixtures" / "production_schema.sql"
    schema = schema_file.read_text()

    # Filter out sqlite_sequence (reserved internal table)
    lines = schema.split('\n')
    filtered_lines = [line for line in lines if 'sqlite_sequence' not in line]
    return '\n'.join(filtered_lines)


def create_test_org_db(
    org_path: Path,
    org_name: str = "test-org",
    status: str = "initialized",
    include_ceo: bool = True,
    ceo_name: str = "TestCEO",
    include_board_channel: bool = True,
) -> Path:
    """Create a complete test org database with production schema.

    This is the canonical way to create test databases. It uses the actual
    production schema to avoid schema drift issues.

    Args:
        org_path: Path to org folder
        org_name: Organization name
        status: Org status ('uninitialized', 'initialized', 'running', 'stopped')
        include_ceo: Whether to create CEO worker
        ceo_name: Name for CEO worker
        include_board_channel: Whether to create board-channel

    Returns:
        Path to created database
    """
    live_path = org_path / "live"
    live_path.mkdir(parents=True, exist_ok=True)

    db_path = live_path / "quinn.db"
    conn = sqlite3.connect(str(db_path))

    # Apply production schema
    schema = get_production_schema()
    conn.executescript(schema)

    now = datetime.now()

    # Insert org state
    ceo_id = "worker-ceo" if include_ceo else None
    started_at = now.isoformat() if status == "running" else None

    conn.execute("""
        INSERT INTO org_state (id, name, status, ceo_worker_id, started_at)
        VALUES ('default', ?, ?, ?, ?)
    """, (org_name, status, ceo_id, started_at))

    # Create executive team and CEO if requested
    if include_ceo:
        conn.execute(
            "INSERT INTO teams (id, name) VALUES ('team-exec', 'Executive')"
        )
        conn.execute("""
            INSERT INTO workers (id, name, role, team_id, manager_id, status, cost, created_at)
            VALUES ('worker-ceo', ?, 'CEO', 'team-exec', NULL, 'pending', 100, ?)
        """, (ceo_name, now.isoformat()))

        # CEO session (optional, based on status)
        if status == "running":
            conn.execute("""
                INSERT INTO sessions (id, worker_id, provider, command, tmux_session_name, state)
                VALUES ('session-ceo', 'worker-ceo', 'claude_code', 'claude-code', 'qn-worker-ceo', 'idle')
            """)

    # Create board-channel if requested
    if include_board_channel:
        conn.execute(
            "INSERT INTO channels (id, name, type) VALUES ('ch-board', 'board-channel', 'topic')"
        )

        # Subscribe CEO to board-channel
        if include_ceo:
            conn.execute("""
                INSERT INTO channel_subscriptions (channel_id, worker_id, subscribed_at)
                VALUES ('ch-board', 'worker-ceo', ?)
            """, (now.isoformat(),))

    conn.commit()
    conn.close()

    return db_path


def add_test_messages(
    db_path: Path,
    channel_name: str,
    messages: list[dict],
) -> None:
    """Add test messages to a channel.

    Args:
        db_path: Path to database
        channel_name: Name of channel
        messages: List of message dicts with keys: from_worker_id, content, priority
    """
    conn = sqlite3.connect(str(db_path))

    # Get or create channel
    cursor = conn.execute("SELECT id FROM channels WHERE name = ?", (channel_name,))
    row = cursor.fetchone()
    if row:
        channel_id = row[0]
    else:
        channel_id = f"ch-{channel_name}"
        conn.execute(
            "INSERT INTO channels (id, name, type) VALUES (?, ?, ?)",
            (channel_id, channel_name, 'topic')
        )

    # Add messages
    now = datetime.now()
    for i, msg in enumerate(messages):
        msg_id = f"msg-{channel_name}-{i}"
        conn.execute("""
            INSERT INTO messages (id, channel_id, from_worker_id, content, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            msg_id,
            channel_id,
            msg.get("from_worker_id", "worker-ceo"),
            msg["content"],
            msg.get("priority", 2),
            now.isoformat(),
        ))

        # Create notification if message is unread
        if msg.get("is_unread", False):
            conn.execute("""
                INSERT INTO notification_beads (id, worker_id, message_id, channel_id, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (f"notif-{msg_id}", msg.get("from_worker_id", "worker-ceo"), msg_id, channel_id))

    conn.commit()
    conn.close()


@pytest.fixture
def test_org_with_ceo(tmp_path):
    """Fixture: Create a test org with CEO."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()
    db_path = create_test_org_db(org_path, include_ceo=True)
    return org_path, db_path


@pytest.fixture
def test_org_running(tmp_path):
    """Fixture: Create a running test org with CEO."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()
    db_path = create_test_org_db(org_path, status="running", include_ceo=True)
    return org_path, db_path


@pytest.fixture
def test_org_with_messages(tmp_path):
    """Fixture: Create a test org with CEO and sample messages."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()
    db_path = create_test_org_db(org_path, include_ceo=True, include_board_channel=True)

    # Add sample messages
    add_test_messages(db_path, "board-channel", [
        {"from_worker_id": "worker-ceo", "content": "Test message 1", "priority": 2},
        {"from_worker_id": "worker-ceo", "content": "Test message 2", "priority": 3, "is_unread": True},
    ])

    return org_path, db_path
