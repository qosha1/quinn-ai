"""Tests for escalation monitoring system (GAP 4)."""

import tempfile
import time
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from core.escalation_monitor import EscalationMonitor
from core.db import init_database
from core.constants import (
    DEFAULT_ESCALATION_TIMEOUT_CEO,
    DEFAULT_ESCALATION_TIMEOUT_MANAGER,
    DEFAULT_ESCALATION_TIMEOUT_WORKER,
)


@pytest.fixture
def temp_org_dir():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / "live").mkdir(parents=True)
        (org_path / ".beads").mkdir(parents=True)
        yield org_path


@pytest.fixture
def test_db(temp_org_dir):
    """Create a test database with schema v19."""
    db_path = temp_org_dir / "live" / "quinn.db"
    db = init_database(db_path)

    # Run migration to v19
    from core.db.migrations import migrate_database
    from core.constants import DB_SCHEMA_VERSION

    # Get current version from config
    current_version_row = db.fetchone("SELECT value FROM config WHERE key = 'schema_version'")
    if current_version_row:
        current_version = int(current_version_row["value"])
    else:
        current_version = 18  # Assume v18 if not set

    # Migrate to current schema version (v19)
    if current_version < DB_SCHEMA_VERSION:
        migrate_database(db, current_version, DB_SCHEMA_VERSION)

    # Create a test worker
    from core.org import Org
    org = Org(db)
    ceo = org.init("TestCEO", "CEO")

    yield db
    db.close()


def test_escalation_monitor_init(temp_org_dir):
    """Test escalation monitor initialization."""
    monitor = EscalationMonitor(temp_org_dir, poll_interval=1.0)
    
    assert monitor.org_path == temp_org_dir
    assert monitor.poll_interval == 1.0
    assert not monitor.is_running()


def test_escalation_monitor_start_stop(temp_org_dir):
    """Test starting and stopping the escalation monitor."""
    monitor = EscalationMonitor(temp_org_dir, poll_interval=0.1)
    
    # Start monitor
    monitor.start()
    assert monitor.is_running()
    
    # Wait a bit to ensure it's running
    time.sleep(0.2)
    assert monitor.is_running()
    
    # Stop monitor
    monitor.stop(timeout=2.0)
    assert not monitor.is_running()


def test_escalation_monitor_double_start(temp_org_dir, test_db):
    """Test that starting an already running monitor is a no-op."""
    monitor = EscalationMonitor(temp_org_dir, poll_interval=0.1)
    
    monitor.start()
    assert monitor.is_running()
    
    # Try to start again
    monitor.start()  # Should log warning but not crash
    assert monitor.is_running()
    
    monitor.stop()


def test_get_timeout_for_role_ceo(temp_org_dir):
    """Test timeout calculation for CEO."""
    monitor = EscalationMonitor(temp_org_dir)
    
    timeout = monitor._get_timeout_for_role("CEO", manager_id=None)
    assert timeout == DEFAULT_ESCALATION_TIMEOUT_CEO


def test_get_timeout_for_role_manager(temp_org_dir):
    """Test timeout calculation for manager."""
    monitor = EscalationMonitor(temp_org_dir)
    
    timeout = monitor._get_timeout_for_role("Director", manager_id=None)
    assert timeout == DEFAULT_ESCALATION_TIMEOUT_MANAGER


def test_get_timeout_for_role_worker(temp_org_dir):
    """Test timeout calculation for regular worker."""
    monitor = EscalationMonitor(temp_org_dir)
    
    timeout = monitor._get_timeout_for_role("Engineer", manager_id="manager-123")
    assert timeout == DEFAULT_ESCALATION_TIMEOUT_WORKER


def test_update_worker_activity(temp_org_dir, test_db):
    """Test updating worker activity timestamp."""
    monitor = EscalationMonitor(temp_org_dir)
    
    # Get test worker
    ceo_row = test_db.fetchone("SELECT id FROM workers LIMIT 1")
    worker_id = ceo_row["id"]
    
    # Update activity
    monitor.update_worker_activity(worker_id)
    
    # Verify escalation state was created/updated
    state_row = test_db.fetchone(
        "SELECT * FROM worker_escalation_state WHERE worker_id = ?",
        (worker_id,)
    )
    
    assert state_row is not None
    assert state_row["current_state"] == "normal"
    assert state_row["last_activity_at"] is not None


def test_escalation_state_table_exists(test_db):
    """Test that escalation state table was created by migration."""
    # Query the table
    result = test_db.fetchall("SELECT * FROM worker_escalation_state")
    
    # Should exist and be empty initially
    assert result is not None
    assert len(result) == 0


def test_escalation_state_has_correct_columns(test_db):
    """Test that escalation state table has all required columns."""
    # Get table info
    result = test_db.fetchall("PRAGMA table_info(worker_escalation_state)")
    
    column_names = {row["name"] for row in result}
    
    required_columns = {
        "worker_id",
        "current_state",
        "last_activity_at",
        "idle_since",
        "escalation_created_at",
        "escalation_id",
        "escalation_target_id",
        "updated_at",
    }
    
    assert required_columns.issubset(column_names)


def test_escalation_state_has_indexes(test_db):
    """Test that escalation state indexes were created."""
    # Get indexes
    result = test_db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='worker_escalation_state'"
    )
    
    index_names = {row["name"] for row in result}
    
    # Should have at least these indexes
    expected_indexes = {
        "idx_escalation_state_worker",
        "idx_escalation_state_status",
        "idx_escalation_state_idle_since",
    }
    
    assert expected_indexes.issubset(index_names)


def test_escalation_state_check_constraint(test_db):
    """Test that escalation state CHECK constraint works."""
    # Try to insert invalid state
    with pytest.raises(Exception):  # Should be OperationalError
        test_db.execute(
            """INSERT INTO worker_escalation_state
               (worker_id, current_state, last_activity_at)
               VALUES ('test', 'invalid_state', datetime('now'))"""
        )


def test_monitor_initializes_escalation_state(temp_org_dir, test_db):
    """Test that monitor initializes escalation state for workers."""
    monitor = EscalationMonitor(temp_org_dir, poll_interval=0.1)
    
    # Get test worker
    ceo_row = test_db.fetchone("SELECT id FROM workers LIMIT 1")
    worker_id = ceo_row["id"]
    
    # Start monitor briefly
    monitor.start()
    time.sleep(0.3)  # Give it time to run one check
    monitor.stop()
    
    # Check that escalation state was initialized
    state_row = test_db.fetchone(
        "SELECT * FROM worker_escalation_state WHERE worker_id = ?",
        (worker_id,)
    )
    
    assert state_row is not None
    assert state_row["current_state"] in ["normal", "idle_warning", "escalated_pending"]
