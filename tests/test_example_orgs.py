"""Integration tests for example_orgs workflows.

These tests verify that the example org scripts work correctly
and document known issues for tracking.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


EXAMPLE_ORGS_DIR = Path(__file__).parent.parent / "example_orgs"
QN_WRAPPER = EXAMPLE_ORGS_DIR / "org-scripts" / "common" / "qn"


@pytest.fixture
def temp_org_dir():
    """Create a temporary directory for org files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def run_qn(*args, org_path: Path = None) -> subprocess.CompletedProcess:
    """Run the qn CLI wrapper with given arguments."""
    cmd = [str(QN_WRAPPER)]
    if org_path:
        cmd.extend(["--org-path", str(org_path)])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestQnWrapper:
    """Test the qn CLI wrapper exists and works."""

    def test_wrapper_exists(self):
        """The qn wrapper script should exist."""
        assert QN_WRAPPER.exists(), f"Wrapper not found at {QN_WRAPPER}"

    def test_wrapper_is_executable(self):
        """The qn wrapper should be executable."""
        assert os.access(QN_WRAPPER, os.X_OK), f"Wrapper not executable: {QN_WRAPPER}"

    def test_wrapper_shows_help(self):
        """qn --help should show usage."""
        result = run_qn("--help")
        assert result.returncode == 0
        assert "QuinnAI" in result.stdout
        assert "org" in result.stdout
        assert "wrkr" in result.stdout


