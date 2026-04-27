"""Tests for continuation engine.

Tests the graduated worker nudging system that replaces EscalationMonitor.
"""

import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from cli.core.continuation_engine import ContinuationEngine, ContinuationPolicy
from cli.core.db import init_database, open_database, Database
from cli.core.queries.worker import create_worker, create_worker_state
from cli.core.queries.activity import record_activity_signal
from cli.core.constants import (
    CONTINUATION_NUDGE_1_MINUTES,
    CONTINUATION_NUDGE_2_MINUTES,
    CONTINUATION_WARNING_MINUTES,
    CONTINUATION_ESCALATE_MINUTES,
    CONTINUATION_NUDGE_1_MINUTES_CEO,
    CONTINUATION_NUDGE_2_MINUTES_CEO,
    CONTINUATION_WARNING_MINUTES_CEO,
    CONTINUATION_ESCALATE_MINUTES_CEO,
    CONTINUATION_NUDGE_1_MINUTES_MANAGER,
    CONTINUATION_ESCALATE_MINUTES_MANAGER,
    DB_SCHEMA_VERSION,
)


@pytest.fixture
def temp_org_dir():
    """Create temp org directory with database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / "live").mkdir(parents=True)
        (org_path / ".beads").mkdir(parents=True)
        yield org_path


@pytest.fixture
def db(temp_org_dir):
    """Initialize database connection."""
    db_path = temp_org_dir / "live" / "quinn.db"
    db = init_database(db_path)

    # Run migrations to current version
    from cli.core.db.migrations import migrate_database

    current_version_row = db.fetchone("SELECT value FROM config WHERE key = 'schema_version'")
    if current_version_row:
        current_version = int(current_version_row["value"])
        if current_version < DB_SCHEMA_VERSION:
            migrate_database(db, current_version, DB_SCHEMA_VERSION)

    yield db
    db.close()


def create_test_team_and_ceo(db):
    """Helper to create team and CEO for tests."""
    # Create team
    db.execute(
        "INSERT INTO teams (id, name, created_at) VALUES (?, ?, ?)",
        ("team1", "Team 1", datetime.now())
    )
    db.connection.commit()

    # Create CEO
    ceo = create_worker(
        db, name="CEO", role="ceo", team_id="team1", cost=100,
        manager_id=None
    )
    return ceo


def test_continuation_policy_for_worker(db):
    """Test that ContinuationPolicy returns correct intervals for each role."""
    # Regular worker
    policy = ContinuationPolicy.for_worker(is_ceo=False, is_manager=False)
    assert policy.nudge_1_minutes == CONTINUATION_NUDGE_1_MINUTES
    assert policy.nudge_2_minutes == CONTINUATION_NUDGE_2_MINUTES
    assert policy.warning_minutes == CONTINUATION_WARNING_MINUTES
    assert policy.escalate_minutes == CONTINUATION_ESCALATE_MINUTES

    # Manager
    policy = ContinuationPolicy.for_worker(is_ceo=False, is_manager=True)
    assert policy.nudge_1_minutes == CONTINUATION_NUDGE_1_MINUTES_MANAGER
    assert policy.escalate_minutes == CONTINUATION_ESCALATE_MINUTES_MANAGER

    # CEO
    policy = ContinuationPolicy.for_worker(is_ceo=True, is_manager=False)
    assert policy.nudge_1_minutes == CONTINUATION_NUDGE_1_MINUTES_CEO
    assert policy.nudge_2_minutes == CONTINUATION_NUDGE_2_MINUTES_CEO
    assert policy.warning_minutes == CONTINUATION_WARNING_MINUTES_CEO
    assert policy.escalate_minutes == CONTINUATION_ESCALATE_MINUTES_CEO


def test_engine_starts_and_stops(temp_org_dir):
    """Test that continuation engine starts and stops cleanly."""
    engine = ContinuationEngine(temp_org_dir, poll_interval=1.0)

    assert not engine.is_running()

    engine.start()
    assert engine.is_running()

    time.sleep(0.5)  # Let it run briefly

    engine.stop(timeout=2.0)
    assert not engine.is_running()


def test_engine_checks_workers_on_schedule(temp_org_dir, db):
    """Test that engine checks workers periodically."""
    # Create team and CEO
    ceo = create_test_team_and_ceo(db)

    # Create active worker
    worker = create_worker(
        db, name="Alice", role="engineer", team_id="team1", cost=50,
        manager_id=ceo.id
    )
    create_worker_state(db, worker.id)
    db.execute(
        "UPDATE workers SET status = 'active' WHERE id = ?",
        (worker.id,)
    )
    db.connection.commit()

    # Record activity 10 minutes ago (should trigger first nudge for workers)
    past = datetime.now() - timedelta(minutes=10)
    record_activity_signal(
        db, worker.id, "bead_update", signal_strength=5,
        metadata={"test": "data"}
    )
    db.execute(
        "UPDATE activity_signals SET created_at = ? WHERE worker_id = ?",
        (past, worker.id)
    )
    db.connection.commit()

    with patch('cli.core.continuation_engine.SessionPrompter') as MockPrompter:
        mock_prompter = Mock()
        MockPrompter.return_value = mock_prompter

        engine = ContinuationEngine(temp_org_dir, poll_interval=0.5)
        engine.start()

        # Wait for at least one check cycle
        time.sleep(1.0)

        engine.stop(timeout=2.0)

        # Verify prompter was created and methods called
        assert MockPrompter.called


def test_graduated_prompts_sent_at_correct_intervals(temp_org_dir, db):
    """Test that graduated prompts are sent at the right idle intervals."""
    # Create team and CEO
    ceo = create_test_team_and_ceo(db)

    # Create worker
    worker = create_worker(
        db, name="Bob", role="engineer", team_id="team1", cost=50,
        manager_id=ceo.id
    )
    create_worker_state(db, worker.id)
    db.execute(
        "UPDATE workers SET status = 'active' WHERE id = ?",
        (worker.id,)
    )
    db.connection.commit()

    with patch('cli.core.continuation_engine.SessionPrompter') as MockPrompter, \
         patch('cli.core.continuation_engine.ActivitySensor') as MockSensor:

        mock_prompter = Mock()
        MockPrompter.return_value = mock_prompter

        mock_sensor = Mock()
        MockSensor.return_value = mock_sensor

        engine = ContinuationEngine(temp_org_dir, poll_interval=0.1)

        # Simulate 6 minutes idle (should trigger soft check)
        idle_time = datetime.now() - timedelta(minutes=6)
        mock_sensor.get_last_activity.return_value = idle_time

        engine._check_all_workers()

        # Should have called soft_check
        assert mock_prompter.send_soft_check.called
        assert not mock_prompter.send_status_request.called
        assert not mock_prompter.send_final_warning.called


def test_escalation_triggered_after_final_timeout(temp_org_dir, db):
    """Test that escalation bead is created after final timeout."""
    # Create team and CEO
    ceo = create_test_team_and_ceo(db)

    # Create worker
    worker = create_worker(
        db, name="Charlie", role="engineer", team_id="team1", cost=50,
        manager_id=ceo.id
    )
    create_worker_state(db, worker.id)
    db.execute(
        "UPDATE workers SET status = 'active' WHERE id = ?",
        (worker.id,)
    )
    db.connection.commit()

    with patch('cli.core.continuation_engine.SessionPrompter') as MockPrompter, \
         patch('cli.core.continuation_engine.ActivitySensor') as MockSensor, \
         patch('cli.core.continuation_engine.run_bd') as mock_run_bd:

        mock_prompter = Mock()
        MockPrompter.return_value = mock_prompter

        mock_sensor = Mock()
        MockSensor.return_value = mock_sensor

        # Mock successful bead creation
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_bd.return_value = mock_result

        engine = ContinuationEngine(temp_org_dir, poll_interval=0.1)

        # Simulate 35 minutes idle (exceeds CONTINUATION_ESCALATE_MINUTES for workers)
        idle_time = datetime.now() - timedelta(minutes=35)
        mock_sensor.get_last_activity.return_value = idle_time

        engine._check_all_workers()

        # Should have called run_bd to create escalation bead
        assert mock_run_bd.called
        args = mock_run_bd.call_args
        assert "--type=ask" in args[0][1]
        assert "--priority=1" in args[0][1]


def test_ceo_gets_longer_timeout(temp_org_dir, db):
    """Test that CEO gets longer timeout before escalation."""
    # Create team and CEO
    ceo = create_test_team_and_ceo(db)
    create_worker_state(db, ceo.id)
    db.execute(
        "UPDATE workers SET status = 'active' WHERE id = ?",
        (ceo.id,)
    )
    db.connection.commit()

    with patch('cli.core.continuation_engine.SessionPrompter') as MockPrompter, \
         patch('cli.core.continuation_engine.ActivitySensor') as MockSensor, \
         patch('cli.core.continuation_engine.run_bd') as mock_run_bd:

        mock_prompter = Mock()
        MockPrompter.return_value = mock_prompter

        mock_sensor = Mock()
        MockSensor.return_value = mock_sensor

        mock_result = Mock()
        mock_result.returncode = 0
        mock_run_bd.return_value = mock_result

        engine = ContinuationEngine(temp_org_dir, poll_interval=0.1)

        # Simulate 35 minutes idle (should NOT escalate CEO yet)
        idle_time = datetime.now() - timedelta(minutes=35)
        mock_sensor.get_last_activity.return_value = idle_time

        engine._check_all_workers()

        # CEO should NOT be escalated at 35 minutes
        assert not mock_run_bd.called

        # But at 65 minutes CEO should be escalated
        idle_time = datetime.now() - timedelta(minutes=65)
        mock_sensor.get_last_activity.return_value = idle_time

        engine._check_all_workers()

        # Now should be escalated
        assert mock_run_bd.called


def test_no_spam_duplicate_prompts(temp_org_dir, db):
    """Test that we don't spam workers with duplicate prompts."""
    # Create team and CEO
    ceo = create_test_team_and_ceo(db)

    # Create worker
    worker = create_worker(
        db, name="Dave", role="engineer", team_id="team1", cost=50,
        manager_id=ceo.id
    )
    create_worker_state(db, worker.id)
    db.execute(
        "UPDATE workers SET status = 'active' WHERE id = ?",
        (worker.id,)
    )
    db.connection.commit()

    with patch('cli.core.continuation_engine.SessionPrompter') as MockPrompter, \
         patch('cli.core.continuation_engine.ActivitySensor') as MockSensor:

        mock_prompter = Mock()
        MockPrompter.return_value = mock_prompter

        mock_sensor = Mock()
        MockSensor.return_value = mock_sensor

        engine = ContinuationEngine(temp_org_dir, poll_interval=0.1)

        # Simulate 6 minutes idle
        idle_time = datetime.now() - timedelta(minutes=6)
        mock_sensor.get_last_activity.return_value = idle_time

        # First check - should send prompt
        engine._check_all_workers()
        assert mock_prompter.send_soft_check.call_count == 1

        # Second check immediately after - should NOT send again
        engine._check_all_workers()
        assert mock_prompter.send_soft_check.call_count == 1  # Still 1

        # Simulate time passing (11 minutes, enough for re-send)
        engine._last_prompts[worker.id]["soft_check"] = datetime.now() - timedelta(minutes=11)

        # Third check - should send again
        engine._check_all_workers()
        assert mock_prompter.send_soft_check.call_count == 2


