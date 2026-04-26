"""Layer-2 audit tests: real tmux + fake_cli.

These tests exercise QuinnAI's actual tmux integration (TmuxSpawner,
capture-pane, send-keys, etc.) without spawning a real LLM CLI. They're
gated on @pytest.mark.tmux and auto-skip when tmux isn't on PATH.

Beads extended (deferred → covered with real tmux):
- quinn-ai-bfh: qn org logs (reads real tmux scrollback)
- quinn-ai-npx: qn org observe (polls real tmux output)
- quinn-ai-9ex: qn org start (spawns a real session via TmuxSpawner)
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.core.constants import TMUX_SESSION_PREFIX
from cli.core.sessions.spawner import SpawnerConfig
from cli.core.sessions.tmux_spawner import TmuxSpawner
from cli.tests.harness.fake_cli import __name__ as _ensure_module  # noqa: F401


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


def _mark_worker_running(org_path: Path, worker_id: str, session_name: str) -> None:
    """Set up DB so QuinnAI thinks the worker has a live session.

    Inserts:
    - worker_state row with runtime_status='running'
    - sessions row with state='running' and matching tmux_session_name

    Required because `qn org logs` / `qn org observe` look up the worker's
    session record AND verify a tmux session by that name actually exists.
    """
    conn = sqlite3.connect(str(org_path / "live" / "quinn.db"))
    try:
        conn.execute(
            """INSERT OR REPLACE INTO worker_state
               (worker_id, runtime_status, started_at, updated_at)
               VALUES (?, 'running', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (worker_id,),
        )
        conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, worker_id, provider, command, tmux_session_name, state,
                state_version, started_at, last_activity)
               VALUES (?, ?, 'claude_code', 'fakecli', ?, 'running', 0,
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (f"sess-{worker_id}", worker_id, session_name),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def worker_with_real_tmux(initialized_org):
    """Spawn a real tmux session named qn-<ceo_id> running fake_cli AND
    mark the worker's runtime_status=running in the DB so the qn commands
    that read tmux think the worker is live.

    Yields (org_path, worker_id, spawner). TmuxSpawner cleans up on teardown.
    """
    ceo_id = _ceo_id(initialized_org)
    session_name = f"{TMUX_SESSION_PREFIX}{ceo_id}"
    spawner = TmuxSpawner()
    config = SpawnerConfig(
        command=sys.executable,
        args=["-m", "cli.tests.harness.fake_cli", "--worker", ceo_id, "--interval", "0.2"],
        session_name=session_name,
        worker_id=ceo_id,
    )
    result = spawner.spawn(config)
    if not result.success:
        pytest.fail(f"failed to spawn tmux session for {ceo_id}: {result.error}")
    _mark_worker_running(initialized_org, ceo_id, session_name)
    # Banner timing
    time.sleep(0.4)
    try:
        yield initialized_org, ceo_id, spawner
    finally:
        spawner.stop(session_name, force=True)


# ============================================================
# quinn-ai-bfh: qn org logs (real tmux scrollback)
# ============================================================
class TestOrgLogsRealTmux:
    @pytest.mark.tmux
    def test_logs_reads_real_tmux_scrollback(self, runner, worker_with_real_tmux):
        org_path, ceo_id, _ = worker_with_real_tmux
        result = runner.invoke(qn, [
            "--org-path", str(org_path), "org", "logs", ceo_id,
        ])
        assert result.exit_code == 0, result.output
        assert "FAKE-CLI: ready" in result.output, (
            f"qn org logs should surface fake_cli banner from tmux pane. "
            f"output:\n{result.output}"
        )

    @pytest.mark.tmux
    def test_logs_with_lines_limit(self, runner, worker_with_real_tmux):
        org_path, ceo_id, _ = worker_with_real_tmux
        # Wait for a few heartbeats to accumulate
        time.sleep(1.0)
        result = runner.invoke(qn, [
            "--org-path", str(org_path), "org", "logs", ceo_id, "-n", "5",
        ])
        assert result.exit_code == 0, result.output


# ============================================================
# quinn-ai-npx: qn org observe (real tmux stream)
# ============================================================
class TestOrgObserveRealTmux:
    @pytest.mark.tmux
    def test_observe_help_renders_with_real_session(self, runner, worker_with_real_tmux):
        """qn org observe's --stream is an indefinite poll loop CliRunner
        can't ctrl-c out of. Instead verify the command is invokable
        (--help works) when a real session is in place — the actual
        streaming behaviour is exercised by the spawner-level harness
        tests in cli/tests/harness/test_tmux_fixtures.py via
        spawner.read_output()."""
        org_path, _, _ = worker_with_real_tmux
        result = runner.invoke(qn, [
            "--org-path", str(org_path), "org", "observe", "--help",
        ])
        assert result.exit_code == 0
        assert "--stream" in result.output


# ============================================================
# quinn-ai-9ex: qn org start spawns a real tmux session
# ============================================================
class TestOrgStartRealTmux:
    @pytest.mark.tmux
    def test_start_spawns_real_session_for_ceo(self, runner, initialized_org):
        """The full --spawn-ceo path with fake_cli as the CEO command.

        This bypasses the providers.yaml machinery by passing the command
        directly via --command/--args.
        """
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "start",
            "--skip-config-validation",
            "--no-wait",  # Don't block on readiness
            "--command", sys.executable,
            "--args", f"-m cli.tests.harness.fake_cli --worker {ceo_id} --interval 0.2",
        ])
        # Verify the tmux session exists with the expected name
        session_name = f"{TMUX_SESSION_PREFIX}{ceo_id}"
        spawner = TmuxSpawner()
        try:
            time.sleep(0.5)  # let session start
            alive = spawner.is_alive(session_name)
            output = result.output
            try:
                assert alive, (
                    f"Expected tmux session {session_name!r} alive after start. "
                    f"qn output:\n{output}"
                )
            except AssertionError:
                # Helpful diag: list tmux sessions
                import subprocess
                ls = subprocess.run(
                    ["tmux", "ls"], capture_output=True, text=True
                )
                pytest.fail(
                    f"session {session_name} not alive.\n"
                    f"tmux ls:\n{ls.stdout}\n"
                    f"qn output:\n{output}"
                )
        finally:
            spawner.stop(session_name, force=True)
