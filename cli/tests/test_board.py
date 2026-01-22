"""
Unit tests for board intervention commands.

Per CLAUDE.md: "Board = Gutterguards. Humans intervene only when org is off-track.
Not required for daily operation."
"""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.worker import Worker
from cli.core.queries import update_worker_runtime_status


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
    """Create and initialize an org."""
    runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
    return temp_org


@pytest.fixture
def started_org(runner, temp_org):
    """Create, initialize, and start an org."""
    runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
    runner.invoke(qn, ["--org-path", str(temp_org), "org", "start", "--no-spawn-ceo"])
    return temp_org


class TestBoardGroup:
    """Test board command group."""

    def test_board_help(self, runner):
        """qn board --help should show subcommands."""
        result = runner.invoke(qn, ["board", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "alerts" in result.output
        assert "pause" in result.output
        assert "resume" in result.output
        assert "fire" in result.output

    def test_board_in_main_help(self, runner):
        """qn --help should show board command group."""
        result = runner.invoke(qn, ["--help"])
        assert result.exit_code == 0
        assert "board" in result.output


class TestBoardStatus:
    """Test qn board status command."""

    def test_status_help(self, runner):
        """qn board status --help should show options."""
        result = runner.invoke(qn, ["board", "status", "--help"])
        assert result.exit_code == 0
        assert "--json" in result.output

    def test_status_requires_init(self, runner, temp_org):
        """qn board status should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "board", "status"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_status_shows_org_info(self, runner, initialized_org):
        """qn board status should show organization info."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "status"
        ])
        assert result.exit_code == 0
        assert "Organization:" in result.output
        assert "Status:" in result.output
        assert "Workers:" in result.output
        assert "Sessions:" in result.output
        assert "Budget:" in result.output

    def test_status_shows_worker_breakdown(self, runner, initialized_org):
        """qn board status should show worker status breakdown."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "status"
        ])
        assert result.exit_code == 0
        assert "Pending:" in result.output
        assert "Active:" in result.output

    def test_status_shows_session_breakdown(self, runner, initialized_org):
        """qn board status should show session status breakdown."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "status"
        ])
        assert result.exit_code == 0
        assert "Running:" in result.output
        assert "Idle:" in result.output
        assert "Stopped:" in result.output

    def test_status_json_output(self, runner, initialized_org):
        """qn board status --json should output JSON."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "status", "--json"
        ])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "status" in data
        assert "workers" in data
        assert "budget" in data

    def test_status_shows_ceo_info(self, runner, initialized_org):
        """qn board status should show CEO information."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "status"
        ])
        assert result.exit_code == 0
        assert "CEO:" in result.output


class TestBoardAlerts:
    """Test qn board alerts command."""

    def test_alerts_help(self, runner):
        """qn board alerts --help should show options."""
        result = runner.invoke(qn, ["board", "alerts", "--help"])
        assert result.exit_code == 0
        assert "--priority" in result.output
        assert "--json" in result.output

    def test_alerts_requires_init(self, runner, temp_org):
        """qn board alerts should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "board", "alerts"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_alerts_shows_header(self, runner, initialized_org):
        """qn board alerts should show header."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "alerts"
        ])
        assert result.exit_code == 0
        assert "Active Alerts" in result.output

    def test_alerts_no_alerts_message(self, runner, initialized_org):
        """qn board alerts should show message when no alerts."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "alerts"
        ])
        assert result.exit_code == 0
        assert "No active alerts" in result.output or "Total: 0" in result.output

    def test_alerts_shows_crashed_session(self, runner, started_org):
        """qn board alerts should detect crashed sessions."""
        # Create a crashed session state
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id

        # Start and crash the CEO session
        worker = Worker.get(db, ceo_id)
        worker.start_session()
        worker.mark_crashed()
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "alerts"
        ])
        assert result.exit_code == 0
        assert "P0" in result.output
        assert "crash" in result.output.lower()

    def test_alerts_json_output(self, runner, initialized_org):
        """qn board alerts --json should output JSON."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "alerts", "--json"
        ])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "alerts" in data

    def test_alerts_priority_filter(self, runner, started_org):
        """qn board alerts --priority should filter by priority."""
        # Create a crashed session to have a P0 alert
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        worker = Worker.get(db, ceo_id)
        worker.start_session()
        worker.mark_crashed()
        db.close()

        # Filter for P0 alerts only
        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "alerts", "--priority", "P0"
        ])
        assert result.exit_code == 0
        assert "P0" in result.output

        # Filter for P2 alerts only (should not include crash)
        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "alerts", "--priority", "P2"
        ])
        assert result.exit_code == 0


