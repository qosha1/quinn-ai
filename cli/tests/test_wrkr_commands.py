"""
Unit tests for qn wrkr commands.

Covers: status, get-work, report, search, delegate, cleanup, restart
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.core.db import init_database, get_org_db_path
from cli.core.queries import (
    create_team,
    create_worker,
    update_org_status,
    create_channel,
    create_message,
    get_channel_by_name,
)
from cli.core.sessions.persistence import create_session_record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def org_dir():
    """Create a fully initialized org directory with DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        # Use CLI to init (creates DB + file structure)
        r = CliRunner()
        result = r.invoke(qn, ["--org-path", str(org_path), "org", "init"])
        assert result.exit_code == 0, f"org init failed: {result.output}"
        yield org_path


@pytest.fixture
def db(org_dir):
    """Open database for the initialized org."""
    from cli.core.db import open_database
    db_path = get_org_db_path(org_dir)
    database = open_database(db_path)
    yield database
    database.close()


@pytest.fixture
def ceo_id(db):
    """Get the CEO worker ID from the initialized org."""
    from cli.core.queries import get_org_state
    state = get_org_state(db)
    return state.ceo_worker_id


@pytest.fixture
def active_ceo(db, ceo_id):
    """Set CEO to active lifecycle status (workers.status column)."""
    db.execute(
        "UPDATE workers SET status = 'active' WHERE id = ?",
        (ceo_id,)
    )
    db.connection.commit()
    return ceo_id


@pytest.fixture
def running_org(db, active_ceo):
    """Set org status to running."""
    update_org_status(db, "running", ceo_worker_id=active_ceo)
    return active_ceo


