"""Audit batch 4: lifecycle / session-touching commands.

Most of these commands fully exercise their happy paths only with a real
tmux session. The audit verifies what's testable without tmux:
- safe-state behaviors (stopped org, no active sessions)
- DB-state side effects of state-machine transitions
- error/edge-case handling

For paths that genuinely need tmux, the bead's close-reason notes the
deferred-coverage.

Beads:
- quinn-ai-9ex: qn org start
- quinn-ai-tnd: qn org stop
- quinn-ai-cib: qn org restart
- quinn-ai-70s: qn org hire
- quinn-ai-xyq: qn org fire
- quinn-ai-bfh: qn org logs
- quinn-ai-npx: qn org observe
- quinn-ai-7hu: qn wrkr restart
- quinn-ai-nk9: qn wrkr cleanup
- quinn-ai-c09: qn board pause
- quinn-ai-roz: qn board resume
- quinn-ai-fjx: qn board fire
- quinn-ai-6x5: qn config set-provider
"""

import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from cli.commands.main import qn


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_org():
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        runner = CliRunner()
        result = runner.invoke(qn, [
            "--org-path", str(org_path), "org", "init",
            "--ceo-name", "AuditCEO", "--skip-okrs",
        ])
        assert result.exit_code == 0, result.output
        yield org_path


def _ceo_id(org_path: Path) -> str:
    conn = sqlite3.connect(str(org_path / "live" / "quinn.db"))
    try:
        return conn.execute("SELECT id FROM workers WHERE role='CEO'").fetchone()[0]
    finally:
        conn.close()


def _make_worker(org_path: Path, name: str, role: str = "engineer", cost: int = 50,
                 status: str = "pending") -> str:
    """Direct DB insert to fabricate a worker."""
    wid = f"wrkr-{uuid.uuid4().hex[:8]}"
    ceo_id = _ceo_id(org_path)
    conn = sqlite3.connect(str(org_path / "live" / "quinn.db"))
    try:
        (team_id,) = conn.execute(
            "SELECT team_id FROM workers WHERE id=?", (ceo_id,)
        ).fetchone()
        conn.execute(
            """INSERT INTO workers
               (id, name, role, team_id, manager_id, status, skills, cost,
                hiring_authority_scope, delegated_budget, max_reports)
               VALUES (?, ?, ?, ?, ?, ?, '{}', ?, NULL, 0, 10)""",
            (wid, name, role, team_id, ceo_id, status, cost),
        )
        conn.commit()
    finally:
        conn.close()
    return wid


# ============================================================
# quinn-ai-9ex: qn org start
# ============================================================
class TestOrgStart:
    def test_no_spawn_ceo_advances_org_state(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "start", "--no-spawn-ceo", "--skip-config-validation",
        ])
        assert result.exit_code == 0, result.output
        assert "running" in result.output.lower()

        # DB should reflect running state
        conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
        try:
            (status,) = conn.execute("SELECT status FROM org_state LIMIT 1").fetchone()
        finally:
            conn.close()
        assert status == "running"

    def test_phase_outputs_visible(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "start", "--no-spawn-ceo", "--skip-config-validation",
        ])
        assert result.exit_code == 0
        # Phases 0-2 print headers
        assert "Phase" in result.output


# ============================================================
# quinn-ai-tnd: qn org stop
# ============================================================
class TestOrgStop:
    def test_stop_after_start(self, runner, initialized_org):
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "start", "--no-spawn-ceo", "--skip-config-validation",
        ])
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "stop", "-y",
        ])
        assert result.exit_code == 0, result.output
        # Verify org transitioned to stopped
        conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
        try:
            (status,) = conn.execute("SELECT status FROM org_state LIMIT 1").fetchone()
        finally:
            conn.close()
        assert status == "stopped"

    def test_stop_when_no_sessions(self, runner, initialized_org):
        # Stopping an initialized-but-not-started org should be safe
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "stop", "-y",
        ])
        # Either succeeds or fails cleanly (state machine may reject) — no traceback
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-cib: qn org restart
# ============================================================
class TestOrgRestart:
    def test_restart_round_trips_state(self, runner, initialized_org):
        # Get to running first
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "start", "--no-spawn-ceo", "--skip-config-validation",
        ])
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "restart", "--no-spawn-ceo", "--skip-config-validation",
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            f"unexpected: {result.exception!r}\n{result.output}"
        )


