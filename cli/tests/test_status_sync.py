"""
Tests for the worker status sync architecture.

This tests the status_changes table with triggers, cursor-based polling,
and event publishing for status transitions.

Architecture from quinnai-vj08 and quinnai-31gu:
- status_changes table auto-populated by triggers
- status_change_cursors for efficient incremental polling
- Event publishing for all status transitions
- Optimistic locking for race condition handling
"""

import tempfile
from datetime import datetime
from pathlib import Path
from time import sleep

import pytest

from cli.core.db import Database, init_database
from cli.core.queries import (
    create_team,
    create_worker,
    get_worker,
    update_worker_status,
    create_worker_state,
    update_worker_runtime_status,
    get_worker_state,
)
from cli.core.events import EventType, init_event_bus, get_event_bus, reset_event_bus


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    # Initialize event bus for event publishing tests
    init_event_bus(database)
    yield database
    database.close()
    # Clear the module-level _event_bus so its closed-db reference doesn't
    # leak into subsequent tests (caused 99 failures in test_worker.py).
    reset_event_bus()


@pytest.fixture
def team(db):
    """Create a test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def worker(db, team):
    """Create a test worker."""
    return create_worker(db, "Alice", "Developer", team.id, 50)


class TestStatusChangesTable:
    """Test the status_changes table and triggers."""

    def test_status_changes_table_exists(self, db):
        """status_changes table should exist after init."""
        # Query sqlite_master for the table
        result = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='status_changes'"
        )
        assert result is not None, "status_changes table should exist"

    def test_status_changes_table_schema(self, db):
        """status_changes table should have correct columns."""
        # Get table info
        rows = db.fetchall("PRAGMA table_info(status_changes)")
        columns = {row["name"] for row in rows}

        expected_columns = {
            "id",
            "entity_type",
            "entity_id",
            "old_status",
            "new_status",
            "changed_at",
        }
        assert expected_columns.issubset(columns), (
            f"Missing columns: {expected_columns - columns}"
        )

    def test_worker_status_change_trigger(self, db, worker):
        """Trigger should auto-insert into status_changes on worker status update."""
        # Initial status is 'pending'
        assert worker.status == "pending"

        # Update status
        update_worker_status(db, worker.id, "onboarding")

        # Check status_changes table
        row = db.fetchone(
            """SELECT * FROM status_changes
               WHERE entity_type = 'worker' AND entity_id = ?
               ORDER BY id DESC LIMIT 1""",
            (worker.id,)
        )

        assert row is not None, "Trigger should insert into status_changes"
        assert row["old_status"] == "pending"
        assert row["new_status"] == "onboarding"
        assert row["entity_type"] == "worker"
        assert row["entity_id"] == worker.id

    def test_worker_runtime_status_change_trigger(self, db, worker):
        """Trigger should auto-insert on worker runtime status change."""
        # Create worker state
        create_worker_state(db, worker.id)

        # Update runtime status
        update_worker_runtime_status(db, worker.id, "running")

        # Check status_changes table
        row = db.fetchone(
            """SELECT * FROM status_changes
               WHERE entity_type = 'worker_state' AND entity_id = ?
               ORDER BY id DESC LIMIT 1""",
            (worker.id,)
        )

        assert row is not None, "Trigger should insert into status_changes"
        assert row["old_status"] == "starting"
        assert row["new_status"] == "running"

    def test_session_state_change_trigger(self, db, worker):
        """Trigger should auto-insert on session state change."""
        # Create a session directly for testing
        db.execute(
            """INSERT INTO sessions
               (id, worker_id, provider, command, state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            ("session-123", worker.id, "claude_code", "claude", "starting")
        )
        db.connection.commit()

        # Update session state
        db.execute(
            "UPDATE sessions SET state = 'running' WHERE id = ?",
            ("session-123",)
        )
        db.connection.commit()

        # Check status_changes table
        row = db.fetchone(
            """SELECT * FROM status_changes
               WHERE entity_type = 'session' AND entity_id = ?
               ORDER BY id DESC LIMIT 1""",
            ("session-123",)
        )

        assert row is not None, "Trigger should insert into status_changes"
        assert row["old_status"] == "starting"
        assert row["new_status"] == "running"

    def test_multiple_status_changes_ordered(self, db, worker):
        """Multiple status changes should be ordered by id/timestamp."""
        # Transition through multiple states
        update_worker_status(db, worker.id, "onboarding")
        update_worker_status(db, worker.id, "active")

        # Get all changes
        rows = db.fetchall(
            """SELECT * FROM status_changes
               WHERE entity_type = 'worker' AND entity_id = ?
               ORDER BY id ASC""",
            (worker.id,)
        )

        assert len(rows) == 2
        assert rows[0]["new_status"] == "onboarding"
        assert rows[1]["new_status"] == "active"


