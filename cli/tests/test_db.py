"""
Unit tests for database operations.
"""

import tempfile
from pathlib import Path

import pytest

from quinnai.core.db import (
    Database,
    init_database,
    open_database,
    get_org_db_path,
    SCHEMA_VERSION,
)
from quinnai.core.queries import (
    # Org
    get_org_state,
    update_org_status,
    # Teams
    create_team,
    get_team,
    get_team_children,
    get_all_teams,
    # Workers
    create_worker,
    get_worker,
    update_worker_status,
    get_workers_by_status,
    get_workers_by_manager,
    get_team_workers,
    # Worker State
    create_worker_state,
    get_worker_state,
    update_worker_runtime_status,
    record_worker_heartbeat,
    increment_worker_task_count,
    get_workers_by_runtime_status,
    # Channels
    create_channel,
    get_channel,
    subscribe_to_channel,
    unsubscribe_from_channel,
    get_channel_subscribers,
    get_worker_channels,
    # Messages
    create_message,
    get_message,
    get_channel_messages,
    get_thread_messages,
    add_message_ref,
    get_message_refs,
    # Config
    get_config,
    set_config,
)


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    yield database
    database.close()


class TestDatabaseInit:
    """Test database initialization."""

    def test_init_creates_database(self, db_path):
        """Database file should be created on init."""
        db = init_database(db_path)
        assert db_path.exists()
        db.close()

    def test_init_creates_parent_dir(self, db_path):
        """Parent directory should be created if missing."""
        db = init_database(db_path)
        assert db_path.parent.exists()
        db.close()

    def test_init_sets_schema_version(self, db):
        """Schema version should be stored in config."""
        version = get_config(db, "schema_version")
        assert version == str(SCHEMA_VERSION)

    def test_init_creates_default_org_state(self, db):
        """Default org state should be created."""
        state = get_org_state(db)
        assert state is not None
        assert state.status == "uninitialized"


class TestDatabaseOpen:
    """Test opening existing databases."""

    def test_open_existing_database(self, db_path):
        """Should open existing database."""
        db1 = init_database(db_path)
        db1.close()

        db2 = open_database(db_path)
        assert db2 is not None
        db2.close()

    def test_open_nonexistent_raises(self, db_path):
        """Should raise FileNotFoundError for missing db."""
        with pytest.raises(FileNotFoundError):
            open_database(db_path)


class TestOrgStateQueries:
    """Test org state queries."""

    def test_get_org_state(self, db):
        """Should get default org state."""
        state = get_org_state(db)
        assert state is not None
        assert state.id == "default"
        assert state.status == "uninitialized"

    def test_update_org_status_initialized(self, db):
        """Should update to initialized status."""
        update_org_status(db, "initialized")
        state = get_org_state(db)
        assert state.status == "initialized"

    def test_update_org_status_running(self, db):
        """Should update to running status with timestamps."""
        update_org_status(db, "running", ceo_worker_id="ceo-123")
        state = get_org_state(db)
        assert state.status == "running"
        assert state.ceo_worker_id == "ceo-123"
        assert state.started_at is not None

    def test_update_org_status_stopped(self, db):
        """Should update to stopped status with timestamp."""
        update_org_status(db, "running")
        update_org_status(db, "stopped")
        state = get_org_state(db)
        assert state.status == "stopped"
        assert state.stopped_at is not None


class TestTeamQueries:
    """Test team queries."""

    def test_create_team(self, db):
        """Should create a new team."""
        team = create_team(db, "Engineering")
        assert team.name == "Engineering"
        assert team.id.startswith("team-")

    def test_create_team_with_parent(self, db):
        """Should create team with parent."""
        parent = create_team(db, "Engineering")
        child = create_team(db, "Frontend", parent_team_id=parent.id)
        assert child.parent_team_id == parent.id

    def test_get_team(self, db):
        """Should get team by ID."""
        created = create_team(db, "Engineering")
        fetched = get_team(db, created.id)
        assert fetched is not None
        assert fetched.name == "Engineering"

    def test_get_team_not_found(self, db):
        """Should return None for missing team."""
        result = get_team(db, "nonexistent")
        assert result is None

    def test_get_team_children(self, db):
        """Should get child teams."""
        parent = create_team(db, "Engineering")
        child1 = create_team(db, "Frontend", parent_team_id=parent.id)
        child2 = create_team(db, "Backend", parent_team_id=parent.id)

        children = get_team_children(db, parent.id)
        assert len(children) == 2
        child_ids = {c.id for c in children}
        assert child1.id in child_ids
        assert child2.id in child_ids

    def test_get_all_teams(self, db):
        """Should get all teams."""
        create_team(db, "Engineering")
        create_team(db, "Product")
        teams = get_all_teams(db)
        assert len(teams) == 2


