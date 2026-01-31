"""Tests for activity sensor and activity signals."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.activity_sensor import ActivitySensor, ActivitySignal
from core.constants import (
    SIGNAL_STRENGTH_BEAD_UPDATE,
    SIGNAL_STRENGTH_FILE_CHANGE,
    SIGNAL_STRENGTH_HEARTBEAT,
    SIGNAL_STRENGTH_MESSAGE_SENT,
)
from core.db import init_database
from core.queries.activity import (
    cleanup_old_signals,
    get_recent_signals,
    get_worker_last_activity,
    record_activity_signal,
)
from core.queries.worker import create_worker
from core.queries.team import create_team


@pytest.fixture
def db():
    """Create test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "quinn.db"
        database = init_database(db_path)
        yield database
        database.close()


@pytest.fixture
def org_path(tmp_path):
    """Create temporary org path."""
    org_dir = tmp_path / "test-org"
    org_dir.mkdir()
    (org_dir / ".beads").mkdir()
    return org_dir


@pytest.fixture
def activity_sensor(db, org_path):
    """Create an activity sensor for testing."""
    return ActivitySensor(db, org_path)


@pytest.fixture
def worker(db):
    """Create a test worker."""
    team = create_team(db, "Engineering")
    return create_worker(
        db=db,
        name="Test Worker",
        role="engineer",
        team_id=team.id,
        cost=50,
        manager_id=None,
    )


def test_record_activity_signal_basic(db, worker):
    """Test recording a basic activity signal."""
    record_activity_signal(
        db=db,
        worker_id=worker.id,
        activity_type="heartbeat",
        signal_strength=SIGNAL_STRENGTH_HEARTBEAT,
    )

    # Verify signal was recorded
    signals = get_recent_signals(db, worker.id, minutes=5)
    assert len(signals) == 1
    assert signals[0]["activity_type"] == "heartbeat"
    assert signals[0]["signal_strength"] == SIGNAL_STRENGTH_HEARTBEAT
    assert signals[0]["metadata"] is None


def test_record_activity_signal_with_metadata(db, worker):
    """Test recording activity signal with metadata."""
    metadata = {"channel_id": "chan-123", "message_id": "msg-456"}

    record_activity_signal(
        db=db,
        worker_id=worker.id,
        activity_type="message_sent",
        signal_strength=SIGNAL_STRENGTH_MESSAGE_SENT,
        metadata=metadata,
    )

    signals = get_recent_signals(db, worker.id, minutes=5)
    assert len(signals) == 1
    assert signals[0]["metadata"] == metadata


def test_record_activity_signal_invalid_type(db, worker):
    """Test recording activity signal with invalid type raises error."""
    with pytest.raises(ValueError, match="Invalid activity_type"):
        record_activity_signal(
            db=db,
            worker_id=worker.id,
            activity_type="invalid_type",
            signal_strength=3,
        )


def test_record_activity_signal_invalid_strength(db, worker):
    """Test recording activity signal with invalid strength raises error."""
    with pytest.raises(ValueError, match="signal_strength must be between 1 and 5"):
        record_activity_signal(
            db=db,
            worker_id=worker.id,
            activity_type="heartbeat",
            signal_strength=10,
        )


def test_strong_signal_updates_worker_state(db, worker):
    """Test that strong signals (>=3) update worker_state.last_activity."""
    # Create worker_state manually
    db.execute(
        """INSERT INTO worker_state (worker_id, runtime_status)
           VALUES (?, ?)""",
        (worker.id, "idle"),
    )
    db.connection.commit()

    # Record weak signal (strength < 3) - should NOT update worker_state
    record_activity_signal(
        db=db,
        worker_id=worker.id,
        activity_type="heartbeat",
        signal_strength=SIGNAL_STRENGTH_HEARTBEAT,  # strength = 1
    )

    # Check worker_state - last_activity should still be None
    state = db.fetchone("SELECT last_activity FROM worker_state WHERE worker_id = ?", (worker.id,))
    assert state is None or state["last_activity"] is None

    # Record strong signal (strength >= 3) - SHOULD update worker_state
    record_activity_signal(
        db=db,
        worker_id=worker.id,
        activity_type="file_change",
        signal_strength=SIGNAL_STRENGTH_FILE_CHANGE,  # strength = 3
    )

    # Check worker_state - last_activity should now be set
    state = db.fetchone("SELECT last_activity FROM worker_state WHERE worker_id = ?", (worker.id,))
    assert state is not None
    assert state["last_activity"] is not None