def test_thread_safe_operation(temp_org_dir):
    """Test that engine handles concurrent operations safely."""
    engine = ContinuationEngine(temp_org_dir, poll_interval=0.1)

    # Start and stop rapidly multiple times
    for _ in range(5):
        engine.start()
        time.sleep(0.05)
        engine.stop(timeout=1.0)

    # Engine should be stopped
    assert not engine.is_running()

    # Should be able to start again
    engine.start()
    assert engine.is_running()
    engine.stop(timeout=1.0)


def test_handles_missing_worker_gracefully(temp_org_dir, db):
    """Test that engine handles missing workers without crashing."""
    # Create team and CEO
    ceo = create_test_team_and_ceo(db)

    # Create worker then delete it (simulate race condition)
    worker = create_worker(
        db, name="Eve", role="engineer", team_id="team1", cost=50,
        manager_id=ceo.id
    )
    create_worker_state(db, worker.id)
    db.execute(
        "UPDATE workers SET status = 'active' WHERE id = ?",
        (worker.id,)
    )
    db.connection.commit()

    with patch('cli.core.continuation_engine.SessionPrompter') as MockPrompter, \
         patch('cli.core.continuation_engine.ActivitySensor') as MockSensor, \
         patch('cli.core.continuation_engine.get_worker') as mock_get_worker:

        mock_prompter = Mock()
        MockPrompter.return_value = mock_prompter

        mock_sensor = Mock()
        MockSensor.return_value = mock_sensor

        # Worker not found
        mock_get_worker.return_value = None

        engine = ContinuationEngine(temp_org_dir, poll_interval=0.1)

        # Simulate escalation time
        idle_time = datetime.now() - timedelta(minutes=35)
        mock_sensor.get_last_activity.return_value = idle_time

        # Should not crash
        engine._check_all_workers()