class TestWorkerQueries:
    """Test worker queries."""

    @pytest.fixture
    def team(self, db):
        """Create a test team."""
        return create_team(db, "Engineering")

    def test_create_worker(self, db, team):
        """Should create a new worker."""
        worker = create_worker(
            db, name="Alice", role="Developer", team_id=team.id, cost=50
        )
        assert worker.name == "Alice"
        assert worker.role == "Developer"
        assert worker.status == "pending"
        assert worker.cost == 50

    def test_create_worker_with_skills(self, db, team):
        """Should create worker with skills."""
        skills = {"coding": 80, "reasoning": 60}
        worker = create_worker(
            db, name="Alice", role="Developer", team_id=team.id,
            cost=50, skills=skills
        )
        assert worker.skills == skills

    def test_get_worker(self, db, team):
        """Should get worker by ID."""
        created = create_worker(db, "Alice", "Developer", team.id, 50)
        fetched = get_worker(db, created.id)
        assert fetched is not None
        assert fetched.name == "Alice"

    def test_update_worker_status(self, db, team):
        """Should update worker status."""
        worker = create_worker(db, "Alice", "Developer", team.id, 50)
        update_worker_status(db, worker.id, "active")
        fetched = get_worker(db, worker.id)
        assert fetched.status == "active"

    def test_get_workers_by_status(self, db, team):
        """Should get workers by status."""
        w1 = create_worker(db, "Alice", "Developer", team.id, 50)
        w2 = create_worker(db, "Bob", "Developer", team.id, 50)
        update_worker_status(db, w1.id, "active")

        active = get_workers_by_status(db, "active")
        pending = get_workers_by_status(db, "pending")

        assert len(active) == 1
        assert len(pending) == 1
        assert active[0].id == w1.id
        assert pending[0].id == w2.id

    def test_get_workers_by_manager(self, db, team):
        """Should get direct reports."""
        manager = create_worker(db, "Alice", "Manager", team.id, 60)
        report1 = create_worker(db, "Bob", "Developer", team.id, 50, manager_id=manager.id)
        report2 = create_worker(db, "Charlie", "Developer", team.id, 50, manager_id=manager.id)

        reports = get_workers_by_manager(db, manager.id)
        assert len(reports) == 2
        report_ids = {r.id for r in reports}
        assert report1.id in report_ids
        assert report2.id in report_ids

    def test_get_team_workers(self, db, team):
        """Should get workers in team."""
        create_worker(db, "Alice", "Developer", team.id, 50)
        create_worker(db, "Bob", "Developer", team.id, 50)

        workers = get_team_workers(db, team.id)
        assert len(workers) == 2


class TestWorkerStateQueries:
    """Test worker state queries."""

    @pytest.fixture
    def worker(self, db):
        """Create a test worker."""
        team = create_team(db, "Engineering")
        return create_worker(db, "Alice", "Developer", team.id, 50)

    def test_create_worker_state(self, db, worker):
        """Should create worker state."""
        state = create_worker_state(db, worker.id, pid=12345)
        assert state.worker_id == worker.id
        assert state.runtime_status == "starting"
        assert state.pid == 12345

    def test_get_worker_state(self, db, worker):
        """Should get worker state."""
        create_worker_state(db, worker.id)
        state = get_worker_state(db, worker.id)
        assert state is not None
        assert state.worker_id == worker.id

    def test_update_worker_runtime_status(self, db, worker):
        """Should update runtime status."""
        create_worker_state(db, worker.id)
        update_worker_runtime_status(db, worker.id, "running", current_task_id="task-123")
        state = get_worker_state(db, worker.id)
        assert state.runtime_status == "running"
        assert state.current_task_id == "task-123"

    def test_record_worker_heartbeat(self, db, worker):
        """Should update last_activity."""
        create_worker_state(db, worker.id)
        initial = get_worker_state(db, worker.id)
        record_worker_heartbeat(db, worker.id)
        after = get_worker_state(db, worker.id)
        assert after.last_activity >= initial.last_activity

    def test_increment_task_count(self, db, worker):
        """Should increment task counts."""
        create_worker_state(db, worker.id)
        increment_worker_task_count(db, worker.id, completed=True)
        increment_worker_task_count(db, worker.id, completed=False)
        state = get_worker_state(db, worker.id)
        assert state.tasks_completed == 1
        assert state.tasks_failed == 1

    def test_get_workers_by_runtime_status(self, db, worker):
        """Should get workers by runtime status."""
        create_worker_state(db, worker.id)
        update_worker_runtime_status(db, worker.id, "running")
        running = get_workers_by_runtime_status(db, "running")
        assert len(running) == 1
        assert running[0].worker_id == worker.id