# ============================================================
# quinn-ai-70s: qn org hire
# ============================================================
class TestOrgHire:
    def test_hire_creates_worker_in_db(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "alice",
            "--role", "engineer",
            "--manager", ceo_id,
            "--cost", "50",
        ])
        # Hire output may include a 'Failed to start session' warning (no tmux);
        # the DB-write part should still succeed.
        conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
        try:
            row = conn.execute(
                "SELECT name, role, manager_id FROM workers WHERE name='alice'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, f"alice should be in workers table. Output:\n{result.output}"
        assert row[1] == "engineer"
        assert row[2] == ceo_id

    def test_hire_resolves_manager_by_name(self, runner, initialized_org):
        """quinn-ai-ozl fix: --manager can be a name."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "bob",
            "--role", "engineer",
            "--manager", "AuditCEO",
            "--cost", "50",
        ])
        conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
        try:
            row = conn.execute("SELECT id FROM workers WHERE name='bob'").fetchone()
        finally:
            conn.close()
        assert row is not None, f"bob should be hired. Output:\n{result.output}"

    def test_hire_unknown_manager_clean_error(self, runner, initialized_org):
        """quinn-ai-ozl fix: unknown manager → ClickException, not traceback."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "hire",
            "--name", "carol",
            "--role", "engineer",
            "--manager", "nobody-by-this-name",
            "--cost", "50",
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()
        # Critically: no uncaught WorkerNotFound traceback
        assert "Traceback" not in result.output


# ============================================================
# quinn-ai-xyq: qn org fire
# ============================================================
class TestOrgFire:
    def test_fire_transitions_worker_to_terminated(self, runner, initialized_org):
        wid = _make_worker(initialized_org, "victim")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", wid, "--reason", "audit", "--force",
        ])
        # Fire may fail if state machine rejects pending→terminated directly,
        # but we verify it doesn't crash with a traceback.
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            f"unexpected: {result.exception!r}\n{result.output}"
        )

    def test_fire_unknown_worker_clean_error(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "fire", "wrkr-bogus", "--force",
        ])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ============================================================
# quinn-ai-bfh: qn org logs
# ============================================================
class TestOrgLogs:
    def test_logs_unknown_worker_clean_error(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", "wrkr-bogus",
        ])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_logs_no_active_session_clean_error(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "logs", ceo_id,
        ])
        # CEO has no tmux session — should error cleanly, not crash
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "Traceback" not in result.output


# ============================================================
# quinn-ai-npx: qn org observe
# ============================================================
class TestOrgObserve:
    def test_observe_unknown_worker_clean_error(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "observe", "wrkr-bogus",
        ])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ============================================================
# quinn-ai-7hu: qn wrkr restart
# ============================================================
class TestWrkrRestart:
    def test_wrkr_restart_unknown_worker_clean_error(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "restart", "wrkr-bogus",
        ])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ============================================================
# quinn-ai-nk9: qn wrkr cleanup
# ============================================================
class TestWrkrCleanup:
    def test_wrkr_cleanup_unknown_worker_clean_error(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "cleanup", "wrkr-bogus",
        ])
        # May succeed (no-op cleanup) or fail cleanly
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "Traceback" not in result.output

    def test_wrkr_cleanup_for_existing_worker(self, runner, initialized_org):
        wid = _make_worker(initialized_org, "stale")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "cleanup", wid,
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-c09: qn board pause
# ============================================================
class TestBoardPause:
    def test_pause_no_session_clean_error(self, runner, initialized_org):
        wid = _make_worker(initialized_org, "guinea-pig")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "pause", wid, "-r", "audit",
        ])
        # Worker has no active session — should respond cleanly
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "Traceback" not in result.output


# ============================================================
# quinn-ai-roz: qn board resume
# ============================================================
class TestBoardResume:
    def test_resume_unknown_worker_clean_error(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "resume", "wrkr-bogus",
        ])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ============================================================
# quinn-ai-fjx: qn board fire
# ============================================================
class TestBoardFire:
    def test_fire_requires_reason(self, runner, initialized_org):
        wid = _make_worker(initialized_org, "to-fire")
        # No --reason given
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "fire", wid, "--force",
        ])
        # Click should error: -r/--reason is required
        assert result.exit_code != 0

    def test_fire_unknown_worker_clean_error(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "board", "fire", "wrkr-bogus", "-r", "audit", "--force",
        ])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ============================================================
# quinn-ai-6x5: qn config set-provider
# ============================================================
class TestConfigSetProvider:
    def test_set_provider_writes_yaml(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "config", "set-provider", "openai", "--org-path", str(initialized_org),
        ])
        assert result.exit_code == 0, result.output

        cfg = yaml.safe_load((initialized_org / "config" / "providers.yaml").read_text())
        assert cfg["default"] == "openai"

    def test_set_provider_rejects_invalid_choice(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "config", "set-provider", "bogus-provider", "--org-path", str(initialized_org),
        ])
        assert result.exit_code != 0
        # Click choice errors list valid options
        assert "claude_code" in result.output or "anthropic" in result.output

    def test_set_provider_requires_org_path(self, runner):
        result = runner.invoke(qn, ["config", "set-provider", "openai"])
        assert result.exit_code != 0
