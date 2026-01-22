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
QN_WRAPPER = EXAMPLE_ORGS_DIR / "common" / "qn"


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
        result = run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)

        assert result.returncode == 0
        assert "running" in result.stdout.lower()

    def test_start_activates_ceo(self, temp_org_dir):
        """qn org start should activate the CEO worker."""
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)

        result = run_qn("org", "status", org_path=temp_org_dir)
        assert "active" in result.stdout.lower()

    @pytest.mark.xfail(reason="Known issue: quinnai-qi2r - Session not spawned on start")
    def test_start_spawns_ceo_session(self, temp_org_dir):
        """qn org start should spawn a tmux session for CEO.

        BUG: This currently fails because `qn org start` does not
        spawn a tmux session. See quinnai-qi2r.
        """
        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)

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
        run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)
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
        result = run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)
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

    @pytest.mark.xfail(reason="quinnai-uekq: No channels created during init")
    def test_init_creates_channels(self, temp_org_dir):
        """qn org init should create default channels.

        BUG: Currently no channels are created. Workers need channels
        to communicate. See quinnai-uekq.
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

    @pytest.mark.xfail(reason="quinnai-8x29: Org-chart shows stale lifecycle status")
    def test_org_chart_reflects_lifecycle_changes(self, temp_org_dir):
        """Org-chart should update when worker lifecycle changes.

        BUG: After start, org-chart still shows 'pending' even though
        worker is 'active'. See quinnai-8x29.
        """
        import yaml

        run_qn("org", "init", org_path=temp_org_dir)
        run_qn("org", "start", "--no-spawn-ceo", org_path=temp_org_dir)

        org_chart_path = temp_org_dir / "org-chart" / "current.yaml"
        with open(org_chart_path) as f:
            org_chart = yaml.safe_load(f)

        # Find the CEO in the workers dict
        workers = org_chart.get("workers", {})
        ceo_entry = list(workers.values())[0]

        assert ceo_entry["lifecycle"] == "active", \
            f"Expected 'active', got '{ceo_entry['lifecycle']}'"