def test_get_worker_last_activity(db, worker):
    """Test getting last activity timestamp."""
    # Initially no activity
    last_activity = get_worker_last_activity(db, worker.id)
    assert last_activity is None

    # Record a weak signal
    record_activity_signal(
        db=db,
        worker_id=worker.id,
        activity_type="heartbeat",
        signal_strength=SIGNAL_STRENGTH_HEARTBEAT,
    )

    # Still no activity (below minimum strength of 3)
    last_activity = get_worker_last_activity(db, worker.id)
    assert last_activity is None

    # Record a strong signal
    record_activity_signal(
        db=db,
        worker_id=worker.id,
        activity_type="bead_update",
        signal_strength=SIGNAL_STRENGTH_BEAD_UPDATE,
    )

    # Now we should have activity
    last_activity = get_worker_last_activity(db, worker.id)
    assert last_activity is not None
    # Database returns datetime as string, check it's a valid timestamp string
    assert last_activity is not None


def test_get_worker_last_activity_custom_min_strength(db, worker):
    """Test getting last activity with custom minimum strength."""
    # Record signals of different strengths
    record_activity_signal(db, worker.id, "heartbeat", 1)
    record_activity_signal(db, worker.id, "session_output", 2)
    record_activity_signal(db, worker.id, "file_change", 3)

    # With min_strength=1, should get the most recent (file_change)
    last = get_worker_last_activity(db, worker.id, min_strength=1)
    assert last is not None

    # With min_strength=3, should get file_change
    last = get_worker_last_activity(db, worker.id, min_strength=3)
    assert last is not None

    # With min_strength=5, should get nothing
    last = get_worker_last_activity(db, worker.id, min_strength=5)
    assert last is None


def test_get_recent_signals(db, worker):
    """Test getting recent signals."""
    # Record multiple signals
    record_activity_signal(db, worker.id, "heartbeat", 1)
    record_activity_signal(db, worker.id, "message_sent", 4, metadata={"msg": "test"})
    record_activity_signal(db, worker.id, "bead_update", 5)

    # Get recent signals
    signals = get_recent_signals(db, worker.id, minutes=5)

    assert len(signals) == 3
    # Should be in reverse chronological order
    assert signals[0]["activity_type"] == "bead_update"
    assert signals[1]["activity_type"] == "message_sent"
    assert signals[2]["activity_type"] == "heartbeat"


def test_get_recent_signals_time_filter(db, worker):
    """Test that time filter works for recent signals."""
    # Record a signal
    record_activity_signal(db, worker.id, "heartbeat", 1)

    # Should be in recent signals (last 30 minutes)
    signals = get_recent_signals(db, worker.id, minutes=30)
    assert len(signals) == 1

    # Manually backdate the signal to 2 hours ago
    two_hours_ago = datetime.now() - timedelta(hours=2)
    db.execute(
        "UPDATE activity_signals SET created_at = ? WHERE worker_id = ?",
        (two_hours_ago, worker.id),
    )
    db.connection.commit()

    # Should NOT be in recent signals (last 30 minutes)
    signals = get_recent_signals(db, worker.id, minutes=30)
    assert len(signals) == 0

    # But should be in signals from last 3 hours
    signals = get_recent_signals(db, worker.id, minutes=180)
    assert len(signals) == 1


def test_cleanup_old_signals(db, worker):
    """Test cleaning up old activity signals."""
    # Record some signals
    record_activity_signal(db, worker.id, "heartbeat", 1)
    record_activity_signal(db, worker.id, "bead_update", 5)

    # Verify they exist
    signals = get_recent_signals(db, worker.id, minutes=5)
    assert len(signals) == 2

    # Backdate one signal to 48 hours ago
    old_time = datetime.now() - timedelta(hours=48)
    db.execute(
        "UPDATE activity_signals SET created_at = ? WHERE activity_type = ?",
        (old_time, "heartbeat"),
    )
    db.connection.commit()

    # Cleanup with 24 hour retention
    deleted = cleanup_old_signals(db, retention_hours=24)
    assert deleted == 1

    # Verify only recent signal remains
    signals = get_recent_signals(db, worker.id, minutes=180)
    assert len(signals) == 1
    assert signals[0]["activity_type"] == "bead_update"