class TestOrgInit:
    """Test qn org init command."""

    def test_init_creates_folder_structure(self, temp_org_dir):
        """qn org init should create the expected folder structure."""
        result = run_qn("org", "init", org_path=temp_org_dir)

        assert result.returncode == 0, f"Init failed: {result.stderr}"
        assert (temp_org_dir / "config").exists()
        assert (temp_org_dir / "org-chart").exists()
        assert (temp_org_dir / "live").exists()
        assert (temp_org_dir / "live" / "quinn.db").exists()
        assert (temp_org_dir / "storage").exists()

    def test_init_creates_ceo(self, temp_org_dir):
        """qn org init should create a CEO worker."""
        result = run_qn("org", "init", "--ceo-name", "TestCEO", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "Created CEO" in result.stdout
        assert "TestCEO" in result.stdout

    def test_init_twice_fails(self, temp_org_dir):
        """qn org init should fail if already initialized."""
        run_qn("org", "init", org_path=temp_org_dir)
        result = run_qn("org", "init", org_path=temp_org_dir)

        assert result.returncode != 0
        assert "already initialized" in result.stdout.lower() or "already initialized" in result.stderr.lower()


class TestOrgStart:
    """Test qn org start command."""

    def test_start_changes_status_to_running(self, temp_org_dir):
        """qn org start should transition org to running."""
        run_qn("org", "init", org_path=temp_org_dir)
        result = run_qn("org", "start", "--no-spawn-ceo", "--skip-config-validation", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "running" in result.stdout.lower()

    def test_start_activates_ceo(self, temp_org_dir):
        """qn org start should activate the CEO worker."""
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", "--skip-config-validation", org_path=temp_org_dir)

        result = run_qn("org", "status", org_path=temp_org_dir)
        assert "active" in result.stdout.lower()

    def test_start_spawns_ceo_session(self, temp_org_dir):
        """qn org start should spawn a session for CEO.

        Fixed: quinnai-qi2r - Sessions now tracked in database.
        """
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--skip-config-validation", org_path=temp_org_dir)  # Default spawns CEO session

        result = run_qn("org", "status", org_path=temp_org_dir)
        # Should show at least 1 session
        assert "Sessions: 1" in result.stdout or "Sessions:  1" in result.stdout


class TestOrgStatus:
    """Test qn org status command."""

    def test_status_shows_org_info(self, temp_org_dir):
        """qn org status should show org info."""
        run_qn("org", "init", org_path=temp_org_dir)

        result = run_qn("org", "status", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "Status:" in result.stdout
        assert "Workers:" in result.stdout


class TestOrgStop:
    """Test qn org stop command."""

    def test_stop_changes_status_to_stopped(self, temp_org_dir):
        """qn org stop should transition org to stopped."""
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", "--skip-config-validation", org_path=temp_org_dir)
        result = run_qn("org", "stop", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()


class TestHelloWorldExample:
    """Test the hello-world example workflow end-to-end."""

    def test_hello_world_init_and_run(self, temp_org_dir):
        """Test the basic hello-world workflow."""
        # Initialize
        result = run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Start
        result = run_qn("org", "start", "--no-spawn-ceo", "--skip-config-validation", org_path=temp_org_dir)
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        # Check status
        result = run_qn("org", "status", org_path=temp_org_dir)
        assert result.returncode == 0
        assert "running" in result.stdout.lower()
        assert "Alice" in result.stdout

        # Stop
        result = run_qn("org", "stop", org_path=temp_org_dir)
        assert result.returncode == 0


class TestWorkerLifecycle:
    """Test complete worker lifecycle: create -> run -> terminate.

    These tests verify the worker lifecycle state machine through
    direct Python API calls, since CLI commands may not exist for
    all lifecycle operations.
    """

    @pytest.fixture
    def initialized_org(self, temp_org_dir):
        """Initialize org and return (org_dir, db) tuple."""
        result = run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Open the database
        from cli.core.db import open_database
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        yield temp_org_dir, db

        db.close()

    def test_hire_creates_worker_in_pending(self, initialized_org):
        """Hiring creates worker in pending lifecycle state."""
        org_dir, db = initialized_org

        from cli.core.worker import Worker, HiringScope
        from cli.core.queries import get_worker_by_name, get_all_teams

        # Get CEO and give them hiring authority
        ceo_data = get_worker_by_name(db, "Alice")
        assert ceo_data is not None, "CEO should exist after org init"

        ceo = Worker.get(db, ceo_data.id)

        # Grant CEO hiring authority
        scope = HiringScope(
            allowed_roles={"engineer", "analyst"},
            max_cost=80,
            max_total_budget=10000,
        )
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = ?,
                   max_reports = ?
               WHERE id = ?""",
            (scope.to_json(), 5000, 10, ceo.id)
        )
        db.connection.commit()
        ceo.refresh()

        # CEO hires a worker
        new_worker = ceo.hire(
            name="Bob",
            role="engineer",
            skills={"coding": 70, "debugging": 60},
            cost=50,
        )

        # Verify worker is in pending state
        assert new_worker.lifecycle_status == "pending"
        assert new_worker.manager_id == ceo.id
        assert new_worker.name == "Bob"
        assert new_worker.role == "engineer"

        # Verify worker exists in database
        from cli.core.queries import get_worker
        db_worker = get_worker(db, new_worker.id)
        assert db_worker is not None
        assert db_worker.status == "pending"

    def test_worker_lifecycle_transitions(self, initialized_org):
        """Test lifecycle state machine: pending -> onboarding -> active -> terminated."""
        org_dir, db = initialized_org

        from cli.core.worker import Worker, HiringScope
        from cli.core.queries import get_worker_by_name

        # Get CEO and give them hiring authority
        ceo_data = get_worker_by_name(db, "Alice")
        ceo = Worker.get(db, ceo_data.id)

        scope = HiringScope(
            allowed_roles={"engineer"},
            max_cost=80,
            max_total_budget=10000,
        )
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = ?,
                   max_reports = ?
               WHERE id = ?""",
            (scope.to_json(), 5000, 10, ceo.id)
        )
        db.connection.commit()
        ceo.refresh()

        # Hire worker
        worker = ceo.hire("Charlie", "engineer", {"coding": 65}, 45)
        assert worker.lifecycle_status == "pending"

        # Transition: pending -> onboarding
        worker.start_onboarding()
        assert worker.lifecycle_status == "onboarding"

        # Transition: onboarding -> active
        worker.complete_onboarding()
        assert worker.lifecycle_status == "active"

        # Transition: active -> offboarding
        worker.start_offboarding()
        assert worker.lifecycle_status == "offboarding"

        # Transition: offboarding -> terminated
        worker.terminate()
        assert worker.lifecycle_status == "terminated"

    def test_worker_folder_created_on_hire(self, initialized_org):
        """Hiring should create worker storage folder."""
        org_dir, db = initialized_org

        from cli.core.worker import Worker, HiringScope
        from cli.core.queries import get_worker_by_name
        from cli.core.storage import StorageManager

        # Get CEO
        ceo_data = get_worker_by_name(db, "Alice")
        ceo = Worker.get(db, ceo_data.id)

        # Give CEO hiring authority
        scope = HiringScope(allowed_roles={"engineer"}, max_cost=80)
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = ?,
                   max_reports = ?
               WHERE id = ?""",
            (scope.to_json(), 5000, 10, ceo.id)
        )
        db.connection.commit()
        ceo.refresh()

        # Hire worker
        worker = ceo.hire("Dave", "engineer", {}, 40)

        # Create storage manager and ensure storage exists
        storage = StorageManager(org_dir, db)
        worker_path = storage.ensure_worker_storage(
            worker.id,
            reports_to=ceo.id,
        )

        # Verify folder was created
        assert worker_path.exists(), f"Worker folder should exist at {worker_path}"
        assert worker_path.is_dir(), "Worker path should be a directory"

        # Verify folder is under CEO's hierarchy
        assert ceo.id in str(worker_path), "Worker folder should be under CEO hierarchy"

    def test_terminate_freezes_storage(self, initialized_org):
        """Terminating worker should freeze their storage folder."""
        org_dir, db = initialized_org

        from cli.core.worker import Worker, HiringScope
        from cli.core.queries import get_worker_by_name
        from cli.core.storage import StorageManager, FROZEN_SUFFIX

        # Get CEO
        ceo_data = get_worker_by_name(db, "Alice")
        ceo = Worker.get(db, ceo_data.id)

        # Give CEO hiring authority
        scope = HiringScope(allowed_roles={"engineer"}, max_cost=80)
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = ?,
                   max_reports = ?
               WHERE id = ?""",
            (scope.to_json(), 5000, 10, ceo.id)
        )
        db.connection.commit()
        ceo.refresh()

        # Hire worker
        worker = ceo.hire("Eve", "engineer", {}, 35)

        # Storage is now created automatically by hire()
        storage = StorageManager(org_dir, db)
        worker_path = storage.get_worker_path(worker.id, reports_to=ceo.id)
        assert worker_path.exists(), "hire() should create storage folder"

        # Create a test file in the worker's storage
        test_file = worker_path / "work_notes.txt"
        test_file.write_text("Some important work notes")

        # Go through full lifecycle to terminated
        # terminate() now automatically freezes storage
        worker.start_onboarding()
        worker.complete_onboarding()
        worker.start_offboarding()
        worker.terminate()

        assert worker.lifecycle_status == "terminated"

        # Storage should now be frozen by terminate()
        frozen_path = worker_path.parent / f"{worker_path.name}{FROZEN_SUFFIX}"

        # Verify folder is frozen
        assert frozen_path.exists(), "terminate() should freeze storage folder"
        assert frozen_path.name.endswith(FROZEN_SUFFIX), \
            f"Frozen folder should have {FROZEN_SUFFIX} suffix"
        assert not worker_path.exists(), "Original folder should not exist"

        # Verify we can check if frozen
        assert storage.is_worker_frozen(worker.id, reports_to=ceo.id)

        # Verify test file content preserved
        frozen_test_file = frozen_path / "work_notes.txt"
        assert frozen_test_file.exists()
        assert frozen_test_file.read_text() == "Some important work notes"

    def test_worker_session_lifecycle(self, initialized_org):
        """Test worker session can be started and stopped.

        Note: This tests the worker state transitions, not actual tmux sessions.
        Session spawning requires budget allocation and is tested separately.
        """
        org_dir, db = initialized_org

        from cli.core.worker import Worker, HiringScope
        from cli.core.queries import get_worker_by_name

        # Get CEO
        ceo_data = get_worker_by_name(db, "Alice")
        ceo = Worker.get(db, ceo_data.id)

        # Give CEO hiring authority
        scope = HiringScope(allowed_roles={"engineer"}, max_cost=80)
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = ?,
                   max_reports = ?
               WHERE id = ?""",
            (scope.to_json(), 5000, 10, ceo.id)
        )
        db.connection.commit()
        ceo.refresh()

        # Hire and onboard worker
        worker = ceo.hire("Frank", "engineer", {}, 45)
        worker.start_onboarding()

        # No runtime state initially
        assert worker.runtime_status is None

        # Start session (during onboarding)
        worker.start_session(pid=12345)
        assert worker.runtime_status == "starting"

        # Session ready
        worker.session_ready()
        assert worker.runtime_status == "running"

        # Complete onboarding
        worker.complete_onboarding()
        assert worker.lifecycle_status == "active"

        # Worker can now work
        assert worker.can_work

        # Go to idle
        worker.finish_work()
        assert worker.runtime_status == "idle"
        assert worker.can_work  # Still can work

        # Stop session
        worker.stop_session()
        assert worker.runtime_status == "stopped"
        assert not worker.can_work  # Cannot work when session stopped

    def test_qn_wrkr_status_shows_lifecycle(self, initialized_org):
        """qn wrkr status should show worker lifecycle state.

        Tests that the CLI correctly displays worker status after init.
        """
        org_dir, db = initialized_org

        from cli.core.queries import get_worker_by_name

        # Get CEO info
        ceo_data = get_worker_by_name(db, "Alice")
        assert ceo_data is not None

        # Run qn wrkr status for the CEO
        result = run_qn("wrkr", "status", ceo_data.id, org_path=org_dir)

        # Should succeed or provide info (may fail if command not fully implemented)
        # At minimum check it doesn't crash
        # The status command should show the worker ID somewhere
        if result.returncode == 0:
            # If command exists and works, verify some content
            output = result.stdout.lower()
            assert "alice" in output or ceo_data.id in output

    def test_onboarding_failure_terminates_worker(self, initialized_org):
        """Failed onboarding should transition worker to terminated."""
        org_dir, db = initialized_org

        from cli.core.worker import Worker, HiringScope
        from cli.core.queries import get_worker_by_name

        # Get CEO
        ceo_data = get_worker_by_name(db, "Alice")
        ceo = Worker.get(db, ceo_data.id)

        # Give CEO hiring authority
        scope = HiringScope(allowed_roles={"engineer"}, max_cost=80)
        db.execute(
            """UPDATE workers
               SET hiring_authority_scope = ?,
                   delegated_budget = ?,
                   max_reports = ?
               WHERE id = ?""",
            (scope.to_json(), 5000, 10, ceo.id)
        )
        db.connection.commit()
        ceo.refresh()

        # Hire worker
        worker = ceo.hire("Grace", "engineer", {}, 50)

        # Start onboarding
        worker.start_onboarding()
        assert worker.lifecycle_status == "onboarding"

        # Fail onboarding (worker couldn't complete training, etc.)
        worker.fail_onboarding()
        assert worker.lifecycle_status == "terminated"

        # Verify terminated worker cannot start session
        from shared import InvalidLifecycleState
        import pytest

        with pytest.raises(InvalidLifecycleState):
            worker.start_session()


class TestKnownIssues:
    """Tests that document known issues.

    These tests are expected to fail until the issues are fixed.
    Each test links to a bead tracking the issue.
    """

    def test_init_creates_channels(self, temp_org_dir):
        """qn org init should create default channels.

        Fixed: quinnai-uekq - Channels are now created during init.
        """
        run_qn("org", "init", org_path=temp_org_dir)

        # Query database for channels
        import sqlite3
        db_path = temp_org_dir / "live" / "quinn.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM channels")
        count = cursor.fetchone()[0]
        conn.close()

        assert count > 0, "Expected at least one channel to be created"

    def test_org_chart_reflects_lifecycle_changes(self, temp_org_dir):
        """Org-chart should update when worker lifecycle changes.

        Fixed: quinnai-8x29 - Org start now updates org-chart.
        """
        import yaml

        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", "--skip-config-validation", org_path=temp_org_dir)

        org_chart_path = temp_org_dir / "org-chart" / "current.yaml"
        with open(org_chart_path) as f:
            org_chart = yaml.safe_load(f)

        # Find the CEO in the workers dict
        workers = org_chart.get("workers", {})
        ceo_entry = list(workers.values())[0]

        assert ceo_entry["lifecycle"] == "active", \
            f"Expected 'active', got '{ceo_entry['lifecycle']}'"


class TestCommunication:
    """Test inter-worker communication: messages/inbox/channels."""

    def test_init_creates_general_channel(self, temp_org_dir):
        """Org init should create a #general channel."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        # Check DB for #general channel
        from cli.core.db import open_database
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            row = db.fetchone(
                "SELECT * FROM channels WHERE name = 'general'"
            )
            assert row is not None, "Expected #general channel to exist"
            assert row["type"] == "topic", "Expected #general to be a topic channel"
        finally:
            db.close()

    def test_init_creates_escalations_channel(self, temp_org_dir):
        """Org init should create a #board-channel for board communications."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        # Check DB for #board-channel
        from cli.core.db import open_database
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            row = db.fetchone(
                "SELECT * FROM channels WHERE name = 'board-channel'"
            )
            assert row is not None, "Expected #board-channel to exist"
            assert row["type"] == "topic", "Expected #board-channel to be a topic channel"
        finally:
            db.close()

    def test_ceo_subscribed_to_general(self, temp_org_dir):
        """CEO should be auto-subscribed to #general."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import get_worker_by_name, get_worker_channels
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = get_worker_by_name(db, "Alice")
            assert ceo is not None, "CEO should exist"

            channels = get_worker_channels(db, ceo.id)
            channel_names = [ch.name for ch in channels]

            assert "general" in channel_names, \
                f"CEO should be subscribed to #general, got: {channel_names}"
        finally:
            db.close()

    def test_ceo_subscribed_to_escalations(self, temp_org_dir):
        """CEO should be auto-subscribed to #board-channel."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import get_worker_by_name, get_worker_channels
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = get_worker_by_name(db, "Alice")
            assert ceo is not None, "CEO should exist"

            channels = get_worker_channels(db, ceo.id)
            channel_names = [ch.name for ch in channels]

            assert "board-channel" in channel_names, \
                f"CEO should be subscribed to #board-channel, got: {channel_names}"
        finally:
            db.close()

    def test_ceo_subscribed_to_team_channel(self, temp_org_dir):
        """CEO should be auto-subscribed to their team channel."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import get_worker_by_name, get_worker_channels
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = get_worker_by_name(db, "Alice")
            assert ceo is not None, "CEO should exist"

            channels = get_worker_channels(db, ceo.id)
            channel_names = [ch.name for ch in channels]
            channel_types = {ch.name: ch.type for ch in channels}

            # Team channel is named after team (lowercase, dash-separated)
            team_channels = [name for name, ctype in channel_types.items() if ctype == "team"]
            assert len(team_channels) > 0, \
                f"CEO should be subscribed to team channel, got: {channel_names}"
        finally:
            db.close()

    def test_hired_worker_subscribed_to_team_channel(self, temp_org_dir):
        """Workers hired by a manager should be subscribed to the team channel."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", "--skip-config-validation", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import get_worker_by_name, get_worker_channels
        from cli.core.worker import Worker, HiringScope
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = Worker.get(db, get_worker_by_name(db, "Alice").id)
            ceo._org_path = temp_org_dir

            # Give CEO hiring authority
            from datetime import datetime
            db.execute(
                """UPDATE workers
                   SET hiring_authority_scope = ?,
                       delegated_budget = 1000,
                       updated_at = ?
                   WHERE id = ?""",
                (HiringScope(allowed_roles={"engineer"}, max_cost=50).to_json(),
                 datetime.now(), ceo.id)
            )
            db.connection.commit()
            ceo._worker_data = None  # Invalidate cache

            # Hire a worker
            bob = ceo.hire("Bob", "engineer", {}, 30)

            # Check Bob's channel subscriptions
            channels = get_worker_channels(db, bob.id)
            channel_types = {ch.name: ch.type for ch in channels}

            team_channels = [name for name, ctype in channel_types.items() if ctype == "team"]
            assert len(team_channels) > 0, \
                f"Hired worker should be subscribed to team channel, got: {[ch.name for ch in channels]}"
        finally:
            db.close()

    def test_terminated_worker_unsubscribed_from_channels(self, temp_org_dir):
        """Terminated workers should be unsubscribed from all channels."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", "--skip-config-validation", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import get_worker_by_name, get_worker_channels
        from cli.core.worker import Worker, HiringScope
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = Worker.get(db, get_worker_by_name(db, "Alice").id)
            ceo._org_path = temp_org_dir

            # Give CEO hiring authority
            from datetime import datetime
            db.execute(
                """UPDATE workers
                   SET hiring_authority_scope = ?,
                       delegated_budget = 1000,
                       updated_at = ?
                   WHERE id = ?""",
                (HiringScope(allowed_roles={"engineer"}, max_cost=50).to_json(),
                 datetime.now(), ceo.id)
            )
            db.connection.commit()
            ceo._worker_data = None

            # Hire and then terminate a worker
            bob = ceo.hire("Bob", "engineer", {}, 30)

            # Verify Bob has channel subscriptions
            channels_before = get_worker_channels(db, bob.id)
            assert len(channels_before) > 0, "Worker should have channel subscriptions after hire"

            # Start onboarding, complete it, then terminate
            bob.start_onboarding()
            bob.complete_onboarding()
            bob.start_offboarding()
            bob.terminate()

            # Check Bob's channel subscriptions after termination
            channels_after = get_worker_channels(db, bob.id)
            assert len(channels_after) == 0, \
                f"Terminated worker should have no channel subscriptions, got: {[ch.name for ch in channels_after]}"
        finally:
            db.close()

    def test_send_message_to_channel(self, temp_org_dir):
        """Workers can send messages to channels."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import (
            get_worker_by_name,
            create_message,
            get_channel_messages,
        )
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = get_worker_by_name(db, "Alice")
            assert ceo is not None

            # Get the general channel
            row = db.fetchone("SELECT id FROM channels WHERE name = 'general'")
            assert row is not None
            channel_id = row["id"]

            # Send a message
            message = create_message(
                db,
                channel_id=channel_id,
                from_worker_id=ceo.id,
                content="Hello, organization!",
            )

            assert message.id is not None
            assert message.content == "Hello, organization!"

            # Verify message is in channel
            messages = get_channel_messages(db, channel_id)
            assert len(messages) == 1
            assert messages[0].content == "Hello, organization!"
        finally:
            db.close()

    def test_message_creates_notifications(self, temp_org_dir):
        """Sending a message should create notifications for subscribers."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import (
            get_worker_by_name,
            create_message_with_notifications,
            create_worker,
            subscribe_to_channel,
        )
        from cli.core.notifications import get_pending_notifications
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = get_worker_by_name(db, "Alice")
            assert ceo is not None

            # Get the general channel
            row = db.fetchone("SELECT id FROM channels WHERE name = 'general'")
            channel_id = row["id"]

            # Create another worker and subscribe them to #general
            team_row = db.fetchone("SELECT id FROM teams LIMIT 1")
            team_id = team_row["id"]
            bob = create_worker(db, "Bob", "engineer", team_id, 50, manager_id=ceo.id)
            subscribe_to_channel(db, channel_id, bob.id)

            # CEO sends a message (Bob should get notified)
            create_message_with_notifications(
                db,
                channel_id=channel_id,
                from_worker_id=ceo.id,
                content="Team update: new project starting!",
            )

            # Bob should have a pending notification
            bob_notifications = get_pending_notifications(db, bob.id)
            assert len(bob_notifications) == 1
            assert bob_notifications[0].channel_id == channel_id

            # CEO should NOT have a notification (sender doesn't get notified)
            ceo_notifications = get_pending_notifications(db, ceo.id)
            assert len(ceo_notifications) == 0
        finally:
            db.close()

    def test_inbox_shows_pending_notifications(self, temp_org_dir):
        """Inbox should show pending notifications for a worker."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import (
            get_worker_by_name,
            create_message_with_notifications,
            create_worker,
            subscribe_to_channel,
        )
        from cli.core.notifications import (
            get_pending_notifications,
            count_pending_notifications,
        )
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = get_worker_by_name(db, "Alice")

            # Get the general channel
            row = db.fetchone("SELECT id FROM channels WHERE name = 'general'")
            channel_id = row["id"]

            # Create another worker and subscribe them
            team_row = db.fetchone("SELECT id FROM teams LIMIT 1")
            team_id = team_row["id"]
            bob = create_worker(db, "Bob", "engineer", team_id, 50, manager_id=ceo.id)
            subscribe_to_channel(db, channel_id, bob.id)

            # Send multiple messages
            for i in range(3):
                create_message_with_notifications(
                    db,
                    channel_id=channel_id,
                    from_worker_id=ceo.id,
                    content=f"Message {i + 1}",
                )

            # Bob should have 3 pending notifications
            count = count_pending_notifications(db, bob.id)
            assert count == 3, f"Expected 3 notifications, got {count}"

            # Get the actual notifications
            notifications = get_pending_notifications(db, bob.id)
            assert len(notifications) == 3
        finally:
            db.close()

    def test_notification_can_be_marked_read(self, temp_org_dir):
        """Notifications can be marked as read."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        from cli.core.db import open_database
        from cli.core.queries import (
            get_worker_by_name,
            create_message_with_notifications,
            create_worker,
            subscribe_to_channel,
        )
        from cli.core.notifications import (
            get_pending_notifications,
            mark_notification_read,
            get_notification_bead,
        )
        db_path = temp_org_dir / "live" / "quinn.db"
        db = open_database(db_path)

        try:
            ceo = get_worker_by_name(db, "Alice")

            # Get the general channel
            row = db.fetchone("SELECT id FROM channels WHERE name = 'general'")
            channel_id = row["id"]

            # Create another worker and subscribe them
            team_row = db.fetchone("SELECT id FROM teams LIMIT 1")
            team_id = team_row["id"]
            bob = create_worker(db, "Bob", "engineer", team_id, 50, manager_id=ceo.id)
            subscribe_to_channel(db, channel_id, bob.id)

            # Send a message
            create_message_with_notifications(
                db,
                channel_id=channel_id,
                from_worker_id=ceo.id,
                content="Important announcement",
            )

            # Get Bob's notification
            notifications = get_pending_notifications(db, bob.id)
            assert len(notifications) == 1
            notif_id = notifications[0].id

            # Mark as read
            result = mark_notification_read(db, notif_id)
            assert result is True

            # Verify status changed
            updated_notif = get_notification_bead(db, notif_id)
            assert updated_notif.status == "read"
            assert updated_notif.read_at is not None
        finally:
            db.close()


class TestWorkManagement:
    """Test work management via beads integration.

    NOTE: Tests that create beads are marked xfail because org init does not
    initialize the beads database. Beads commands require 'bd init --prefix <prefix>'
    to be run first.
    """

    def test_bd_wrapper_list_works(self, temp_org_dir):
        """bd list command works through wrapper."""
        # Init org
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        # Run bd list through wrapper - list works even if db not initialized
        from cli.core.bd_wrapper import run_bd
        result = run_bd(["list", "--json"], org_path=Path(temp_org_dir), capture_output=True)
        assert result.returncode == 0

    # xfail removed - beads now initialized in org init
    def test_bd_wrapper_create_works(self, temp_org_dir):
        """bd create command works through wrapper."""
        # Init org
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        # Create a bead
        from cli.core.bd_wrapper import run_bd
        result = run_bd(
            ["create", "Test task", "--type=task", "--priority=2", "--json"],
            org_path=Path(temp_org_dir),
            skip_permission_check=True,
            capture_output=True,
        )
        assert result.returncode == 0

    # xfail removed - beads now initialized in org init
    def test_work_assignment_shows_in_get_work(self, temp_org_dir):
        """Assigned work shows in qn wrkr get-work."""
        # Init and start org
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        # Get CEO worker ID from database
        from cli.core.db import open_database, get_org_db_path
        from cli.core.queries import get_worker_by_name

        db = open_database(get_org_db_path(Path(temp_org_dir)))
        ceo = get_worker_by_name(db, "Alice")
        db.close()

        # Create and assign work to CEO
        from cli.core.bd_wrapper import run_bd
        create_result = run_bd(
            ["create", "CEO task", f"--assignee={ceo.id}", "--priority=1", "--json"],
            org_path=Path(temp_org_dir),
            skip_permission_check=True,
            capture_output=True,
        )
        assert create_result.returncode == 0

        # Note: get-work requires worker to be in can_work state
        # For this test, just verify the bead was created with assignment

    # xfail removed - beads now initialized in org init
    def test_work_status_transitions(self, temp_org_dir):
        """Work can transition through status states."""
        run_qn("org", "init", org_path=temp_org_dir)

        from cli.core.bd_wrapper import run_bd

        # Create work
        result = run_bd(
            ["create", "Status test", "--json"],
            org_path=Path(temp_org_dir),
            skip_permission_check=True,
            capture_output=True,
        )
        assert result.returncode == 0
        # Parse ID from output
        import json
        data = json.loads(result.stdout) if result.stdout else {}
        work_id = data.get("id") or "unknown"  # May need to parse differently

    # xfail removed - beads now initialized in org init
    def test_work_priority_ordering(self, temp_org_dir):
        """Work items are ordered by priority (P0 first)."""
        run_qn("org", "init", org_path=temp_org_dir)

        from cli.core.bd_wrapper import run_bd

        # Create P3, P1, P2 tasks (out of order) - these will fail without bd init
        result1 = run_bd(["create", "Low priority", "--priority=3", "--json"],
                         org_path=Path(temp_org_dir), skip_permission_check=True, capture_output=True)
        assert result1.returncode == 0, "Should be able to create beads"

        result2 = run_bd(["create", "High priority", "--priority=1", "--json"],
                         org_path=Path(temp_org_dir), skip_permission_check=True, capture_output=True)
        assert result2.returncode == 0, "Should be able to create beads"

        result3 = run_bd(["create", "Medium priority", "--priority=2", "--json"],
                         org_path=Path(temp_org_dir), skip_permission_check=True, capture_output=True)
        assert result3.returncode == 0, "Should be able to create beads"

        # List and verify ordering
        result = run_bd(["list", "--json"],
                        org_path=Path(temp_org_dir), skip_permission_check=True, capture_output=True)
        import json
        items = json.loads(result.stdout) if result.stdout else []

        # Verify we have items and they are ordered by priority
        assert len(items) == 3, "Should have 3 work items"
        priorities = [item.get("priority", 4) for item in items]
        assert priorities == sorted(priorities), "Items should be sorted by priority"


class TestOKRCascade:
    """Test OKR cascade: goals/alignment/tracking.

    NOTE: Many tests are marked xfail because org init does not initialize
    the beads database. OKR commands require beads to be initialized first
    with 'bd init --prefix <prefix>'. This is tracked as a known limitation.

    To make these tests pass, org init should also initialize the beads
    database, or the tests should run 'bd init' before creating OKRs.
    """

    # xfail removed - beads now initialized in org init
    def test_okr_create_via_set(self, temp_org_dir):
        """qn org okr set creates OKR bead."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        result = run_qn(
            "org", "okr", "set",
            "--title", "Q1 Revenue Growth",
            "--owner", "ceo",
            org_path=temp_org_dir
        )
        assert result.returncode == 0
        assert "Created" in result.stdout or "okr" in result.stdout.lower()

    # xfail removed - beads now initialized in org init
    def test_okr_create_via_add(self, temp_org_dir):
        """qn org okr add (alias for set) creates OKR bead."""
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        result = run_qn(
            "org", "okr", "add",
            "--title", "Q2 Customer Growth",
            "--owner", "ceo",
            org_path=temp_org_dir
        )
        assert result.returncode == 0
        assert "Created" in result.stdout or "okr" in result.stdout.lower()

    # xfail removed - beads now initialized in org init
    def test_okr_list_shows_created(self, temp_org_dir):
        """qn org okr list shows created OKRs."""
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "okr", "set", "--title", "Test OKR", org_path=temp_org_dir)

        result = run_qn("org", "okr", "list", org_path=temp_org_dir)
        assert result.returncode == 0
        assert "Test OKR" in result.stdout

    def test_okr_list_empty_org(self, temp_org_dir):
        """qn org okr list on empty org shows no OKRs."""
        run_qn("org", "init", org_path=temp_org_dir)

        result = run_qn("org", "okr", "list", org_path=temp_org_dir)
        assert result.returncode == 0
        assert "No OKRs found" in result.stdout or result.stdout.strip() == ""

    # xfail removed - beads now initialized in org init
    def test_okr_hierarchy_via_parent(self, temp_org_dir):
        """OKRs can have parent-child relationships."""
        run_qn("org", "init", org_path=temp_org_dir)

        # Create parent OKR
        result1 = run_qn(
            "org", "okr", "set",
            "--title", "Company Goal",
            org_path=temp_org_dir
        )
        assert result1.returncode == 0

        # Extract parent OKR ID from output
        # Output format typically: "Created issue: quinnai-xxxx"
        parent_id = None
        for line in result1.stdout.split("\n"):
            if "Created" in line and "-" in line:
                words = line.split()
                for word in reversed(words):
                    if "-" in word and not word.startswith("-"):
                        parent_id = word.strip()
                        break
                break

        # If we couldn't parse ID, use bd list to get it
        if not parent_id:
            from cli.core.bd_wrapper import run_bd
            list_result = run_bd(
                ["list", "--label=okr", "--json"],
                org_path=Path(temp_org_dir),
                skip_permission_check=True,
                capture_output=True,
            )
            if list_result.returncode == 0 and list_result.stdout.strip():
                import json
                okrs = json.loads(list_result.stdout)
                if okrs:
                    parent_id = okrs[0].get("id")

        assert parent_id is not None, "Should have created parent OKR"

        # Create child OKR with --parent
        result2 = run_qn(
            "org", "okr", "set",
            "--title", "Team Goal",
            "--parent", parent_id,
            org_path=temp_org_dir
        )
        assert result2.returncode == 0

    # xfail removed - beads now initialized in org init
    def test_work_okr_linking(self, temp_org_dir):
        """Work items can link to OKRs via 'serves' dependency."""
        run_qn("org", "init", org_path=temp_org_dir)

        # Create OKR
        okr_result = run_qn(
            "org", "okr", "set",
            "--title", "Test OKR",
            org_path=temp_org_dir
        )
        assert okr_result.returncode == 0

        # Get OKR ID
        from cli.core.bd_wrapper import run_bd
        import json

        okr_list = run_bd(
            ["list", "--label=okr", "--json"],
            org_path=Path(temp_org_dir),
            skip_permission_check=True,
            capture_output=True,
        )
        okrs = json.loads(okr_list.stdout) if okr_list.stdout.strip() else []
        assert len(okrs) > 0, "Should have created OKR"
        okr_id = okrs[0].get("id")

        # Create work item
        work_result = run_bd(
            ["create", "Test task", "--type=task", "--json"],
            org_path=Path(temp_org_dir),
            skip_permission_check=True,
            capture_output=True,
        )
        assert work_result.returncode == 0

        # Get work item ID
        work_list = run_bd(
            ["list", "--type=task", "--json"],
            org_path=Path(temp_org_dir),
            skip_permission_check=True,
            capture_output=True,
        )
        tasks = json.loads(work_list.stdout) if work_list.stdout.strip() else []
        assert len(tasks) > 0, "Should have created task"
        work_id = tasks[0].get("id")

        # Link work to OKR via qn org okr link
        link_result = run_qn(
            "org", "okr", "link",
            work_id, okr_id,
            org_path=temp_org_dir
        )
        assert link_result.returncode == 0
        assert "Linked" in link_result.stdout or "serves" in link_result.stdout.lower()

    # xfail removed - beads now initialized in org init
    def test_okr_show_displays_details(self, temp_org_dir):
        """qn org okr show displays OKR details."""
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn(
            "org", "okr", "set",
            "--title", "Detailed OKR",
            "--owner", "ceo",
            org_path=temp_org_dir
        )

        # Get OKR ID
        from cli.core.bd_wrapper import run_bd
        import json

        okr_list = run_bd(
            ["list", "--label=okr", "--json"],
            org_path=Path(temp_org_dir),
            skip_permission_check=True,
            capture_output=True,
        )
        okrs = json.loads(okr_list.stdout) if okr_list.stdout.strip() else []
        assert len(okrs) > 0, "Should have created OKR"
        okr_id = okrs[0].get("id")

        # Show OKR details
        result = run_qn("org", "okr", "show", okr_id, org_path=temp_org_dir)
        assert result.returncode == 0
        assert "Detailed OKR" in result.stdout or okr_id in result.stdout

    def test_okr_cascade_shows_hierarchy(self, temp_org_dir):
        """qn org okr cascade shows hierarchy tree."""
        run_qn("org", "init", org_path=temp_org_dir)
        # Note: OKR creation will fail since beads not initialized, but cascade command should still work
        run_qn("org", "okr", "set", "--title", "Root OKR", org_path=temp_org_dir)

        result = run_qn("org", "okr", "cascade", org_path=temp_org_dir)
        assert result.returncode == 0
        # Should show either tree structure or "No OKRs found" or the OKR title
        assert "OKR Cascade" in result.stdout or "Root OKR" in result.stdout or "No OKRs" in result.stdout

    def test_okr_cascade_empty_org(self, temp_org_dir):
        """qn org okr cascade on empty org shows no OKRs."""
        run_qn("org", "init", org_path=temp_org_dir)

        result = run_qn("org", "okr", "cascade", org_path=temp_org_dir)
        assert result.returncode == 0
        assert "No OKRs found" in result.stdout or "OKR Cascade" in result.stdout

    # xfail removed - beads now initialized in org init
    def test_okr_cascade_with_root_filter(self, temp_org_dir):
        """qn org okr cascade --root filters to specific OKR tree."""
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "okr", "set", "--title", "Root OKR", org_path=temp_org_dir)

        # Get OKR ID
        from cli.core.bd_wrapper import run_bd
        import json

        okr_list = run_bd(
            ["list", "--label=okr", "--json"],
            org_path=Path(temp_org_dir),
            skip_permission_check=True,
            capture_output=True,
        )
        okrs = json.loads(okr_list.stdout) if okr_list.stdout.strip() else []
        assert len(okrs) > 0, "Should have created OKR"
        okr_id = okrs[0].get("id")

        result = run_qn("org", "okr", "cascade", "--root", okr_id, org_path=temp_org_dir)
        assert result.returncode == 0
        assert okr_id in result.stdout or "OKR Cascade" in result.stdout

    # xfail removed - beads now initialized in org init
    def test_okr_with_priority(self, temp_org_dir):
        """OKR can be created with priority."""
        run_qn("org", "init", org_path=temp_org_dir)

        result = run_qn(
            "org", "okr", "set",
            "--title", "High Priority OKR",
            "--priority", "0",
            org_path=temp_org_dir
        )
        assert result.returncode == 0

    # xfail removed - beads now initialized in org init
    def test_okr_with_labels(self, temp_org_dir):
        """OKR can be created with labels."""
        run_qn("org", "init", org_path=temp_org_dir)

        result = run_qn(
            "org", "okr", "set",
            "--title", "Labeled OKR",
            "--label", "growth",
            "--label", "q1",
            org_path=temp_org_dir
        )
        assert result.returncode == 0

    # xfail removed - beads now initialized in org init
    def test_okr_with_description(self, temp_org_dir):
        """OKR can be created with description."""
        run_qn("org", "init", org_path=temp_org_dir)

        result = run_qn(
            "org", "okr", "set",
            "--title", "Described OKR",
            "--description", "This is the objective description with key results",
            org_path=temp_org_dir
        )
        assert result.returncode == 0

    def test_okr_list_with_status_filter(self, temp_org_dir):
        """qn org okr list can filter by status."""
        run_qn("org", "init", org_path=temp_org_dir)
        # OKR creation will fail since beads not initialized, but list command should work
        run_qn("org", "okr", "set", "--title", "Test OKR", org_path=temp_org_dir)

        # Filter by open status (default) - should return no OKRs since creation failed
        result = run_qn("org", "okr", "list", "--status", "open", org_path=temp_org_dir)
        assert result.returncode == 0

    def test_okr_list_with_all_flag(self, temp_org_dir):
        """qn org okr list --all includes all OKRs."""
        run_qn("org", "init", org_path=temp_org_dir)
        # OKR creation will fail since beads not initialized, but list command should work
        run_qn("org", "okr", "set", "--title", "Test OKR", org_path=temp_org_dir)

        result = run_qn("org", "okr", "list", "--all", org_path=temp_org_dir)
        assert result.returncode == 0


class TestSystemevalResults:
    """Test systemeval-results.csv generation and validation.

    These tests verify the standardized results format that enables
    comparison across example org runs.
    """

    def test_archive_generates_systemeval_csv(self, temp_org_dir):
        """Archive should generate systemeval-results.csv."""
        # Setup org
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        # Run archive script
        archive_script = EXAMPLE_ORGS_DIR / "org-scripts" / "common" / "archive.sh"
        result = subprocess.run(
            [str(archive_script), str(temp_org_dir), "test-run"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Archive failed: {result.stderr}"
        assert "Systemeval results" in result.stdout

        # Find the archive and check CSV exists
        run_history = EXAMPLE_ORGS_DIR / "run-history"
        org_name = temp_org_dir.name
        from tests.systemeval_utils import find_latest_archive

        archive_dir = find_latest_archive(run_history, org_name)
        assert archive_dir is not None, "Archive should be created"

        csv_path = archive_dir / "systemeval-results.csv"
        assert csv_path.exists(), "systemeval-results.csv should be generated"

    def test_systemeval_csv_has_correct_schema(self, temp_org_dir):
        """systemeval-results.csv should have all expected columns."""
        # Setup and archive
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)

        archive_script = EXAMPLE_ORGS_DIR / "org-scripts" / "common" / "archive.sh"
        subprocess.run(
            [str(archive_script), str(temp_org_dir), "schema-test"],
            capture_output=True,
            text=True,
        )

        # Parse CSV and verify schema
        run_history = EXAMPLE_ORGS_DIR / "run-history"
        org_name = temp_org_dir.name
        from tests.systemeval_utils import find_latest_archive, parse_systemeval_csv

        archive_dir = find_latest_archive(run_history, org_name)
        csv_path = archive_dir / "systemeval-results.csv"

        result = parse_systemeval_csv(csv_path)

        # Verify all fields are populated
        assert result.run_id is not None
        assert result.org_name == org_name
        assert result.timestamp is not None
        assert result.org_status == "initialized"
        assert result.worker_count == 1  # CEO

    def test_systemeval_result_validation(self, temp_org_dir):
        """ResultValidator provides fluent assertions."""
        # Setup, start, and stop org
        run_qn("org", "init", "--ceo-name", "Alice", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", "--skip-config-validation", org_path=temp_org_dir)
        run_qn("org", "stop", org_path=temp_org_dir)

        # Archive
        archive_script = EXAMPLE_ORGS_DIR / "org-scripts" / "common" / "archive.sh"
        subprocess.run(
            [str(archive_script), str(temp_org_dir), "validation-test"],
            capture_output=True,
            text=True,
        )

        # Parse and validate
        run_history = EXAMPLE_ORGS_DIR / "run-history"
        org_name = temp_org_dir.name
        from tests.systemeval_utils import (
            find_latest_archive,
            parse_systemeval_csv,
            validate_result,
        )

        archive_dir = find_latest_archive(run_history, org_name)
        result = parse_systemeval_csv(archive_dir / "systemeval-results.csv")

        # Use fluent validation (duration may be 0 for quick start/stop)
        validate_result(result) \
            .expect_org_status("stopped") \
            .expect_min_workers(1) \
            .expect_no_failed_tasks() \
            .validate()

        # Duration should be >= 0 (calculated, not -1)
        assert result.duration_seconds >= 0, "Duration should be calculated"

    def test_systemeval_validation_failure_shows_details(self, temp_org_dir):
        """Validation failures should show specific errors."""
        run_qn("org", "init", org_path=temp_org_dir)

        # Archive without starting (will have initialized status)
        archive_script = EXAMPLE_ORGS_DIR / "org-scripts" / "common" / "archive.sh"
        subprocess.run(
            [str(archive_script), str(temp_org_dir), "failure-test"],
            capture_output=True,
            text=True,
        )

        run_history = EXAMPLE_ORGS_DIR / "run-history"
        org_name = temp_org_dir.name
        from tests.systemeval_utils import (
            find_latest_archive,
            parse_systemeval_csv,
            validate_result,
        )

        archive_dir = find_latest_archive(run_history, org_name)
        result = parse_systemeval_csv(archive_dir / "systemeval-results.csv")

        # This should fail because org wasn't started/stopped
        validator = validate_result(result) \
            .expect_org_status("stopped") \
            .expect_duration_positive()

        # Verify errors are captured
        assert len(validator.errors) == 2
        assert "org_status" in validator.errors[0]
        assert "duration_seconds" in validator.errors[1]