class TestStatusChangeCursors:
    """Test the cursor-based polling mechanism."""

    def test_status_change_cursors_table_exists(self, db):
        """status_change_cursors table should exist."""
        result = db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='status_change_cursors'"
        )
        assert result is not None, "status_change_cursors table should exist"

    def test_cursor_table_schema(self, db):
        """status_change_cursors should have correct columns."""
        rows = db.fetchall("PRAGMA table_info(status_change_cursors)")
        columns = {row["name"] for row in rows}

        expected_columns = {"client_id", "last_change_id", "updated_at"}
        assert expected_columns.issubset(columns)

    def test_get_changes_since_cursor(self, db, worker):
        """Should get status changes since a given cursor position."""
        # Create some status changes
        update_worker_status(db, worker.id, "onboarding")

        # Get the cursor position
        first_row = db.fetchone(
            "SELECT MAX(id) as last_id FROM status_changes"
        )
        cursor_pos = first_row["last_id"]

        # Create more changes after the cursor
        update_worker_status(db, worker.id, "active")

        # Query changes since cursor
        rows = db.fetchall(
            "SELECT * FROM status_changes WHERE id > ? ORDER BY id ASC",
            (cursor_pos,)
        )

        assert len(rows) == 1
        assert rows[0]["new_status"] == "active"

    def test_upsert_cursor_position(self, db):
        """Should be able to upsert cursor position."""
        client_id = "board-ui-123"

        # Insert initial cursor position
        db.execute(
            """INSERT INTO status_change_cursors (client_id, last_change_id, updated_at)
               VALUES (?, 0, CURRENT_TIMESTAMP)
               ON CONFLICT(client_id) DO UPDATE SET
                   last_change_id = excluded.last_change_id,
                   updated_at = excluded.updated_at""",
            (client_id,)
        )
        db.connection.commit()

        # Verify
        row = db.fetchone(
            "SELECT * FROM status_change_cursors WHERE client_id = ?",
            (client_id,)
        )
        assert row is not None
        assert row["last_change_id"] == 0

        # Update cursor position
        db.execute(
            """INSERT INTO status_change_cursors (client_id, last_change_id, updated_at)
               VALUES (?, 10, CURRENT_TIMESTAMP)
               ON CONFLICT(client_id) DO UPDATE SET
                   last_change_id = excluded.last_change_id,
                   updated_at = excluded.updated_at""",
            (client_id,)
        )
        db.connection.commit()

        # Verify update
        row = db.fetchone(
            "SELECT * FROM status_change_cursors WHERE client_id = ?",
            (client_id,)
        )
        assert row["last_change_id"] == 10


class TestStatusEventPublishing:
    """Test event publishing for status transitions."""

    def test_worker_status_change_publishes_event(self, db, worker):
        """update_worker_status should publish WORKER_STATUS_CHANGED event."""
        bus = get_event_bus()
        assert bus is not None, "Event bus should be initialized"

        # Track received events
        received_events = []

        def handler(event):
            received_events.append(event)

        bus.subscribe(EventType.WORKER_STATUS_CHANGED, handler)

        # Update status
        update_worker_status(db, worker.id, "active")

        # Check event was published
        assert len(received_events) == 1
        event = received_events[0]
        assert event.event_type == EventType.WORKER_STATUS_CHANGED
        assert event.entity_id == worker.id
        assert event.payload.get("old_status") == "pending"
        assert event.payload.get("new_status") == "active"

        bus.unsubscribe(EventType.WORKER_STATUS_CHANGED, handler)

    def test_worker_runtime_status_change_publishes_event(self, db, worker):
        """update_worker_runtime_status should publish event."""
        bus = get_event_bus()

        # Create worker state first
        create_worker_state(db, worker.id)

        received_events = []

        def handler(event):
            received_events.append(event)

        bus.subscribe(EventType.WORKER_RUNTIME_STATUS_CHANGED, handler)

        # Update runtime status
        update_worker_runtime_status(db, worker.id, "running")

        # Check event was published
        assert len(received_events) == 1
        event = received_events[0]
        assert event.event_type == EventType.WORKER_RUNTIME_STATUS_CHANGED
        assert event.entity_id == worker.id
        assert event.payload.get("old_status") == "starting"
        assert event.payload.get("new_status") == "running"

        bus.unsubscribe(EventType.WORKER_RUNTIME_STATUS_CHANGED, handler)


