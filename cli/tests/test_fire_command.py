"""
Unit tests for qn org fire command.

Tests the fire command CLI including:
- Worker lookup and termination
- Authorization (manager/CEO only)
- Work reassignment
- Session stopping
- Error cases
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from cli.commands.main import qn


@pytest.fixture
def runner():
    """Get Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_org():
    """Create temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def initialized_org(runner, temp_org):
    """Create an initialized org and return its path."""
    result = runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--ceo-name", "TestCEO"])
    if result.exit_code != 0:
        pytest.fail(f"org init failed: {result.output}")
    return temp_org


def get_ceo_worker_id(temp_org: Path) -> str:
    """Get the CEO worker ID from an initialized org."""
    from cli.core.db import open_database, get_org_db_path
    from cli.core.org import Org

    db = open_database(get_org_db_path(temp_org))
    org = Org.load(db)
    ceo_id = org.ceo_worker_id
    db.close()
    return ceo_id


def create_worker(temp_org: Path, name: str, manager_id: str) -> str:
    """Create a worker and return their ID.

    Sets up hiring authority for the manager if needed.
    """
    from cli.core.db import open_database, get_org_db_path
    from cli.core.queries import create_worker as db_create_worker, generate_id

    db = open_database(get_org_db_path(temp_org))
    try:
        # Create worker directly in database to avoid hiring authority issues
        worker_id = generate_id("wrkr")
        db_create_worker(
            db=db,
            worker_id=worker_id,
            name=name,
            role="developer",
            manager_id=manager_id,
            status="active",
            skills={},
            cost=50,
        )
        return worker_id
    finally:
        db.close()


class TestFireCommandHelp:
    """Test fire command help and arguments."""

    def test_fire_help(self, runner):
        """qn org fire --help should show usage."""
        result = runner.invoke(qn, ["org", "fire", "--help"])
        assert result.exit_code == 0
        assert "WORKER" in result.output
        assert "--reason" in result.output
        assert "--force" in result.output
        assert "--manager" in result.output

    def test_fire_requires_worker_arg(self, runner, initialized_org):
        """fire command should require worker argument."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "--reason", "Test"
        ])
        # Click exits with 2 for missing required args
        assert result.exit_code == 2
        assert "Missing argument" in result.output

    def test_fire_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "fire", "SomeWorker", "--reason", "Test"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestFireWorkerLookup:
    """Test worker lookup in fire command."""

    def test_worker_not_found(self, runner, initialized_org):
        """Should fail when worker not found."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "NonexistentWorker", "--reason", "Test", "--force"
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_cannot_fire_ceo(self, runner, initialized_org):
        """Should not allow firing the CEO."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "TestCEO", "--reason", "Test", "--force"
        ])

        assert result.exit_code != 0
        assert "Cannot terminate the CEO" in result.output


class TestFireAuthorization:
    """Test authorization checks for fire command."""

    def test_ceo_can_fire_anyone(self, runner, initialized_org):
        """CEO should be able to fire any worker."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "Alice", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Alice",
            "--reason", "Position eliminated",
            "--manager", "TestCEO",
            "--force"
        ])

        assert result.exit_code == 0
        assert "terminated" in result.output.lower()

    def test_manager_can_fire_direct_report(self, runner, initialized_org):
        """Manager should be able to fire their direct reports."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "Bob", ceo_id)

        # CEO is Bob's manager by default
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Bob",
            "--reason", "Project complete",
            "--force"
        ])

        assert result.exit_code == 0
        assert "terminated" in result.output.lower()

    def test_non_manager_cannot_fire(self, runner, initialized_org):
        """Non-manager should not be able to fire workers."""
        ceo_id = get_ceo_worker_id(initialized_org)

        # Create two workers under CEO
        worker1_id = create_worker(initialized_org, "Carol", ceo_id)
        worker2_id = create_worker(initialized_org, "Dave", ceo_id)

        # Carol trying to fire Dave should fail (Carol is not Dave's manager)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Dave",
            "--reason", "Test",
            "--manager", "Carol",
            "--force"
        ])

        assert result.exit_code != 0
        assert "cannot terminate" in result.output.lower()


class TestFireTermination:
    """Test termination process."""

    def test_terminates_worker(self, runner, initialized_org):
        """Should successfully terminate a worker."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "Eve", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Eve",
            "--reason", "Budget cuts",
            "--force"
        ])

        assert result.exit_code == 0
        assert "terminated" in result.output.lower()
        assert "Budget cuts" in result.output

        # Verify worker is actually terminated
        from cli.core.db import open_database, get_org_db_path
        from cli.core.worker import Worker

        db = open_database(get_org_db_path(initialized_org))
        try:
            worker = Worker.get(db, worker_id)
            assert worker.lifecycle_status == "terminated"
        finally:
            db.close()

    def test_already_terminated_worker(self, runner, initialized_org):
        """Should fail when trying to fire already terminated worker."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "Frank", ceo_id)

        # Fire once
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Frank",
            "--reason", "First time",
            "--force"
        ])

        # Try to fire again
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Frank",
            "--reason", "Second time",
            "--force"
        ])

        assert result.exit_code != 0
        assert "already terminated" in result.output.lower()


class TestFireReassignment:
    """Test work reassignment during termination."""

    @patch('cli.commands.org.fire._reassign_pending_work')
    def test_reassign_work_flag(self, mock_reassign, runner, initialized_org):
        """--reassign-to should trigger work reassignment."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker1_id = create_worker(initialized_org, "Grace", ceo_id)
        worker2_id = create_worker(initialized_org, "Henry", ceo_id)

        # Mock reassignment function
        mock_reassign.return_value = 0

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Grace",
            "--reason", "Restructuring",
            "--reassign-to", "Henry",
            "--force"
        ])

        assert result.exit_code == 0
        assert "Reassign work to: Henry" in result.output
        mock_reassign.assert_called_once()

    def test_reassign_to_self_fails(self, runner, initialized_org):
        """Cannot reassign work to the worker being terminated."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "Iris", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Iris",
            "--reason", "Test",
            "--reassign-to", "Iris",
            "--force"
        ])

        assert result.exit_code != 0
        assert "Cannot reassign work to the worker being terminated" in result.output

    def test_reassign_to_nonexistent_fails(self, runner, initialized_org):
        """Cannot reassign to non-existent worker."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "Jake", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Jake",
            "--reason", "Test",
            "--reassign-to", "NonexistentWorker",
            "--force"
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestFireConfirmation:
    """Test confirmation prompts."""

    def test_confirmation_prompt(self, runner, initialized_org):
        """Should prompt for confirmation without --force."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "Kim", ceo_id)

        # Answer 'n' to cancel
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Kim",
            "--reason", "Test"
        ], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output

    def test_force_skips_confirmation(self, runner, initialized_org):
        """--force should skip confirmation prompt."""
        ceo_id = get_ceo_worker_id(initialized_org)
        worker_id = create_worker(initialized_org, "Leo", ceo_id)

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "Leo",
            "--reason", "Test",
            "--force"
        ])

        assert result.exit_code == 0
        assert "terminated" in result.output.lower()
        # Should not contain confirmation prompt
        assert "Are you sure" not in result.output