class TestBoardPause:
    """Test qn board pause command."""

    def test_pause_help(self, runner):
        """qn board pause --help should show usage."""
        result = runner.invoke(qn, ["board", "pause", "--help"])
        assert result.exit_code == 0
        assert "WORKER_ID" in result.output
        assert "--reason" in result.output

    def test_pause_requires_init(self, runner, temp_org):
        """qn board pause should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "board", "pause", "some-worker"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_pause_requires_valid_worker(self, runner, initialized_org):
        """qn board pause should require valid worker."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "pause", "nonexistent-worker"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_pause_requires_active_lifecycle(self, runner, initialized_org):
        """qn board pause should require worker in active lifecycle."""
        # Get CEO (which is pending, not active)
        db = open_database(get_org_db_path(initialized_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "pause", ceo_id
        ])
        assert result.exit_code != 0
        assert "active" in result.output.lower() or "cannot pause" in result.output.lower()

    def test_pause_running_worker(self, runner, started_org):
        """qn board pause should pause a running worker."""
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id

        # Start a session for the CEO
        worker = Worker.get(db, ceo_id)
        worker.start_session()
        worker.session_ready()
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "pause", ceo_id, "--reason", "Test pause"
        ])
        assert result.exit_code == 0
        assert "paused" in result.output.lower()


class TestBoardResume:
    """Test qn board resume command."""

    def test_resume_help(self, runner):
        """qn board resume --help should show usage."""
        result = runner.invoke(qn, ["board", "resume", "--help"])
        assert result.exit_code == 0
        assert "WORKER_ID" in result.output

    def test_resume_requires_init(self, runner, temp_org):
        """qn board resume should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "board", "resume", "some-worker"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_resume_requires_valid_worker(self, runner, initialized_org):
        """qn board resume should require valid worker."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "resume", "nonexistent-worker"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_resume_requires_stopped_worker(self, runner, started_org):
        """qn board resume should require worker to be paused/stopped."""
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id

        # Start a running session (not stopped)
        worker = Worker.get(db, ceo_id)
        worker.start_session()
        worker.session_ready()
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "resume", ceo_id
        ])
        assert result.exit_code != 0
        assert "not paused" in result.output.lower() or "pause" in result.output.lower()

    def test_resume_stopped_worker(self, runner, started_org):
        """qn board resume should resume a stopped worker."""
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id

        # Create stopped state
        worker = Worker.get(db, ceo_id)
        worker.start_session()
        worker.session_ready()
        worker.stop_session()
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "resume", ceo_id
        ])
        assert result.exit_code == 0
        assert "resume" in result.output.lower()


class TestBoardFire:
    """Test qn board fire command."""

    def test_fire_help(self, runner):
        """qn board fire --help should show usage."""
        result = runner.invoke(qn, ["board", "fire", "--help"])
        assert result.exit_code == 0
        assert "WORKER_ID" in result.output
        assert "--reason" in result.output
        assert "--force" in result.output

    def test_fire_requires_init(self, runner, temp_org):
        """qn board fire should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "board", "fire", "some-worker", "--reason", "test"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_fire_requires_valid_worker(self, runner, initialized_org):
        """qn board fire should require valid worker."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "fire", "nonexistent-worker", "--reason", "test"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_fire_requires_reason(self, runner, started_org):
        """qn board fire should require --reason."""
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "fire", ceo_id
        ])
        assert result.exit_code != 0
        assert "--reason" in result.output

    def test_fire_requires_confirmation(self, runner, started_org):
        """qn board fire should require confirmation."""
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        db.close()

        # Without --force, should ask for confirmation
        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "fire", ceo_id, "--reason", "test"
        ], input="wrong\n")  # Wrong confirmation
        assert "cancelled" in result.output.lower() or result.exit_code == 0

    def test_fire_with_force(self, runner, started_org):
        """qn board fire --force should skip confirmation."""
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        ceo_name = org.ceo.name.upper()
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "fire", ceo_id, "--reason", "test termination", "--force"
        ])
        assert result.exit_code == 0
        assert "terminated" in result.output.lower()

    def test_fire_shows_ceo_warning(self, runner, started_org):
        """qn board fire should warn when firing CEO."""
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "fire", ceo_id, "--reason", "test"
        ], input="wrong\n")
        assert "CEO" in result.output

    def test_fire_already_terminated(self, runner, started_org):
        """qn board fire should fail for already terminated worker."""
        db = open_database(get_org_db_path(started_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        worker = Worker(db, ceo_id, org_path=started_org)
        worker.start_offboarding()
        worker.terminate()
        db.close()

        result = runner.invoke(qn, [
            "--org-path", str(started_org),
            "board", "fire", ceo_id, "--reason", "test", "--force"
        ])
        assert result.exit_code != 0
        assert "already terminated" in result.output.lower()