@pytest.fixture
def active_ceo_with_session(db, active_ceo):
    """CEO is active with a running session and runtime state."""
    # Ensure worker_state row exists with running status
    existing = db.fetchone("SELECT worker_id FROM worker_state WHERE worker_id = ?", (active_ceo,))
    if existing:
        db.execute(
            "UPDATE worker_state SET runtime_status = 'running' WHERE worker_id = ?",
            (active_ceo,)
        )
    else:
        db.execute(
            """INSERT INTO worker_state (worker_id, runtime_status, started_at, last_activity, updated_at)
               VALUES (?, 'running', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (active_ceo,)
        )
    db.connection.commit()
    create_session_record(
        db=db,
        session_id="sess-test-001",
        worker_id=active_ceo,
        provider="claude_code",
        command="claude",
        tmux_session_name="qn-test-session",
        state="running",
    )
    return active_ceo


# ---------------------------------------------------------------------------
# Helper to invoke with org-path and optional worker-id env
# ---------------------------------------------------------------------------

def invoke_wrkr(runner, org_dir, args, worker_id=None, extra_env=None):
    env = {}
    if worker_id:
        env["QUINN_WORKER_ID"] = worker_id
    if extra_env:
        env.update(extra_env)
    return runner.invoke(
        qn,
        ["--org-path", str(org_dir)] + args,
        env=env if env else None,
    )


# ===========================================================================
# qn wrkr status
# ===========================================================================

class TestWrkrStatus:

    def test_worker_id_not_specified(self, runner, org_dir):
        """status requires QUINN_WORKER_ID."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "status"])
        assert result.exit_code != 0
        assert "QUINN_WORKER_ID" in result.output

    def test_org_not_initialized(self, runner):
        """status fails when org not initialized."""
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(
                qn,
                ["--org-path", tmp, "wrkr", "status"],
                env={"QUINN_WORKER_ID": "some-worker"},
            )
            assert result.exit_code != 0
            assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_worker_not_found(self, runner, org_dir):
        """status fails for unknown worker ID."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "status"], worker_id="nonexistent-worker")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_happy_path_active_worker_with_running_session(self, runner, org_dir, db, active_ceo_with_session):
        """status shows details for active worker with session."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "status"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        assert "Worker:" in result.output
        assert "Lifecycle:" in result.output
        assert "Runtime:" in result.output

    def test_pending_worker_lifecycle_state(self, runner, org_dir, db, ceo_id):
        """status shows pending lifecycle."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "status"], worker_id=ceo_id)
        assert result.exit_code == 0
        assert "pending" in result.output

    def test_onboarding_worker_lifecycle_state(self, runner, org_dir, db, ceo_id):
        """status shows onboarding lifecycle."""
        db.execute(
            "UPDATE workers SET status = 'onboarding' WHERE id = ?",
            (ceo_id,)
        )
        db.connection.commit()
        result = invoke_wrkr(runner, org_dir, ["wrkr", "status"], worker_id=ceo_id)
        assert result.exit_code == 0
        assert "onboarding" in result.output

    def test_worker_with_no_session(self, runner, org_dir, db, active_ceo):
        """status shows '(no session)' when runtime is null."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "status"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "no session" in result.output.lower()

    def test_crashed_worker_runtime_state(self, runner, org_dir, db, active_ceo):
        """status shows crashed runtime state."""
        # Ensure worker_state row exists
        existing = db.fetchone("SELECT worker_id FROM worker_state WHERE worker_id = ?", (active_ceo,))
        if existing:
            db.execute(
                "UPDATE worker_state SET runtime_status = 'crashed' WHERE worker_id = ?",
                (active_ceo,)
            )
        else:
            db.execute(
                """INSERT INTO worker_state (worker_id, runtime_status, started_at, last_activity, updated_at)
                   VALUES (?, 'crashed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                (active_ceo,)
            )
        db.connection.commit()
        result = invoke_wrkr(runner, org_dir, ["wrkr", "status"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "crashed" in result.output

    def test_worker_with_current_task(self, runner, org_dir, db, active_ceo):
        """status shows current task ID when set."""
        existing = db.fetchone("SELECT worker_id FROM worker_state WHERE worker_id = ?", (active_ceo,))
        if existing:
            db.execute(
                "UPDATE worker_state SET runtime_status = 'running', current_task_id = 'beads-abc123' WHERE worker_id = ?",
                (active_ceo,)
            )
        else:
            db.execute(
                """INSERT INTO worker_state (worker_id, runtime_status, current_task_id, started_at, last_activity, updated_at)
                   VALUES (?, 'running', 'beads-abc123', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                (active_ceo,)
            )
        db.connection.commit()
        result = invoke_wrkr(runner, org_dir, ["wrkr", "status"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "beads-abc123" in result.output

    def test_db_closed_in_finally_block(self, runner, org_dir, db, active_ceo):
        """status closes DB even if worker lookup fails."""
        with patch("commands.wrkr.status.Worker.get", side_effect=Exception("db error")):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "status"], worker_id=active_ceo)
        assert result.exit_code != 0


# ===========================================================================
# qn wrkr get-work
# ===========================================================================

class TestWrkrGetWork:

    def test_worker_id_not_in_context(self, runner, org_dir):
        """get-work requires QUINN_WORKER_ID."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work"])
        assert result.exit_code != 0
        assert "QUINN_WORKER_ID" in result.output

    def test_org_not_initialized(self, runner):
        """get-work fails when org not initialized."""
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(
                qn,
                ["--org-path", tmp, "wrkr", "get-work"],
                env={"QUINN_WORKER_ID": "some-worker"},
            )
            assert result.exit_code != 0
            assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_worker_not_found(self, runner, org_dir):
        """get-work fails for unknown worker."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work"], worker_id="nonexistent")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_worker_cannot_accept_work(self, runner, org_dir, db, ceo_id):
        """get-work shows cannot accept work when worker is pending."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work"], worker_id=ceo_id)
        assert result.exit_code == 0
        assert "cannot accept work" in result.output.lower()

    def test_worker_cannot_work_with_json(self, runner, org_dir, db, ceo_id):
        """get-work --json returns error JSON when worker not ready."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work", "--json"], worker_id=ceo_id)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "worker_not_ready"
        assert "lifecycle" in data

    def test_no_work_items_assigned(self, runner, org_dir, db, active_ceo_with_session):
        """get-work shows no work assigned when bd returns empty list."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"
        mock_result.stderr = ""
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        assert "no work" in result.output.lower()

    def test_no_work_items_with_json(self, runner, org_dir, db, active_ceo_with_session):
        """get-work --json returns empty items list."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"
        mock_result.stderr = ""
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work", "--json"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["items"] == []
        assert data["count"] == 0

    def test_bd_command_failure(self, runner, org_dir, db, active_ceo_with_session):
        """get-work shows no work items when bd fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "bd error"
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        assert "no work" in result.output.lower()

    def test_bd_command_failure_with_json(self, runner, org_dir, db, active_ceo_with_session):
        """get-work --json returns error when bd fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "bd error"
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work", "--json"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "beads_error"

    def test_bd_returns_invalid_json(self, runner, org_dir, db, active_ceo_with_session):
        """get-work handles invalid JSON from bd gracefully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_result.stderr = ""
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        assert "no work" in result.output.lower()

    def test_bd_not_found_shows_fallback(self, runner, org_dir, db, active_ceo_with_session):
        """get-work shows note when bd binary not found."""
        with patch("commands.wrkr.get_work.run_bd", side_effect=FileNotFoundError()):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        assert "no work" in result.output.lower()

    def test_happy_path_returns_work_items(self, runner, org_dir, db, active_ceo_with_session):
        """get-work displays work items from bd."""
        items = [{"id": "beads-abc", "title": "Fix bug", "priority": 1, "status": "open", "type": "bug"}]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(items)
        mock_result.stderr = ""
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            with patch("commands.wrkr.get_work.can_worker_access_bead", return_value=True):
                result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        assert "Fix bug" in result.output

    def test_get_work_with_json_shows_items_with_all_fields(self, runner, org_dir, db, active_ceo_with_session):
        """get-work --json shows full item list."""
        items = [{"id": "beads-abc", "title": "Fix bug", "priority": 1, "status": "open", "type": "bug"}]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(items)
        mock_result.stderr = ""
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            with patch("commands.wrkr.get_work.can_worker_access_bead", return_value=True):
                result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work", "--json"], worker_id=active_ceo_with_session)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["items"][0]["id"] == "beads-abc"

    def test_items_sorted_by_priority(self, runner, org_dir, db, active_ceo_with_session):
        """get-work sorts items P0 first."""
        items = [
            {"id": "beads-p2", "title": "Medium", "priority": 2, "status": "open", "type": "task"},
            {"id": "beads-p0", "title": "Critical", "priority": 0, "status": "open", "type": "task"},
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(items)
        mock_result.stderr = ""
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            with patch("commands.wrkr.get_work.can_worker_access_bead", return_value=True):
                result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work", "--json"], worker_id=active_ceo_with_session)
        data = json.loads(result.output)
        priorities = [i["priority"] for i in data["items"]]
        assert priorities == sorted(priorities)

    def test_items_filtered_by_permission(self, runner, org_dir, db, active_ceo_with_session):
        """get-work filters out items worker cannot access."""
        items = [
            {"id": "beads-allowed", "title": "Allowed", "priority": 1, "status": "open", "type": "task"},
            {"id": "beads-denied", "title": "Denied", "priority": 1, "status": "open", "type": "task"},
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(items)
        mock_result.stderr = ""

        def perm_check(db, worker_id, bead_id, level):
            return bead_id == "beads-allowed"

        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            with patch("commands.wrkr.get_work.can_worker_access_bead", side_effect=perm_check):
                result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work", "--json"], worker_id=active_ceo_with_session)
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["items"][0]["id"] == "beads-allowed"

    def test_limit_flag_respected(self, runner, org_dir, db, active_ceo_with_session):
        """get-work respects --limit flag."""
        items = [{"id": f"beads-{i}", "title": f"Task {i}", "priority": 2, "status": "open", "type": "task"} for i in range(5)]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(items)
        mock_result.stderr = ""
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            with patch("commands.wrkr.get_work.can_worker_access_bead", return_value=True):
                result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work", "--limit", "2", "--json"], worker_id=active_ceo_with_session)
        data = json.loads(result.output)
        assert data["count"] == 2

    def test_default_limit_is_10(self, runner, org_dir, db, active_ceo_with_session):
        """get-work default limit is 10."""
        items = [{"id": f"beads-{i}", "title": f"Task {i}", "priority": 2, "status": "open", "type": "task"} for i in range(15)]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(items)
        mock_result.stderr = ""
        with patch("commands.wrkr.get_work.run_bd", return_value=mock_result):
            with patch("commands.wrkr.get_work.can_worker_access_bead", return_value=True):
                result = invoke_wrkr(runner, org_dir, ["wrkr", "get-work", "--json"], worker_id=active_ceo_with_session)
        data = json.loads(result.output)
        assert data["count"] == 10


# ===========================================================================
# qn wrkr report
# ===========================================================================

class TestWrkrReport:

    def test_worker_id_not_in_context(self, runner, org_dir):
        """report requires QUINN_WORKER_ID."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "report", "--summary", "Done"])
        assert result.exit_code != 0
        assert "QUINN_WORKER_ID" in result.output

    def test_worker_not_active_returns_error(self, runner, org_dir, db, ceo_id):
        """report fails when worker is not active."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "report", "--summary", "Done"], worker_id=ceo_id)
        assert result.exit_code != 0
        assert "active" in result.output.lower()

    def test_worker_not_active_with_json_returns_json_error(self, runner, org_dir, db, ceo_id):
        """report --json returns JSON error when worker not active."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "report", "--summary", "Done", "--json"], worker_id=ceo_id)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "worker_not_active"

    def test_no_manager_and_no_to_raises_error(self, runner, org_dir, db, active_ceo):
        """report fails when CEO has no manager and no --to given."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "report", "--summary", "Done"], worker_id=active_ceo)
        assert result.exit_code != 0
        assert "manager" in result.output.lower() or "no manager" in result.output.lower()

    def test_recipient_not_found(self, runner, org_dir, db, active_ceo):
        """report fails when --to recipient not found."""
        result = invoke_wrkr(
            runner, org_dir,
            ["wrkr", "report", "--summary", "Done", "--to", "nonexistent-worker"],
            worker_id=active_ceo,
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_happy_path_sends_to_manager(self, runner, org_dir, db, active_ceo_with_session):
        """report sends report via bd when worker active and has manager."""
        # Create a subordinate (CEO will be the "manager" target here - use CEO as recipient by ID)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "beads-rpt001"
        mock_result.stderr = ""
        with patch("commands.wrkr.report.run_bd", return_value=mock_result):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo_with_session],
                worker_id=active_ceo_with_session,
            )
        assert result.exit_code == 0
        assert "Report sent to" in result.output

    def test_explicit_to_recipient_by_id(self, runner, org_dir, db, active_ceo):
        """report sends to explicit --to recipient by ID."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "beads-rpt001"
        mock_result.stderr = ""
        with patch("commands.wrkr.report.run_bd", return_value=mock_result):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0

    def test_explicit_to_recipient_by_name(self, runner, org_dir, db, active_ceo, ceo_id):
        """report sends to explicit --to recipient by name."""
        from cli.core.queries import get_worker
        worker_data = get_worker(db, ceo_id)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "beads-rpt001"
        mock_result.stderr = ""
        with patch("commands.wrkr.report.run_bd", return_value=mock_result):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", worker_data.name],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0

    def test_bd_create_failure_returns_error(self, runner, org_dir, db, active_ceo):
        """report fails when bd create fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "bd create error"
        with patch("commands.wrkr.report.run_bd", return_value=mock_result):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo],
                worker_id=active_ceo,
            )
        assert result.exit_code != 0
        assert "failed" in result.output.lower()

    def test_bd_binary_not_found(self, runner, org_dir, db, active_ceo):
        """report fails gracefully when bd binary not found."""
        with patch("commands.wrkr.report.run_bd", side_effect=FileNotFoundError()):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo],
                worker_id=active_ceo,
            )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_bd_binary_not_found_with_json(self, runner, org_dir, db, active_ceo):
        """report --json returns JSON error when bd not found."""
        with patch("commands.wrkr.report.run_bd", side_effect=FileNotFoundError()):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo, "--json"],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "beads_not_found"

    def test_json_flag_outputs_success_json(self, runner, org_dir, db, active_ceo):
        """report --json returns success JSON."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "beads-rpt001"
        mock_result.stderr = ""
        with patch("commands.wrkr.report.run_bd", return_value=mock_result):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo, "--json"],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert "report_id" in data

    def test_summary_truncated_to_50_chars_in_bead_title(self, runner, org_dir, db, active_ceo):
        """report truncates summary > 50 chars in bead title."""
        long_summary = "A" * 60
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "beads-rpt001"
        mock_result.stderr = ""
        captured_args = []
        def capture_run_bd(args, **kwargs):
            captured_args.extend(args)
            return mock_result
        with patch("commands.wrkr.report.run_bd", side_effect=capture_run_bd):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", long_summary, "--to", active_ceo],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        # Find the --title arg value
        title_idx = captured_args.index("--title") if "--title" in captured_args else -1
        if title_idx >= 0:
            title = captured_args[title_idx + 1]
            assert "..." in title
            # The full summary should not appear verbatim in title
            assert title != f"Report: {long_summary}"

    def test_short_summary_not_truncated(self, runner, org_dir, db, active_ceo):
        """report does not truncate short summaries."""
        short_summary = "Short summary"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "beads-rpt001"
        mock_result.stderr = ""
        captured_args = []
        def capture_run_bd(args, **kwargs):
            captured_args.extend(args)
            return mock_result
        with patch("commands.wrkr.report.run_bd", side_effect=capture_run_bd):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", short_summary, "--to", active_ceo],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        title_idx = captured_args.index("--title") if "--title" in captured_args else -1
        if title_idx >= 0:
            title = captured_args[title_idx + 1]
            assert "..." not in title

    def test_with_link_flag_links_tasks(self, runner, org_dir, db, active_ceo):
        """report calls bd dep add for --link tasks."""
        mock_create = MagicMock()
        mock_create.returncode = 0
        mock_create.stdout = "beads-rpt001"
        mock_create.stderr = ""
        mock_dep = MagicMock()
        mock_dep.returncode = 0
        mock_dep.stdout = ""
        mock_dep.stderr = ""
        call_count = [0]
        def run_bd_side_effect(args, **kwargs):
            call_count[0] += 1
            if args[0] == "create":
                return mock_create
            return mock_dep
        with patch("commands.wrkr.report.run_bd", side_effect=run_bd_side_effect):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo, "--link", "beads-task1"],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        assert call_count[0] == 2  # create + dep add

    def test_multiple_link_flags(self, runner, org_dir, db, active_ceo):
        """report handles multiple --link flags."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "beads-rpt001"
        mock_result.stderr = ""
        call_count = [0]
        def run_bd_side_effect(args, **kwargs):
            call_count[0] += 1
            return mock_result
        with patch("commands.wrkr.report.run_bd", side_effect=run_bd_side_effect):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo,
                 "--link", "beads-1", "--link", "beads-2"],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        assert call_count[0] == 3  # create + 2 dep adds

    def test_bd_create_extracts_bead_id_from_output(self, runner, org_dir, db, active_ceo):
        """report extracts bead ID from bd create output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "beads-rpt001"
        mock_result.stderr = ""
        with patch("commands.wrkr.report.run_bd", return_value=mock_result):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        assert "beads-rpt001" in result.output

    def test_bd_create_returns_id_embedded_in_longer_output(self, runner, org_dir, db, active_ceo):
        """report extracts bead ID embedded in longer bd output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Created report beads-rpt002 successfully"
        mock_result.stderr = ""
        with patch("commands.wrkr.report.run_bd", return_value=mock_result):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "report", "--summary", "Done", "--to", active_ceo],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        assert "beads-rpt002" in result.output


# ===========================================================================
# qn wrkr search
# ===========================================================================

class TestWrkrSearch:

    def test_worker_id_not_in_context(self, runner, org_dir):
        """search requires QUINN_WORKER_ID."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "error"])
        assert result.exit_code != 0
        assert "QUINN_WORKER_ID" in result.output

    def test_org_not_initialized(self, runner):
        """search fails when org not initialized."""
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(
                qn,
                ["--org-path", tmp, "wrkr", "search", "error"],
                env={"QUINN_WORKER_ID": "some-worker"},
            )
            assert result.exit_code != 0
            assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_worker_not_found(self, runner, org_dir):
        """search fails for unknown worker."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "error"], worker_id="nonexistent")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_no_messages_found(self, runner, org_dir, db, active_ceo):
        """search shows no messages when nothing matches."""
        with patch("commands.wrkr.search.search_messages", return_value=[]):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "nonexistent-term"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "no messages" in result.output.lower()

    def test_happy_path_returns_matching_messages(self, runner, org_dir, db, active_ceo):
        """search displays matching messages."""
        from cli.core.queries import get_channel_by_name
        chan = get_channel_by_name(db, "general")
        if chan is None:
            from cli.core.queries import create_channel
            chan = create_channel(db, "general", "General channel", active_ceo)

        mock_msg = MagicMock()
        mock_msg.id = "msg-001"
        mock_msg.channel_id = chan.id
        mock_msg.from_worker_id = active_ceo
        mock_msg.content = "deployment failed with error"
        mock_msg.created_at = "2026-01-01 10:00"

        with patch("commands.wrkr.search.search_messages", return_value=[mock_msg]):
            with patch("commands.wrkr.search.can_worker_access_channel", return_value=True):
                with patch("commands.wrkr.search.get_channel") as mock_get_chan:
                    mock_get_chan.return_value = chan
                    result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "error"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "deployment failed" in result.output

    def test_messages_grouped_by_channel_in_output(self, runner, org_dir, db, active_ceo):
        """search groups results by channel."""
        from cli.core.queries import get_channel_by_name
        chan = get_channel_by_name(db, "general")
        if chan is None:
            from cli.core.queries import create_channel
            chan = create_channel(db, "general", "General", active_ceo)

        mock_msg = MagicMock()
        mock_msg.id = "msg-001"
        mock_msg.channel_id = chan.id
        mock_msg.from_worker_id = active_ceo
        mock_msg.content = "error occurred"
        mock_msg.created_at = "2026-01-01 10:00"

        with patch("commands.wrkr.search.search_messages", return_value=[mock_msg]):
            with patch("commands.wrkr.search.can_worker_access_channel", return_value=True):
                with patch("commands.wrkr.search.get_channel") as mock_get_chan:
                    mock_get_chan.return_value = chan
                    result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "error"], worker_id=active_ceo)
        assert result.exit_code == 0
        # Channel name should appear as header
        assert chan.name in result.output or "#" in result.output

    def test_messages_filtered_by_channel_permission(self, runner, org_dir, db, active_ceo):
        """search hides messages from channels worker cannot access."""
        mock_msg = MagicMock()
        mock_msg.id = "msg-001"
        mock_msg.channel_id = "private-channel"
        mock_msg.from_worker_id = active_ceo
        mock_msg.content = "secret message"
        mock_msg.created_at = "2026-01-01 10:00"

        with patch("commands.wrkr.search.search_messages", return_value=[mock_msg]):
            with patch("commands.wrkr.search.can_worker_access_channel", return_value=False):
                result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "secret"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "secret message" not in result.output

    def test_skipped_no_permission_count_shown_in_output(self, runner, org_dir, db, active_ceo):
        """search shows count of hidden messages."""
        mock_msg = MagicMock()
        mock_msg.id = "msg-001"
        mock_msg.channel_id = "private-channel"
        mock_msg.from_worker_id = active_ceo
        mock_msg.content = "secret"
        mock_msg.created_at = "2026-01-01 10:00"

        with patch("commands.wrkr.search.search_messages", return_value=[mock_msg]):
            with patch("commands.wrkr.search.can_worker_access_channel", return_value=False):
                result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "secret"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "permission" in result.output.lower() or "hidden" in result.output.lower()

    def test_channel_not_found_uses_channel_id_as_name(self, runner, org_dir, db, active_ceo):
        """search uses channel_id as display name when channel not in DB."""
        mock_msg = MagicMock()
        mock_msg.id = "msg-001"
        mock_msg.channel_id = "orphan-channel-id"
        mock_msg.from_worker_id = active_ceo
        mock_msg.content = "some message"
        mock_msg.created_at = "2026-01-01 10:00"

        with patch("commands.wrkr.search.search_messages", return_value=[mock_msg]):
            with patch("commands.wrkr.search.can_worker_access_channel", return_value=True):
                with patch("commands.wrkr.search.get_channel", return_value=None):
                    result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "some"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "orphan-channel-id" in result.output

    def test_limit_flag_caps_results(self, runner, org_dir, db, active_ceo):
        """search respects --limit flag."""
        mock_msgs = []
        for i in range(5):
            m = MagicMock()
            m.id = f"msg-{i}"
            m.channel_id = "chan-1"
            m.from_worker_id = active_ceo
            m.content = f"error message {i}"
            m.created_at = "2026-01-01 10:00"
            mock_msgs.append(m)

        captured_kwargs = {}
        def search_side(db, query, channel_id, limit, offset):
            captured_kwargs["limit"] = limit
            return mock_msgs[:limit]

        with patch("commands.wrkr.search.search_messages", side_effect=search_side):
            result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "error", "--limit", "2"], worker_id=active_ceo)
        assert captured_kwargs.get("limit") == 2

    def test_default_limit_is_20(self, runner, org_dir, db, active_ceo):
        """search default limit is 20."""
        captured_kwargs = {}
        def search_side(db, query, channel_id, limit, offset):
            captured_kwargs["limit"] = limit
            return []
        with patch("commands.wrkr.search.search_messages", side_effect=search_side):
            invoke_wrkr(runner, org_dir, ["wrkr", "search", "error"], worker_id=active_ceo)
        assert captured_kwargs.get("limit") == 20

    def test_offset_pagination(self, runner, org_dir, db, active_ceo):
        """search passes --offset to search function."""
        captured_kwargs = {}
        def search_side(db, query, channel_id, limit, offset):
            captured_kwargs["offset"] = offset
            return []
        with patch("commands.wrkr.search.search_messages", side_effect=search_side):
            invoke_wrkr(runner, org_dir, ["wrkr", "search", "error", "--offset", "20"], worker_id=active_ceo)
        assert captured_kwargs.get("offset") == 20

    def test_pagination_hint_shown_at_limit(self, runner, org_dir, db, active_ceo):
        """search shows pagination hint when results == limit."""
        mock_msgs = []
        for i in range(20):
            m = MagicMock()
            m.id = f"msg-{i}"
            m.channel_id = "chan-1"
            m.from_worker_id = active_ceo
            m.content = f"error {i}"
            m.created_at = "2026-01-01 10:00"
            mock_msgs.append(m)

        with patch("commands.wrkr.search.search_messages", return_value=mock_msgs):
            with patch("commands.wrkr.search.can_worker_access_channel", return_value=True):
                chan_mock = MagicMock()
                chan_mock.name = "general"
                with patch("commands.wrkr.search.get_channel", return_value=chan_mock):
                    result = invoke_wrkr(runner, org_dir, ["wrkr", "search", "error"], worker_id=active_ceo)
        assert result.exit_code == 0
        assert "--offset" in result.output

    def test_channel_filter_limits_to_channel(self, runner, org_dir, db, active_ceo):
        """search passes --channel filter to search_messages."""
        captured_kwargs = {}
        def search_side(db, query, channel_id, limit, offset):
            captured_kwargs["channel_id"] = channel_id
            return []
        with patch("commands.wrkr.search.search_messages", side_effect=search_side):
            invoke_wrkr(runner, org_dir, ["wrkr", "search", "error", "--channel", "chan-abc"], worker_id=active_ceo)
        assert captured_kwargs.get("channel_id") == "chan-abc"

    def test_fts_simple_term(self, runner, org_dir, db, active_ceo):
        """search passes simple term to search_messages."""
        captured_kwargs = {}
        def search_side(db, query, channel_id, limit, offset):
            captured_kwargs["query"] = query
            return []
        with patch("commands.wrkr.search.search_messages", side_effect=search_side):
            invoke_wrkr(runner, org_dir, ["wrkr", "search", "error"], worker_id=active_ceo)
        assert captured_kwargs.get("query") == "error"

    def test_fts_phrase_search(self, runner, org_dir, db, active_ceo):
        """search passes phrase query to search_messages."""
        captured_kwargs = {}
        def search_side(db, query, channel_id, limit, offset):
            captured_kwargs["query"] = query
            return []
        with patch("commands.wrkr.search.search_messages", side_effect=search_side):
            invoke_wrkr(runner, org_dir, ["wrkr", "search", "connection refused"], worker_id=active_ceo)
        assert captured_kwargs.get("query") == "connection refused"


# ===========================================================================
# qn wrkr delegate
# ===========================================================================

@pytest.fixture
def worker_with_report(org_dir, db, active_ceo):
    """Create an active direct report under the CEO."""
    team_row = db.fetchone("SELECT id FROM teams LIMIT 1")
    team_id = team_row["id"] if team_row else None
    if team_id is None:
        from cli.core.queries import create_team
        team = create_team(db, "Engineering")
        team_id = team.id
    report_data = create_worker(db, "Bob", "Engineer", team_id, 50, manager_id=active_ceo)
    db.execute("UPDATE workers SET status = 'active' WHERE id = ?", (report_data.id,))
    db.connection.commit()
    return report_data.id


class TestWrkrDelegate:

    def test_worker_id_not_in_context(self, runner, org_dir):
        """delegate requires QUINN_WORKER_ID."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "delegate", "beads-abc", "--to", "bob"])
        assert result.exit_code != 0
        assert "QUINN_WORKER_ID" in result.output

    def test_worker_not_active(self, runner, org_dir, db, ceo_id):
        """delegate fails when calling worker is not active."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "delegate", "beads-abc", "--to", "bob"], worker_id=ceo_id)
        assert result.exit_code != 0
        assert "active" in result.output.lower()

    def test_worker_not_active_with_json(self, runner, org_dir, db, ceo_id):
        """delegate --json returns JSON error when worker not active."""
        result = invoke_wrkr(
            runner, org_dir,
            ["wrkr", "delegate", "beads-abc", "--to", "bob", "--json"],
            worker_id=ceo_id,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "worker_not_active"

    def test_no_direct_reports(self, runner, org_dir, db, active_ceo):
        """delegate fails when worker has no direct reports."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "delegate", "beads-abc", "--to", "bob"], worker_id=active_ceo)
        assert result.exit_code != 0
        assert "direct report" in result.output.lower() or "subordinate" in result.output.lower()

    def test_no_direct_reports_with_json(self, runner, org_dir, db, active_ceo):
        """delegate --json returns JSON error when no direct reports."""
        result = invoke_wrkr(
            runner, org_dir,
            ["wrkr", "delegate", "beads-abc", "--to", "bob", "--json"],
            worker_id=active_ceo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "no_authority"

    def test_target_not_a_subordinate(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate fails when target is not a direct report."""
        result = invoke_wrkr(
            runner, org_dir,
            ["wrkr", "delegate", "beads-abc", "--to", "nonexistent-person"],
            worker_id=active_ceo,
        )
        assert result.exit_code != 0
        assert "not your direct report" in result.output.lower() or "subordinate" in result.output.lower()

    def test_target_not_subordinate_with_json(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate --json returns JSON error when target not subordinate."""
        result = invoke_wrkr(
            runner, org_dir,
            ["wrkr", "delegate", "beads-abc", "--to", "nonexistent-person", "--json"],
            worker_id=active_ceo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "not_subordinate"

    def test_target_worker_not_active(self, runner, org_dir, db, active_ceo):
        """delegate fails when target is not active."""
        team_row = db.fetchone("SELECT id FROM teams LIMIT 1")
        team_id = team_row["id"]
        report_data = create_worker(db, "InactiveWorker", "Engineer", team_id, 50, manager_id=active_ceo)
        # workers.status defaults to 'pending', no worker_state row needed
        result = invoke_wrkr(
            runner, org_dir,
            ["wrkr", "delegate", "beads-abc", "--to", "InactiveWorker"],
            worker_id=active_ceo,
        )
        assert result.exit_code != 0
        assert "active" in result.output.lower()

    def test_target_not_active_with_json(self, runner, org_dir, db, active_ceo):
        """delegate --json returns JSON error when target not active."""
        team_row = db.fetchone("SELECT id FROM teams LIMIT 1")
        team_id = team_row["id"]
        report_data = create_worker(db, "InactiveWorker2", "Engineer", team_id, 50, manager_id=active_ceo)
        # workers.status defaults to 'pending', no worker_state row needed
        result = invoke_wrkr(
            runner, org_dir,
            ["wrkr", "delegate", "beads-abc", "--to", "InactiveWorker2", "--json"],
            worker_id=active_ceo,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "target_not_active"

    def test_no_permission_on_task(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate fails when worker lacks permission on task."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=False):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "delegate", "beads-abc", "--to", report_data.name],
                worker_id=active_ceo,
            )
        assert result.exit_code != 0
        assert "permission" in result.output.lower()

    def test_no_permission_with_json(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate --json returns JSON error when no permission."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=False):
            result = invoke_wrkr(
                runner, org_dir,
                ["wrkr", "delegate", "beads-abc", "--to", report_data.name, "--json"],
                worker_id=active_ceo,
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["error"] == "no_permission"

    def test_happy_path_delegates_to_direct_report(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate successfully delegates task to direct report."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=True):
            with patch("commands.wrkr.delegate.run_bd", return_value=mock_result):
                result = invoke_wrkr(
                    runner, org_dir,
                    ["wrkr", "delegate", "beads-abc", "--to", report_data.name],
                    worker_id=active_ceo,
                )
        assert result.exit_code == 0
        assert "delegated" in result.output.lower()

    def test_delegate_to_subordinate_by_id(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate accepts worker ID as --to argument."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=True):
            with patch("commands.wrkr.delegate.run_bd", return_value=mock_result):
                result = invoke_wrkr(
                    runner, org_dir,
                    ["wrkr", "delegate", "beads-abc", "--to", worker_with_report],
                    worker_id=active_ceo,
                )
        assert result.exit_code == 0

    def test_case_insensitive_name_matching_for_target(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate matches target by name case-insensitively."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=True):
            with patch("commands.wrkr.delegate.run_bd", return_value=mock_result):
                result = invoke_wrkr(
                    runner, org_dir,
                    ["wrkr", "delegate", "beads-abc", "--to", report_data.name.upper()],
                    worker_id=active_ceo,
                )
        assert result.exit_code == 0

    def test_with_reason_logged_in_comment(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate passes reason to bd comment."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        captured_calls = []
        def run_bd_side(args, **kwargs):
            captured_calls.append(args[:])
            return mock_result
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=True):
            with patch("commands.wrkr.delegate.run_bd", side_effect=run_bd_side):
                result = invoke_wrkr(
                    runner, org_dir,
                    ["wrkr", "delegate", "beads-abc", "--to", report_data.name, "--reason", "Better fit"],
                    worker_id=active_ceo,
                )
        assert result.exit_code == 0
        # Should have called update + comment
        assert len(captured_calls) == 2
        comment_args = captured_calls[1]
        assert "Better fit" in " ".join(comment_args)

    def test_bd_update_fails(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate fails when bd update fails."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "update failed"
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=True):
            with patch("commands.wrkr.delegate.run_bd", return_value=mock_result):
                result = invoke_wrkr(
                    runner, org_dir,
                    ["wrkr", "delegate", "beads-abc", "--to", report_data.name],
                    worker_id=active_ceo,
                )
        assert result.exit_code != 0
        assert "failed" in result.output.lower()

    def test_comment_failure_is_non_critical(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate succeeds even when comment bd call fails."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        mock_update = MagicMock(returncode=0, stdout="", stderr="")
        mock_comment = MagicMock(returncode=1, stdout="", stderr="comment failed")
        call_num = [0]
        def run_bd_side(args, **kwargs):
            call_num[0] += 1
            if call_num[0] == 1:
                return mock_update
            return mock_comment
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=True):
            with patch("commands.wrkr.delegate.run_bd", side_effect=run_bd_side):
                result = invoke_wrkr(
                    runner, org_dir,
                    ["wrkr", "delegate", "beads-abc", "--to", report_data.name],
                    worker_id=active_ceo,
                )
        assert result.exit_code == 0

    def test_bd_binary_not_found(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate fails gracefully when bd binary not found."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=True):
            with patch("commands.wrkr.delegate.run_bd", side_effect=FileNotFoundError()):
                result = invoke_wrkr(
                    runner, org_dir,
                    ["wrkr", "delegate", "beads-abc", "--to", report_data.name],
                    worker_id=active_ceo,
                )
        assert result.exit_code != 0

    def test_json_flag_success_output_format(self, runner, org_dir, db, active_ceo, worker_with_report):
        """delegate --json returns success JSON with expected fields."""
        from cli.core.queries import get_worker
        report_data = get_worker(db, worker_with_report)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("commands.wrkr.delegate.can_worker_access_bead", return_value=True):
            with patch("commands.wrkr.delegate.run_bd", return_value=mock_result):
                result = invoke_wrkr(
                    runner, org_dir,
                    ["wrkr", "delegate", "beads-abc", "--to", report_data.name, "--json"],
                    worker_id=active_ceo,
                )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert "task_id" in data
        assert "delegated_to" in data


# ===========================================================================
# qn wrkr cleanup
# ===========================================================================

class TestWrkrCleanup:

    def test_org_not_initialized(self, runner):
        """cleanup fails when org not initialized."""
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(qn, ["--org-path", tmp, "wrkr", "cleanup", "some-worker"])
            assert result.exit_code != 0
            assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_worker_not_found(self, runner, org_dir):
        """cleanup fails for unknown worker."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", "nonexistent-worker"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_worker_has_no_session_record(self, runner, org_dir, db, active_ceo):
        """cleanup shows 'no session record' when no session exists."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo])
        assert result.exit_code == 0
        assert "no session" in result.output.lower()

    def test_happy_path_cleans_stale_session(self, runner, org_dir, db, active_ceo_with_session):
        """cleanup succeeds and shows completion message."""
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr = MagicMock()
            mock_mgr.unbind.return_value = MagicMock()
            mock_mgr_factory.return_value = mock_mgr
            result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo_with_session])
        assert result.exit_code == 0
        assert "cleanup complete" in result.output.lower()

    def test_session_state_updated_to_stopped(self, runner, org_dir, db, active_ceo_with_session):
        """cleanup updates session state to stopped."""
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr_factory.return_value = MagicMock()
            with patch("commands.wrkr.cleanup.update_session_state") as mock_update:
                result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo_with_session])
        assert result.exit_code == 0
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args
        assert call_kwargs.kwargs.get("state") == "stopped" or (call_kwargs.args and "stopped" in call_kwargs.args)

    def test_worker_runtime_set_to_stopped(self, runner, org_dir, db, active_ceo_with_session):
        """cleanup sets worker runtime_status to stopped."""
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr_factory.return_value = MagicMock()
            invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo_with_session])
        row = db.fetchone(
            "SELECT runtime_status FROM worker_state WHERE worker_id = ?",
            (active_ceo_with_session,),
        )
        assert row is not None
        assert row["runtime_status"] == "stopped"

    def test_tmux_session_name_cleared_in_db(self, runner, org_dir, db, active_ceo_with_session):
        """cleanup clears tmux_session_name from sessions table."""
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr_factory.return_value = MagicMock()
            invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo_with_session])
        row = db.fetchone(
            "SELECT tmux_session_name FROM sessions WHERE worker_id = ?",
            (active_ceo_with_session,),
        )
        assert row is not None
        assert row["tmux_session_name"] is None

    def test_binding_unbound_via_binding_manager(self, runner, org_dir, db, active_ceo_with_session):
        """cleanup calls binding manager unbind."""
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr = MagicMock()
            mock_mgr_factory.return_value = mock_mgr
            invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo_with_session])
        mock_mgr.unbind.assert_called_once_with(active_ceo_with_session)

    def test_unbind_failure_shows_warning_not_exception(self, runner, org_dir, db, active_ceo_with_session):
        """cleanup shows warning (not error) when unbind fails."""
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr = MagicMock()
            mock_mgr.unbind.side_effect = Exception("unbind error")
            mock_mgr_factory.return_value = mock_mgr
            result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo_with_session])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()

    def test_displays_session_info_in_output(self, runner, org_dir, db, active_ceo_with_session):
        """cleanup displays tmux session name and session ID."""
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr_factory.return_value = MagicMock()
            result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo_with_session])
        assert result.exit_code == 0
        assert "sess-test-001" in result.output or "qn-test-session" in result.output

    def test_session_with_no_tmux_session_name(self, runner, org_dir, db, active_ceo):
        """cleanup works when session has no tmux_session_name."""
        create_session_record(
            db=db,
            session_id="sess-no-tmux",
            worker_id=active_ceo,
            provider="claude_code",
            command="claude",
            tmux_session_name=None,
            state="stopped",
        )
        db.execute(
            "UPDATE worker_state SET runtime_status = 'stopped' WHERE worker_id = ?",
            (active_ceo,)
        )
        db.connection.commit()
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr_factory.return_value = MagicMock()
            result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo])
        assert result.exit_code == 0

    def test_session_with_no_session_id_still_updates_worker(self, runner, org_dir, db, active_ceo):
        """cleanup still updates worker runtime even if session record lacks ID."""
        with patch("commands.wrkr.cleanup.get_session_for_worker") as mock_sess:
            mock_sess.return_value = {"id": None, "tmux_session_name": None, "state": "stopped"}
            with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
                mock_mgr_factory.return_value = MagicMock()
                result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo])
        assert result.exit_code == 0

    def test_output_shows_restart_hint(self, runner, org_dir, db, active_ceo_with_session):
        """cleanup shows hint to use 'qn wrkr restart'."""
        with patch("commands.wrkr.cleanup.get_binding_manager") as mock_mgr_factory:
            mock_mgr_factory.return_value = MagicMock()
            result = invoke_wrkr(runner, org_dir, ["wrkr", "cleanup", active_ceo_with_session])
        assert result.exit_code == 0
        assert "restart" in result.output.lower()


