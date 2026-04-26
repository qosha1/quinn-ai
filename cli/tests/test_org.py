"""
Unit tests for Org lifecycle state machine.
"""

import tempfile
from pathlib import Path

import pytest

from cli.core.db import init_database
from cli.core.org import Org
from shared import (
    InvalidOrgTransition,
    OrgNotInitialized,
    ORG_TRANSITIONS,
)


@pytest.fixture
def db():
    """Create test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "quinn.db"
        database = init_database(db_path)
        yield database
        database.close()


@pytest.fixture
def org(db):
    """Get Org instance."""
    return Org.load(db)


class TestOrgCreation:
    """Test Org instance creation."""

    def test_load_org(self, db):
        """Should load org from database."""
        org = Org.load(db)
        assert org.status == "uninitialized"

    def test_initial_status(self, org):
        """New org should be uninitialized."""
        assert org.status == "uninitialized"


class TestOrgProperties:
    """Test org property access."""

    def test_status_property(self, org):
        """Should expose org status."""
        assert org.status == "uninitialized"

    def test_ceo_worker_id_uninitialized(self, org):
        """Uninitialized org has no CEO."""
        assert org.ceo_worker_id is None

    def test_ceo_uninitialized(self, org):
        """Uninitialized org returns None for CEO."""
        assert org.ceo is None

    def test_is_operational_uninitialized(self, org):
        """Uninitialized org is not operational."""
        assert not org.is_operational

    def test_started_at_uninitialized(self, org):
        """Uninitialized org has no start time."""
        assert org.started_at is None


class TestOrgInit:
    """Test org initialization."""

    def test_init_creates_ceo(self, org):
        """Init should create CEO worker."""
        ceo = org.init("Alice", "Chief Executive")
        assert ceo.name == "Alice"
        assert ceo.role == "Chief Executive"

    def test_init_when_running_raises(self, org):
        """Cannot init when running."""
        org.init("Alice")
        org.start()
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.init("Bob")
        assert exc_info.value.current == "running"
        assert exc_info.value.attempted == "initialized"
        # Error message should list valid transitions
        assert "stopped" in str(exc_info.value)

    def test_init_when_stopped_raises(self, org):
        """Cannot init when stopped (can't reinitialize)."""
        org.init("Alice")
        org.start()
        org.stop()
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.init("Bob")
        assert exc_info.value.current == "stopped"
        assert exc_info.value.attempted == "initialized"
        # Valid transition from stopped is running, not initialized
        assert "running" in str(exc_info.value)

    def test_init_transitions_to_initialized(self, org):
        """Init should transition to initialized."""
        org.init("Alice")
        assert org.status == "initialized"

    def test_init_sets_ceo_worker_id(self, org):
        """Init should set ceo_worker_id."""
        ceo = org.init("Alice")
        assert org.ceo_worker_id == ceo.id

    def test_init_ceo_has_no_manager(self, org):
        """CEO should have no manager."""
        ceo = org.init("Alice")
        # Access underlying worker data
        worker_data = org.db.fetchone(
            "SELECT manager_id FROM workers WHERE id = ?",
            (ceo.id,)
        )
        assert worker_data["manager_id"] is None

    def test_init_ceo_is_pending(self, org):
        """CEO should start in pending lifecycle."""
        ceo = org.init("Alice")
        assert ceo.lifecycle_status == "pending"

    def test_init_default_role(self, org):
        """Init should use default CEO role."""
        ceo = org.init("Alice")
        assert ceo.role == "CEO"

    def test_init_creates_team(self, org):
        """Init should create Executive team."""
        org.init("Alice")
        team = org.db.fetchone(
            "SELECT * FROM teams WHERE name = 'Executive'"
        )
        assert team is not None

    def test_init_when_initialized_raises(self, org):
        """Cannot init when already initialized."""
        org.init("Alice")
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.init("Bob")
        assert exc_info.value.current == "initialized"
        assert exc_info.value.attempted == "initialized"


class TestOrgStart:
    """Test org start transitions."""

    def test_start_from_initialized(self, org):
        """Should start from initialized state."""
        org.init("Alice")
        org.start()
        assert org.status == "running"

    def test_start_activates_ceo(self, org):
        """Start should activate CEO worker."""
        org.init("Alice")
        org.start()
        ceo = org.ceo
        assert ceo.lifecycle_status == "active"

    def test_start_sets_started_at(self, org):
        """Start should set started_at timestamp."""
        org.init("Alice")
        org.start()
        assert org.started_at is not None

    def test_start_from_stopped(self, org):
        """Should resume from stopped state."""
        org.init("Alice")
        org.start()
        org.stop()
        org.start()
        assert org.status == "running"

    def test_start_when_uninitialized_raises(self, org):
        """Cannot start when uninitialized."""
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.start()
        assert exc_info.value.current == "uninitialized"

    def test_start_when_running_raises(self, org):
        """Cannot start when already running (double start)."""
        org.init("Alice")
        org.start()
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.start()
        assert exc_info.value.current == "running"
        assert exc_info.value.attempted == "running"
        # Error message should list valid transitions
        assert "stopped" in str(exc_info.value)


class TestOrgStop:
    """Test org stop transitions."""

    def test_stop_from_running(self, org):
        """Should stop from running state."""
        org.init("Alice")
        org.start()
        org.stop()
        assert org.status == "stopped"

    def test_stop_sets_stopped_at(self, org):
        """Stop should set stopped_at timestamp."""
        org.init("Alice")
        org.start()
        org.stop()
        assert org.stopped_at is not None

    def test_stop_when_initialized_raises(self, org):
        """Cannot stop when not running."""
        org.init("Alice")
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.stop()
        assert exc_info.value.current == "initialized"

    def test_stop_when_stopped_raises(self, org):
        """Cannot stop when already stopped (double stop)."""
        org.init("Alice")
        org.start()
        org.stop()
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.stop()
        assert exc_info.value.current == "stopped"
        assert exc_info.value.attempted == "stopped"
        # Error message should list valid transitions
        assert "running" in str(exc_info.value)

    def test_stop_when_uninitialized_raises(self, org):
        """Cannot stop when uninitialized."""
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.stop()
        assert exc_info.value.current == "uninitialized"
        assert exc_info.value.attempted == "stopped"
        # Valid transition from uninitialized is initialized
        assert "initialized" in str(exc_info.value)


class TestOrgQueryHelpers:
    """Test org query helper properties."""

    def test_worker_count_uninitialized(self, org):
        """Uninitialized org has zero workers."""
        assert org.worker_count == 0

    def test_worker_count_after_init(self, org):
        """Initialized org has one worker (CEO)."""
        org.init("Alice")
        assert org.worker_count == 1

    def test_active_session_count_no_sessions(self, org):
        """No sessions initially."""
        org.init("Alice")
        assert org.active_session_count == 0

    def test_active_worker_count_uninitialized(self, org):
        """No active workers when uninitialized."""
        assert org.active_worker_count == 0

    def test_active_worker_count_after_start(self, org):
        """CEO is active after start."""
        org.init("Alice")
        org.start()
        assert org.active_worker_count == 1


class TestOrgIsOperational:
    """Test is_operational property."""

    def test_uninitialized_not_operational(self, org):
        """Uninitialized org is not operational."""
        assert not org.is_operational

    def test_initialized_not_operational(self, org):
        """Initialized org is not operational."""
        org.init("Alice")
        assert not org.is_operational

    def test_running_is_operational(self, org):
        """Running org is operational."""
        org.init("Alice")
        org.start()
        assert org.is_operational

    def test_stopped_not_operational(self, org):
        """Stopped org is not operational."""
        org.init("Alice")
        org.start()
        org.stop()
        assert not org.is_operational


class TestOrgCeoProperty:
    """Test CEO property access."""

    def test_ceo_after_init(self, org):
        """Should get CEO after init."""
        org.init("Alice", "Boss")
        ceo = org.ceo
        assert ceo is not None
        assert ceo.name == "Alice"
        assert ceo.role == "Boss"

    def test_ceo_is_worker_instance(self, org):
        """CEO should be Worker instance."""
        org.init("Alice")
        from cli.core.worker import Worker
        assert isinstance(org.ceo, Worker)


class TestOrgLifecycleCycles:
    """Test complete lifecycle cycles and round trips."""

    def test_full_lifecycle_init_start_stop(self, org):
        """Test complete lifecycle: init -> start -> stop."""
        assert org.status == "uninitialized"
        org.init("Alice")
        assert org.status == "initialized"
        org.start()
        assert org.status == "running"
        org.stop()
        assert org.status == "stopped"

    def test_stop_start_cycle(self, org):
        """Test stop/start cycling multiple times."""
        org.init("Alice")
        org.start()
        # Cycle 1
        org.stop()
        assert org.status == "stopped"
        org.start()
        assert org.status == "running"
        # Cycle 2
        org.stop()
        assert org.status == "stopped"
        org.start()
        assert org.status == "running"
        # Cycle 3
        org.stop()
        assert org.status == "stopped"

    def test_multiple_start_from_stopped(self, org):
        """Should be able to start multiple times from stopped."""
        org.init("Alice")
        org.start()
        org.stop()
        # First restart
        org.start()
        assert org.status == "running"
        assert org.is_operational
        org.stop()
        # Second restart
        org.start()
        assert org.status == "running"
        assert org.is_operational


class TestOrgTransitionErrorMessages:
    """Test error messages for invalid transitions."""

    def test_error_contains_current_state(self, org):
        """Error message should contain current state."""
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.start()  # Can't start uninitialized
        assert "uninitialized" in str(exc_info.value)

    def test_error_contains_attempted_state(self, org):
        """Error message should contain attempted state."""
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.start()  # Can't start uninitialized
        assert "running" in str(exc_info.value)

    def test_error_contains_valid_transitions(self, org):
        """Error message should contain valid transitions."""
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.start()  # Can't start uninitialized
        # Valid transition from uninitialized is initialized
        assert "initialized" in str(exc_info.value)

    def test_error_attributes_accessible(self, org):
        """Exception attributes should be accessible."""
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.start()
        exc = exc_info.value
        assert exc.current == "uninitialized"
        assert exc.attempted == "running"
        assert exc.valid == ["initialized"]

    def test_error_valid_list_from_stopped(self, org):
        """Error from stopped should list running as valid."""
        org.init("Alice")
        org.start()
        org.stop()
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.stop()  # Can't double stop
        assert exc_info.value.valid == ["running"]

    def test_error_valid_list_from_running(self, org):
        """Error from running should list stopped as valid."""
        org.init("Alice")
        org.start()
        with pytest.raises(InvalidOrgTransition) as exc_info:
            org.start()  # Can't double start
        assert exc_info.value.valid == ["stopped"]


class TestTransitionMaps:
    """Test transition map constants."""

    def test_all_states_have_transitions(self):
        """All org states should have transitions defined."""
        states = ["uninitialized", "initialized", "running", "stopped"]
        for state in states:
            assert state in ORG_TRANSITIONS

    def test_uninitialized_transitions(self):
        """Uninitialized can only go to initialized."""
        assert ORG_TRANSITIONS["uninitialized"] == ["initialized"]

    def test_initialized_transitions(self):
        """Initialized can only go to running."""
        assert ORG_TRANSITIONS["initialized"] == ["running"]

    def test_running_transitions(self):
        """Running can only go to stopped."""
        assert ORG_TRANSITIONS["running"] == ["stopped"]

    def test_stopped_transitions(self):
        """Stopped can only go back to running."""
        assert ORG_TRANSITIONS["stopped"] == ["running"]


class TestRefresh:
    """Test state refresh functionality."""

    def test_refresh_updates_state(self, org):
        """Refresh should update cached state."""
        org.init("Alice")
        # Force load state
        _ = org.status
        assert org._state_data.status == "initialized"
        # Manually update database
        org.db.execute(
            "UPDATE org_state SET status = 'running' WHERE id = 'default'"
        )
        org.db.connection.commit()
        # Cached state is still initialized
        assert org._state_data.status == "initialized"
        # Refresh updates it
        org.refresh()
        assert org.status == "running"


class TestOrgChannelAutoCreation:
    """Test automatic channel creation during org init."""

    def test_init_creates_general_channel(self, org):
        """Init should create general channel for org-wide announcements."""
        org.init("Alice")
        channel = org.db.fetchone(
            "SELECT * FROM channels WHERE name = 'general'"
        )
        assert channel is not None
        assert channel["type"] == "topic"
        assert channel["team_id"] is None  # org-wide

    def test_init_creates_escalations_channel(self, org):
        """Init should create board-channel for board communications."""
        org.init("Alice")
        channel = org.db.fetchone(
            "SELECT * FROM channels WHERE name = 'board-channel'"
        )
        assert channel is not None
        assert channel["type"] == "topic"
        assert channel["team_id"] is None  # org-wide

    def test_init_subscribes_ceo_to_general(self, org):
        """Init should subscribe CEO to general channel."""
        ceo = org.init("Alice")
        general = org.db.fetchone(
            "SELECT * FROM channels WHERE name = 'general'"
        )
        subscription = org.db.fetchone(
            "SELECT * FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?",
            (general["id"], ceo.id)
        )
        assert subscription is not None

    def test_init_subscribes_ceo_to_escalations(self, org):
        """Init should subscribe CEO to board-channel."""
        ceo = org.init("Alice")
        board_channel = org.db.fetchone(
            "SELECT * FROM channels WHERE name = 'board-channel'"
        )
        subscription = org.db.fetchone(
            "SELECT * FROM channel_subscriptions WHERE channel_id = ? AND worker_id = ?",
            (board_channel["id"], ceo.id)
        )
        assert subscription is not None

    def test_init_creates_executive_team_channel(self, org):
        """Init should create channel for Executive team."""
        org.init("Alice")
        team = org.db.fetchone(
            "SELECT * FROM teams WHERE name = 'Executive'"
        )
        channel = org.db.fetchone(
            "SELECT * FROM channels WHERE team_id = ? AND type = 'team'",
            (team["id"],)
        )
        assert channel is not None
        assert channel["name"] == "executive"  # lowercase team name