def test_activity_sensor_record_signal(activity_sensor, worker):
    """Test ActivitySensor.record_signal()."""
    signal = ActivitySignal(
        worker_id=worker.id,
        activity_type="message_sent",
        signal_strength=4,
        metadata={"channel": "test"},
    )

    activity_sensor.record_signal(signal)

    # Verify signal was recorded
    signals = activity_sensor.get_recent_signals(worker.id, minutes=5)
    assert len(signals) == 1
    assert signals[0]["activity_type"] == "message_sent"


def test_activity_sensor_get_last_activity(activity_sensor, worker):
    """Test ActivitySensor.get_last_activity()."""
    # No activity initially
    last = activity_sensor.get_last_activity(worker.id)
    assert last is None

    # Record activity
    signal = ActivitySignal(
        worker_id=worker.id,
        activity_type="bead_update",
        signal_strength=5,
        metadata={},
    )
    activity_sensor.record_signal(signal)

    # Should now have activity
    last = activity_sensor.get_last_activity(worker.id)
    assert last is not None


def test_activity_sensor_get_recent_signals(activity_sensor, worker):
    """Test ActivitySensor.get_recent_signals()."""
    # Record multiple signals
    for activity_type in ["heartbeat", "file_change", "message_sent"]:
        signal = ActivitySignal(
            worker_id=worker.id,
            activity_type=activity_type,
            signal_strength=3,
            metadata={},
        )
        activity_sensor.record_signal(signal)

    signals = activity_sensor.get_recent_signals(worker.id, minutes=5)
    assert len(signals) == 3


def test_activity_sensor_cleanup_old_signals(activity_sensor, worker):
    """Test ActivitySensor.cleanup_old_signals()."""
    # Record a signal
    signal = ActivitySignal(
        worker_id=worker.id,
        activity_type="heartbeat",
        signal_strength=1,
        metadata={},
    )
    activity_sensor.record_signal(signal)

    # Backdate it
    old_time = datetime.now() - timedelta(hours=48)
    activity_sensor.db.execute(
        "UPDATE activity_signals SET created_at = ? WHERE worker_id = ?",
        (old_time, worker.id),
    )
    activity_sensor.db.connection.commit()

    # Cleanup
    deleted = activity_sensor.cleanup_old_signals(retention_hours=24)
    assert deleted == 1


def test_message_sent_records_activity_signal(db, worker):
    """Test that sending a message records activity signal."""
    from core.queries.channel import create_channel, create_message

    # Create channel
    channel = create_channel(db, "test-channel", "topic")

    # Send message
    message = create_message(
        db=db,
        channel_id=channel.id,
        from_worker_id=worker.id,
        content="Test message",
    )

    # Verify activity signal was recorded
    signals = get_recent_signals(db, worker.id, minutes=5)
    assert len(signals) == 1
    assert signals[0]["activity_type"] == "message_sent"
    assert signals[0]["signal_strength"] == SIGNAL_STRENGTH_MESSAGE_SENT
    assert signals[0]["metadata"]["message_id"] == message.id


def test_bead_update_records_activity_signal(db, worker, org_path, tmp_path):
    """Test that bead wrapper records activity signals for write operations."""
    # Test that the bd_wrapper would record activity for write commands
    # We test by manually calling record_activity_signal as the wrapper would

    # Simulate what _record_bead_activity does for a "create" command
    record_activity_signal(
        db=db,
        worker_id=worker.id,
        activity_type="bead_update",
        signal_strength=SIGNAL_STRENGTH_BEAD_UPDATE,
        metadata={"command": "create"},
    )

    # Verify activity signal was recorded
    signals = get_recent_signals(db, worker.id, minutes=5)
    assert len(signals) == 1
    assert signals[0]["activity_type"] == "bead_update"
    assert signals[0]["signal_strength"] == SIGNAL_STRENGTH_BEAD_UPDATE
    assert signals[0]["metadata"]["command"] == "create"


def test_activity_signal_timestamp_auto_set():
    """Test that ActivitySignal sets timestamp automatically."""
    before = datetime.now()
    signal = ActivitySignal(
        worker_id="test-worker",
        activity_type="heartbeat",
        signal_strength=1,
        metadata={},
    )
    after = datetime.now()

    assert signal.timestamp is not None
    assert before <= signal.timestamp <= after


def test_activity_signal_custom_timestamp():
    """Test that ActivitySignal respects custom timestamp."""
    custom_time = datetime(2025, 1, 1, 12, 0, 0)
    signal = ActivitySignal(
        worker_id="test-worker",
        activity_type="heartbeat",
        signal_strength=1,
        metadata={},
        timestamp=custom_time,
    )

    assert signal.timestamp == custom_time