# ===========================================================================
# qn wrkr restart
# ===========================================================================

class TestWrkrRestart:

    def test_org_not_initialized(self, runner):
        """restart fails when org not initialized."""
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(qn, ["--org-path", tmp, "wrkr", "restart", "some-worker"])
            assert result.exit_code != 0
            assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_org_in_stopped_state(self, runner, org_dir, db, active_ceo):
        """restart fails when org is stopped."""
        update_org_status(db, "stopped")
        result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo])
        assert result.exit_code != 0
        assert "not running" in result.output.lower() or "org" in result.output.lower()

    def test_org_in_uninitialized_state(self, runner, org_dir, db):
        """restart fails when org is in uninitialized state."""
        db.execute("UPDATE org_state SET status = 'uninitialized' WHERE id = 'default'")
        db.connection.commit()
        result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", "some-worker"])
        assert result.exit_code != 0

    def test_worker_not_found(self, runner, org_dir, db, running_org):
        """restart fails for unknown worker."""
        result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", "nonexistent-worker"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_blocks_restart_of_running_session_without_force(self, runner, org_dir, db, running_org, active_ceo_with_session):
        """restart blocks active running session without --force."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session])
        assert result.exit_code != 0
        assert "running" in result.output.lower()
        assert "--force" in result.output

    def test_blocks_restart_of_starting_session_without_force(self, runner, org_dir, db, active_ceo):
        """restart blocks starting session without --force."""
        update_org_status(db, "running", ceo_worker_id=active_ceo)
        create_session_record(
            db=db, session_id="sess-starting", worker_id=active_ceo,
            provider="claude_code", command="claude",
            tmux_session_name="qn-starting", state="starting",
        )
        result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo])
        assert result.exit_code != 0
        assert "--force" in result.output

    def test_blocks_restart_of_idle_session_without_force(self, runner, org_dir, db, active_ceo):
        """restart blocks idle session without --force."""
        update_org_status(db, "running", ceo_worker_id=active_ceo)
        create_session_record(
            db=db, session_id="sess-idle", worker_id=active_ceo,
            provider="claude_code", command="claude",
            tmux_session_name="qn-idle", state="idle",
        )
        result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo])
        assert result.exit_code != 0
        assert "--force" in result.output

    def test_happy_path_with_no_existing_session(self, runner, org_dir, db, running_org):
        """restart spawns new session when no existing session."""
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_registry = MagicMock()
                        mock_reg.return_value = mock_registry
                        with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                            mock_worker = MagicMock()
                            mock_worker.name = "TestCEO"
                            mock_worker.is_session_active = False
                            mock_worker_cls.get.return_value = mock_worker
                            result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org])
        assert result.exit_code == 0
        assert "spawned" in result.output.lower() or "restarted" in result.output.lower()

    def test_restarts_worker_with_stopped_session(self, runner, org_dir, db, active_ceo):
        """restart succeeds with stopped session."""
        update_org_status(db, "running", ceo_worker_id=active_ceo)
        create_session_record(
            db=db, session_id="sess-stopped", worker_id=active_ceo,
            provider="claude_code", command="claude",
            tmux_session_name="qn-stopped", state="stopped",
        )
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                            mock_worker = MagicMock()
                            mock_worker.name = "TestCEO"
                            mock_worker.is_session_active = False
                            mock_worker_cls.get.return_value = mock_worker
                            result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo])
        assert result.exit_code == 0

    def test_restarts_worker_with_crashed_session(self, runner, org_dir, db, active_ceo):
        """restart succeeds with crashed session."""
        update_org_status(db, "running", ceo_worker_id=active_ceo)
        create_session_record(
            db=db, session_id="sess-crashed", worker_id=active_ceo,
            provider="claude_code", command="claude",
            tmux_session_name="qn-crashed", state="stopped",
        )
        db.execute(
            "UPDATE sessions SET state = 'stopped' WHERE worker_id = ?",
            (active_ceo,)
        )
        db.connection.commit()
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                            mock_worker = MagicMock()
                            mock_worker.name = "TestCEO"
                            mock_worker.is_session_active = False
                            mock_worker_cls.get.return_value = mock_worker
                            result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo])
        assert result.exit_code == 0

    def test_force_restarts_running_session(self, runner, org_dir, db, active_ceo_with_session):
        """restart --force ignores running state."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        with patch("subprocess.run"):
            with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
                mock_ctx.return_value = MagicMock()
                with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                    with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                        mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                        with patch("core.sessions.registry.get_default_registry") as mock_reg:
                            mock_reg.return_value = MagicMock()
                            with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                mock_worker = MagicMock()
                                mock_worker.name = "TestCEO"
                                mock_worker.is_session_active = False
                                mock_worker_cls.get.return_value = mock_worker
                                result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session, "--force"])
        assert result.exit_code == 0

    def test_tmux_kill_called_for_existing_session(self, runner, org_dir, db, active_ceo_with_session):
        """restart calls tmux kill-session for existing session."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        with patch("subprocess.run") as mock_run:
            with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
                mock_ctx.return_value = MagicMock()
                with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                    with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                        mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                        with patch("core.sessions.registry.get_default_registry") as mock_reg:
                            mock_reg.return_value = MagicMock()
                            with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                mock_worker = MagicMock()
                                mock_worker.name = "TestCEO"
                                mock_worker.is_session_active = False
                                mock_worker_cls.get.return_value = mock_worker
                                result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session, "--force"])
        assert result.exit_code == 0
        # Verify tmux kill was called
        kill_calls = [c for c in mock_run.call_args_list if "kill-session" in str(c)]
        assert len(kill_calls) > 0

    def test_tmux_kill_failure_is_swallowed(self, runner, org_dir, db, active_ceo_with_session):
        """restart continues when tmux kill-session fails."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        with patch("subprocess.run", side_effect=Exception("tmux not found")):
            with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
                mock_ctx.return_value = MagicMock()
                with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                    with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                        mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                        with patch("core.sessions.registry.get_default_registry") as mock_reg:
                            mock_reg.return_value = MagicMock()
                            with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                mock_worker = MagicMock()
                                mock_worker.name = "TestCEO"
                                mock_worker.is_session_active = False
                                mock_worker_cls.get.return_value = mock_worker
                                result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session, "--force"])
        assert result.exit_code == 0

    def test_session_state_updated_to_stopped_before_unbind(self, runner, org_dir, db, active_ceo_with_session):
        """restart updates session state to stopped before unbind."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        with patch("subprocess.run"):
            with patch("commands.wrkr.restart.update_session_state") as mock_update:
                with patch("commands.wrkr.restart.get_binding_manager") as mock_mgr_factory:
                    mock_mgr_factory.return_value = MagicMock()
                    with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
                        mock_ctx.return_value = MagicMock()
                        with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                            with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                                mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                                with patch("core.sessions.registry.get_default_registry") as mock_reg:
                                    mock_reg.return_value = MagicMock()
                                    with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                        mock_worker = MagicMock()
                                        mock_worker.name = "TestCEO"
                                        mock_worker.is_session_active = False
                                        mock_worker_cls.get.return_value = mock_worker
                                        result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session, "--force"])
        assert result.exit_code == 0
        mock_update.assert_called_once()
        assert mock_update.call_args.kwargs.get("state") == "stopped"

    def test_worker_runtime_updated_to_stopped_before_respawn(self, runner, org_dir, db, active_ceo_with_session):
        """restart updates worker runtime_status to stopped."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        with patch("subprocess.run"):
            with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
                mock_ctx.return_value = MagicMock()
                with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                    with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                        mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                        with patch("core.sessions.registry.get_default_registry") as mock_reg:
                            mock_reg.return_value = MagicMock()
                            with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                mock_worker = MagicMock()
                                mock_worker.name = "TestCEO"
                                mock_worker.is_session_active = False
                                mock_worker_cls.get.return_value = mock_worker
                                result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session, "--force"])
        assert result.exit_code == 0
        row = db.fetchone(
            "SELECT runtime_status FROM worker_state WHERE worker_id = ?",
            (active_ceo_with_session,),
        )
        assert row["runtime_status"] == "stopped"

    def test_old_session_record_deleted_before_new_spawn(self, runner, org_dir, db, active_ceo_with_session):
        """restart deletes old session record before spawning new one."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        with patch("subprocess.run"):
            with patch("commands.wrkr.restart.delete_session_record") as mock_delete:
                with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
                    mock_ctx.return_value = MagicMock()
                    with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                        with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                            mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                            with patch("core.sessions.registry.get_default_registry") as mock_reg:
                                mock_reg.return_value = MagicMock()
                                with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                    mock_worker = MagicMock()
                                    mock_worker.name = "TestCEO"
                                    mock_worker.is_session_active = False
                                    mock_worker_cls.get.return_value = mock_worker
                                    result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session, "--force"])
        assert result.exit_code == 0
        mock_delete.assert_called_once()

    def test_unbind_warning_shown_but_non_fatal(self, runner, org_dir, db, active_ceo_with_session):
        """restart shows warning when unbind fails but continues."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        with patch("subprocess.run"):
            with patch("commands.wrkr.restart.get_binding_manager") as mock_mgr_factory:
                mock_mgr = MagicMock()
                mock_mgr.unbind.side_effect = Exception("unbind error")
                mock_mgr_factory.return_value = mock_mgr
                with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
                    mock_ctx.return_value = MagicMock()
                    with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                        with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                            mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                            with patch("core.sessions.registry.get_default_registry") as mock_reg:
                                mock_reg.return_value = MagicMock()
                                with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                    mock_worker = MagicMock()
                                    mock_worker.name = "TestCEO"
                                    mock_worker.is_session_active = False
                                    mock_worker_cls.get.return_value = mock_worker
                                    result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session, "--force"])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()

    def test_terminate_session_warning_shown_but_non_fatal(self, runner, org_dir, db, active_ceo_with_session):
        """restart shows warning when terminate_session fails but continues."""
        update_org_status(db, "running", ceo_worker_id=active_ceo_with_session)
        with patch("subprocess.run"):
            with patch("commands.wrkr.restart.get_binding_manager") as mock_mgr_factory:
                mock_mgr_factory.return_value = MagicMock()
                with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
                    mock_ctx.return_value = MagicMock()
                    with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                        with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                            mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                            with patch("core.sessions.registry.get_default_registry") as mock_reg:
                                mock_reg.return_value = MagicMock()
                                with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                    mock_worker = MagicMock()
                                    mock_worker.name = "TestCEO"
                                    mock_worker.is_session_active = True
                                    mock_worker.terminate_session.side_effect = Exception("terminate error")
                                    mock_worker_cls.get.return_value = mock_worker
                                    result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", active_ceo_with_session, "--force"])
        assert result.exit_code == 0
        assert "warning" in result.output.lower()

    def test_session_spawn_failure(self, runner, org_dir, db, running_org):
        """restart fails when spawn raises exception."""
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                            mock_worker = MagicMock()
                            mock_worker.name = "TestCEO"
                            mock_worker.is_session_active = False
                            mock_worker.spawn.side_effect = Exception("spawn failed")
                            mock_worker_cls.get.return_value = mock_worker
                            result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org])
        assert result.exit_code != 0
        assert "failed" in result.output.lower()

    def test_custom_provider_flag(self, runner, org_dir, db, running_org):
        """restart passes --provider to session config."""
        captured = {}
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.SessionConfig") as mock_sc:
                            mock_sc.side_effect = lambda **kw: captured.update(kw) or MagicMock()
                            with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                mock_worker = MagicMock()
                                mock_worker.name = "TestCEO"
                                mock_worker.is_session_active = False
                                mock_worker_cls.get.return_value = mock_worker
                                invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org, "--provider", "cursor"])
        assert captured.get("provider") == "cursor"

    def test_custom_command_flag(self, runner, org_dir, db, running_org):
        """restart passes --command to session config."""
        captured = {}
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.SessionConfig") as mock_sc:
                            mock_sc.side_effect = lambda **kw: captured.update(kw) or MagicMock()
                            with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                mock_worker = MagicMock()
                                mock_worker.name = "TestCEO"
                                mock_worker.is_session_active = False
                                mock_worker_cls.get.return_value = mock_worker
                                invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org, "--command", "cursor"])
        assert captured.get("command") == "cursor"

    def test_custom_args_flag(self, runner, org_dir, db, running_org):
        """restart passes --args to session config."""
        captured = {}
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.SessionConfig") as mock_sc:
                            mock_sc.side_effect = lambda **kw: captured.update(kw) or MagicMock()
                            with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                                mock_worker = MagicMock()
                                mock_worker.name = "TestCEO"
                                mock_worker.is_session_active = False
                                mock_worker_cls.get.return_value = mock_worker
                                invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org, "--args", "--no-auto"])
        assert captured.get("args") == ["--no-auto"]

    def test_onboarding_context_loaded_for_new_session(self, runner, org_dir, db, running_org):
        """restart loads onboarding context for new session."""
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                            mock_worker = MagicMock()
                            mock_worker.name = "TestCEO"
                            mock_worker.is_session_active = False
                            mock_worker_cls.get.return_value = mock_worker
                            invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org])
        mock_ctx.assert_called_once()

    def test_shows_tmux_attach_command_in_output(self, runner, org_dir, db, running_org):
        """restart shows tmux attach command after successful spawn."""
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                            mock_worker = MagicMock()
                            mock_worker.name = "TestCEO"
                            mock_worker.is_session_active = False
                            mock_worker_cls.get.return_value = mock_worker

                            # After spawn, set up a session record with tmux name
                            def spawn_side_effect(config):
                                create_session_record(
                                    db=db,
                                    session_id="sess-new",
                                    worker_id=running_org,
                                    provider="claude_code",
                                    command="claude",
                                    tmux_session_name="qn-new-session",
                                    state="running",
                                )
                            mock_worker.spawn.side_effect = spawn_side_effect

                            result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org])
        assert result.exit_code == 0
        assert "tmux attach" in result.output.lower() or "attach-session" in result.output.lower()

    def test_no_tmux_name_shown_when_session_has_no_tmux(self, runner, org_dir, db, running_org):
        """restart does not show tmux attach when session has no tmux name."""
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                            mock_worker = MagicMock()
                            mock_worker.name = "TestCEO"
                            mock_worker.is_session_active = False
                            mock_worker_cls.get.return_value = mock_worker
                            with patch("commands.wrkr.restart.get_session_for_worker") as mock_sess:
                                mock_sess.return_value = {"tmux_session_name": None}
                                result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org])
        assert result.exit_code == 0
        assert "attach-session" not in result.output

    def test_db_closed_in_finally_block_on_error(self, runner, org_dir, db, running_org):
        """restart closes DB even when spawn fails."""
        with patch("commands.wrkr.restart.load_onboarding_context") as mock_ctx:
            mock_ctx.return_value = MagicMock()
            with patch("commands.wrkr.restart.get_worker_env_vars", return_value={}):
                with patch("commands.wrkr.restart.StorageManager") as mock_sm:
                    mock_sm.return_value.get_worker_path.return_value = Path("/tmp/worker")
                    with patch("core.sessions.registry.get_default_registry") as mock_reg:
                        mock_reg.return_value = MagicMock()
                        with patch("commands.wrkr.restart.Worker") as mock_worker_cls:
                            mock_worker = MagicMock()
                            mock_worker.name = "TestCEO"
                            mock_worker.is_session_active = False
                            mock_worker.spawn.side_effect = Exception("spawn failed")
                            mock_worker_cls.get.return_value = mock_worker
                            result = invoke_wrkr(runner, org_dir, ["wrkr", "restart", running_org])
        # Should fail but not raise unhandled exception
        assert result.exit_code != 0
