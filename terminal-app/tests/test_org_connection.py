"""Tests for OrgConnection implementation.

Tests real SQLite connection and data retrieval from running orgs.
"""

import pytest
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from board_ui.services.org_connection import (
    QuinnAIOrgConnection,
    OrgConnectionError,
    OrgNotFound,
    DatabaseNotFound,
)
from board_ui.interfaces.org_connection import OrgStatus, WorkerStatus, SessionState


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
        return cursor

    def close(self):
        self.connection.close()


@pytest.fixture
def temp_org_with_db():
    """Create a temporary org directory with a fully populated database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org"
        org_path.mkdir()
        live_path = org_path / "live"
        live_path.mkdir()

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

        # Insert test data
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
            INSERT INTO sessions VALUES
            ('session-ceo', 'worker-ceo', 'running', 'org-test-org-ceo')
        """)
        conn.execute("""
            INSERT INTO sessions VALUES
            ('session-dev1', 'worker-dev1', 'idle', 'org-test-org-dev1')
        """)

        conn.execute("INSERT INTO channels VALUES ('ch-esc', 'escalations')")
        conn.execute("""
            INSERT INTO messages VALUES
            ('msg-1', 'ch-esc', NULL, NULL, 'worker-dev1', 'Need help with API design', 3, 'normal', ?)
        """, (now.isoformat(),))
        conn.execute("""
            INSERT INTO notification_beads VALUES ('nb-1', 'msg-1', 'pending', NULL)
        """)

        conn.execute("""
            INSERT INTO okrs VALUES
            ('okr-1', 'Q1 Goals', 'Company objectives', 'worker-ceo', 'active', NULL, '[]', NULL, ?)
        """, (now.isoformat(),))

        conn.commit()
        conn.close()

        yield org_path, db_path


class TestOrgConnection:
    """Tests for OrgConnection implementation."""

    def test_connect_to_org(self, temp_org_with_db):
        """Should connect to an org's SQLite database."""
        org_path, db_path = temp_org_with_db

        # Use database_factory for dependency injection
        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)

        assert conn.is_connected is True
        # Compare resolved paths (macOS /var -> /private/var symlink)
        assert conn.org_path.resolve() == org_path.resolve()

        conn.close()

    def test_connect_to_nonexistent_org_raises(self):
        """Should raise OrgNotFound for nonexistent path."""
        with pytest.raises(OrgNotFound):
            QuinnAIOrgConnection(Path("/nonexistent/org"))

    def test_connect_to_org_without_db_raises(self):
        """Should raise DatabaseNotFound for org without quinn.db."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir) / "empty-org"
            org_path.mkdir()

            with pytest.raises(DatabaseNotFound):
                QuinnAIOrgConnection(org_path)

    def test_get_org_info(self, temp_org_with_db):
        """Should retrieve org status and metrics."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)
        info = conn.get_org_info()

        assert info.name == "test-org"
        assert info.status == OrgStatus.RUNNING
        assert info.ceo_worker_id == "worker-ceo"
        assert info.worker_count == 2
        assert info.active_session_count >= 0

        conn.close()

    def test_get_workers(self, temp_org_with_db):
        """Should retrieve all workers with status."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)
        workers = conn.get_workers()

        assert len(workers) == 2
        ceo = next((w for w in workers if w.is_ceo), None)
        assert ceo is not None
        assert ceo.name == "Alice"
        assert ceo.role == "CEO"

        conn.close()

    def test_get_ceo(self, temp_org_with_db):
        """Should retrieve CEO worker specifically."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)
        ceo = conn.get_ceo()

        assert ceo is not None
        assert ceo.id == "worker-ceo"
        assert ceo.is_ceo is True
        assert ceo.tmux_session_name == "org-test-org-ceo"

        conn.close()

    def test_get_board_messages(self, temp_org_with_db):
        """Should retrieve messages escalated to board."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)
        messages = conn.get_board_messages()

        assert len(messages) == 1
        assert messages[0].content == "Need help with API design"
        assert messages[0].from_worker_name == "Bob"

        conn.close()

    def test_get_unread_count(self, temp_org_with_db):
        """Should count unread messages correctly."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)
        count = conn.get_unread_count()

        assert count == 1

        conn.close()

    def test_mark_message_read(self, temp_org_with_db):
        """Should mark message as read."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)

        # Get initial unread count
        initial_count = conn.get_unread_count()
        assert initial_count == 1

        # Mark message as read
        result = conn.mark_message_read("msg-1")
        assert result is True

        # Verify count decreased
        new_count = conn.get_unread_count()
        assert new_count == 0

        conn.close()

    def test_get_okrs(self, temp_org_with_db):
        """Should retrieve OKRs in hierarchy order."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)
        okrs = conn.get_okrs()

        assert len(okrs) == 1
        assert okrs[0].title == "Q1 Goals"
        assert okrs[0].owner_name == "Alice"

        conn.close()

    def test_context_manager(self, temp_org_with_db):
        """Should work as context manager for cleanup."""
        org_path, db_path = temp_org_with_db

        with QuinnAIOrgConnection(org_path, database_factory=MockDatabase) as conn:
            assert conn.is_connected is True
            info = conn.get_org_info()
            assert info.status == OrgStatus.RUNNING

        # After exiting context, connection should be closed
        # (internal state, not easily testable without accessing private attr)

    def test_get_worker_by_id(self, temp_org_with_db):
        """Should retrieve specific worker by ID."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)
        worker = conn.get_worker("worker-dev1")

        assert worker is not None
        assert worker.name == "Bob"
        assert worker.role == "Developer"
        assert worker.is_ceo is False

        conn.close()

    def test_get_worker_returns_none_for_invalid_id(self, temp_org_with_db):
        """Should return None for invalid worker ID."""
        org_path, db_path = temp_org_with_db

        conn = QuinnAIOrgConnection(org_path, database_factory=MockDatabase)
        worker = conn.get_worker("nonexistent-worker")

        assert worker is None

        conn.close()