class TestChannelQueries:
    """Test channel queries."""

    def test_create_channel(self, db):
        """Should create a channel."""
        channel = create_channel(db, "general", "topic")
        assert channel.name == "general"
        assert channel.type == "topic"

    def test_create_team_channel(self, db):
        """Should create team channel with team_id."""
        team = create_team(db, "Engineering")
        channel = create_channel(db, "eng-general", "team", team_id=team.id)
        assert channel.team_id == team.id

    def test_get_channel(self, db):
        """Should get channel by ID."""
        created = create_channel(db, "general", "topic")
        fetched = get_channel(db, created.id)
        assert fetched is not None
        assert fetched.name == "general"

    def test_subscribe_to_channel(self, db):
        """Should subscribe worker to channel."""
        team = create_team(db, "Engineering")
        worker = create_worker(db, "Alice", "Developer", team.id, 50)
        channel = create_channel(db, "general", "topic")

        subscribe_to_channel(db, channel.id, worker.id)
        subscribers = get_channel_subscribers(db, channel.id)
        assert worker.id in subscribers

    def test_unsubscribe_from_channel(self, db):
        """Should unsubscribe worker from channel."""
        team = create_team(db, "Engineering")
        worker = create_worker(db, "Alice", "Developer", team.id, 50)
        channel = create_channel(db, "general", "topic")

        subscribe_to_channel(db, channel.id, worker.id)
        unsubscribe_from_channel(db, channel.id, worker.id)
        subscribers = get_channel_subscribers(db, channel.id)
        assert worker.id not in subscribers

    def test_get_worker_channels(self, db):
        """Should get channels worker is subscribed to."""
        team = create_team(db, "Engineering")
        worker = create_worker(db, "Alice", "Developer", team.id, 50)
        channel1 = create_channel(db, "general", "topic")
        channel2 = create_channel(db, "random", "topic")

        subscribe_to_channel(db, channel1.id, worker.id)
        subscribe_to_channel(db, channel2.id, worker.id)

        channels = get_worker_channels(db, worker.id)
        assert len(channels) == 2


class TestMessageQueries:
    """Test message queries."""

    @pytest.fixture
    def setup(self, db):
        """Create test channel and worker."""
        team = create_team(db, "Engineering")
        worker = create_worker(db, "Alice", "Developer", team.id, 50)
        channel = create_channel(db, "general", "topic")
        return {"team": team, "worker": worker, "channel": channel}

    def test_create_message(self, db, setup):
        """Should create a message."""
        msg = create_message(
            db, setup["channel"].id, setup["worker"].id, "Hello world"
        )
        assert msg.content == "Hello world"
        assert msg.priority == 2
        assert msg.time_sensitivity == "whenever"

    def test_create_message_with_priority(self, db, setup):
        """Should create message with custom priority."""
        msg = create_message(
            db, setup["channel"].id, setup["worker"].id, "Urgent!",
            priority=0, time_sensitivity="immediate"
        )
        assert msg.priority == 0
        assert msg.time_sensitivity == "immediate"

    def test_get_message(self, db, setup):
        """Should get message by ID."""
        created = create_message(db, setup["channel"].id, setup["worker"].id, "Test")
        fetched = get_message(db, created.id)
        assert fetched is not None
        assert fetched.content == "Test"

    def test_get_channel_messages(self, db, setup):
        """Should get messages in channel, newest first."""
        create_message(db, setup["channel"].id, setup["worker"].id, "First")
        create_message(db, setup["channel"].id, setup["worker"].id, "Second")
        create_message(db, setup["channel"].id, setup["worker"].id, "Third")

        messages = get_channel_messages(db, setup["channel"].id, limit=2)
        assert len(messages) == 2
        assert messages[0].content == "Third"  # newest first

    def test_get_thread_messages(self, db, setup):
        """Should get messages in thread, oldest first."""
        thread_id = "thread-123"
        create_message(
            db, setup["channel"].id, setup["worker"].id, "Start",
            thread_id=thread_id
        )
        create_message(
            db, setup["channel"].id, setup["worker"].id, "Reply",
            thread_id=thread_id
        )

        messages = get_thread_messages(db, thread_id)
        assert len(messages) == 2
        assert messages[0].content == "Start"  # oldest first

    def test_message_refs(self, db, setup):
        """Should add and get message references."""
        msg = create_message(db, setup["channel"].id, setup["worker"].id, "Test")
        add_message_ref(db, msg.id, "bead", "bead-123")
        add_message_ref(db, msg.id, "okr", "okr-456")

        refs = get_message_refs(db, msg.id)
        assert len(refs) == 2
        assert ("bead", "bead-123") in refs
        assert ("okr", "okr-456") in refs


class TestConfigQueries:
    """Test config queries."""

    def test_set_and_get_config(self, db):
        """Should set and get config values."""
        set_config(db, "test_key", "test_value")
        value = get_config(db, "test_key")
        assert value == "test_value"

    def test_get_missing_config(self, db):
        """Should return None for missing config."""
        value = get_config(db, "nonexistent")
        assert value is None

    def test_update_config(self, db):
        """Should update existing config."""
        set_config(db, "test_key", "value1")
        set_config(db, "test_key", "value2")
        value = get_config(db, "test_key")
        assert value == "value2"


class TestGetOrgDbPath:
    """Test org db path helper."""

    def test_get_org_db_path(self):
        """Should return correct db path."""
        org_path = Path("/home/user/orgs/my-org")
        db_path = get_org_db_path(org_path)
        assert db_path == Path("/home/user/orgs/my-org/live/quinn.db")