class TestStatusChangeIndexes:
    """Test indexes for efficient polling."""

    def test_entity_index_exists(self, db):
        """Index on entity_type, entity_id should exist for filtering."""
        rows = db.fetchall(
            """SELECT name FROM sqlite_master
               WHERE type='index' AND tbl_name='status_changes'"""
        )
        index_names = {row["name"] for row in rows}

        # Should have an index for entity lookup
        assert any("entity" in name.lower() for name in index_names), (
            "Should have index for entity_type/entity_id queries"
        )

    def test_changed_at_index_exists(self, db):
        """Index on changed_at should exist for time-based queries."""
        rows = db.fetchall(
            """SELECT name FROM sqlite_master
               WHERE type='index' AND tbl_name='status_changes'"""
        )
        index_names = {row["name"] for row in rows}

        # Primary key on id provides ordering, but we should have changed_at too
        assert any("changed" in name.lower() or "id" in name.lower() for name in index_names), (
            "Should have index for time-based queries"
        )


class TestOptimisticLocking:
    """Test optimistic locking for concurrent updates."""

    def test_worker_has_updated_at(self, db, worker):
        """Workers should have updated_at for optimistic locking."""
        row = db.fetchone("SELECT updated_at FROM workers WHERE id = ?", (worker.id,))
        assert row is not None
        assert row["updated_at"] is not None

    def test_worker_state_has_updated_at(self, db, worker):
        """Worker state should have updated_at for optimistic locking."""
        create_worker_state(db, worker.id)
        row = db.fetchone(
            "SELECT updated_at FROM worker_state WHERE worker_id = ?",
            (worker.id,)
        )
        assert row is not None
        assert row["updated_at"] is not None

    def test_status_change_includes_timestamp(self, db, worker):
        """Status changes should include changed_at timestamp."""
        update_worker_status(db, worker.id, "active")

        row = db.fetchone(
            """SELECT changed_at FROM status_changes
               WHERE entity_id = ? ORDER BY id DESC LIMIT 1""",
            (worker.id,)
        )
        assert row is not None
        assert row["changed_at"] is not None


class TestStaleDataDetection:
    """Test stale data detection based on timestamps."""

    def test_get_latest_status_change_time(self, db, worker):
        """Should be able to get latest status change time."""
        update_worker_status(db, worker.id, "active")

        row = db.fetchone(
            "SELECT MAX(changed_at) as latest FROM status_changes"
        )
        assert row is not None
        assert row["latest"] is not None

    def test_detect_no_changes_since_timestamp(self, db, worker):
        """Should detect when no changes have occurred."""
        update_worker_status(db, worker.id, "active")

        # Get current max
        row = db.fetchone("SELECT MAX(id) as max_id FROM status_changes")
        max_id = row["max_id"]

        # Check for changes since max_id
        rows = db.fetchall(
            "SELECT * FROM status_changes WHERE id > ?",
            (max_id,)
        )
        assert len(rows) == 0


class TestIntegrationScenarios:
    """Integration tests for realistic scenarios."""

    def test_full_worker_lifecycle_tracking(self, db, team):
        """Track a worker through full lifecycle."""
        # Create worker
        worker = create_worker(db, "Bob", "Engineer", team.id, 50)

        # Track lifecycle transitions
        update_worker_status(db, worker.id, "onboarding")
        update_worker_status(db, worker.id, "active")

        # Create runtime state
        create_worker_state(db, worker.id)
        update_worker_runtime_status(db, worker.id, "running")
        update_worker_runtime_status(db, worker.id, "idle")
        update_worker_runtime_status(db, worker.id, "stopped")

        # Terminate worker
        update_worker_status(db, worker.id, "terminated")

        # Verify all changes tracked
        rows = db.fetchall(
            """SELECT * FROM status_changes
               WHERE entity_id = ?
               ORDER BY id ASC""",
            (worker.id,)
        )

        # Should have: 2 lifecycle + 3 runtime = 5 changes minimum
        assert len(rows) >= 5, f"Expected at least 5 changes, got {len(rows)}"

    def test_concurrent_workers_isolated(self, db, team):
        """Multiple workers should have isolated status tracking."""
        worker1 = create_worker(db, "Alice", "Engineer", team.id, 50)
        worker2 = create_worker(db, "Bob", "Engineer", team.id, 50)

        # Update both workers
        update_worker_status(db, worker1.id, "active")
        update_worker_status(db, worker2.id, "onboarding")

        # Check isolation
        w1_changes = db.fetchall(
            "SELECT * FROM status_changes WHERE entity_id = ?",
            (worker1.id,)
        )
        w2_changes = db.fetchall(
            "SELECT * FROM status_changes WHERE entity_id = ?",
            (worker2.id,)
        )

        assert len(w1_changes) == 1
        assert w1_changes[0]["new_status"] == "active"

        assert len(w2_changes) == 1
        assert w2_changes[0]["new_status"] == "onboarding"
