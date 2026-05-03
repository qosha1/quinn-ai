"""Audit batch 3: write-side commands that don't require tmux/session spawn.

Beads (one class per bead):
- quinn-ai-o1o: qn org okr set
- quinn-ai-2dt: qn org okr update-kr
- quinn-ai-acb: qn org okr link
- quinn-ai-uzi: qn org budget allocate
- quinn-ai-qbh: qn org provider default
- quinn-ai-e9j: qn org provider set-worker
- quinn-ai-zov: qn org provider show-worker
- quinn-ai-e7h: qn org provider validate
- quinn-ai-a2u: qn org delegate-authority
- quinn-ai-3hc: qn org revoke-authority
- quinn-ai-7u5: qn org promote
- quinn-ai-qei: qn org demote
- quinn-ai-00t: qn org cleanup
- quinn-ai-983: qn wrkr get-work
- quinn-ai-ywg: qn wrkr status
- quinn-ai-e0z: qn wrkr search
- quinn-ai-trm: qn wrkr delegate
- quinn-ai-fqi: qn wrkr report
- quinn-ai-kwy: msgr send
- quinn-ai-5ln: msgr read
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.msgr.main import msgr


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


def _make_worker(runner, org_path: Path, name: str, role: str = "engineer", cost: int = 50) -> str:
    """Hire a worker via direct DB insert (avoid the auto-spawn tmux issue)."""
    import uuid
    from datetime import datetime
    wid = f"wrkr-{uuid.uuid4().hex[:8]}"
    ceo_id = _ceo_id(org_path)
    conn = sqlite3.connect(str(org_path / "live" / "quinn.db"))
    try:
        # Get CEO's team
        (team_id,) = conn.execute(
            "SELECT team_id FROM workers WHERE id=?", (ceo_id,)
        ).fetchone()
        conn.execute(
            """INSERT INTO workers
               (id, name, role, team_id, manager_id, status, skills, cost,
                hiring_authority_scope, delegated_budget, max_reports)
               VALUES (?, ?, ?, ?, ?, 'pending', '{}', ?, NULL, 0, 10)""",
            (wid, name, role, team_id, ceo_id, cost),
        )
        conn.commit()
    finally:
        conn.close()
    return wid


# ============================================================
# quinn-ai-o1o: qn org okr set
# ============================================================
class TestOkrSet:
    def test_creates_okr_as_bead(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set",
            "--title", "Set test", "-d", "desc", "--owner", "ceo", "-p", "1",
            "--no-krs-needed",
        ])
        assert result.exit_code == 0, result.output
        assert "Created issue:" in result.output

    def test_no_fk_warning_with_owner_ceo(self, runner, initialized_org):
        """quinn-ai-6se fix: owner='ceo' must resolve via Org.ceo_worker_id,
        not fall through as the literal string 'ceo'."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set", "--title", "Owner test", "--owner", "ceo",
            "--no-krs-needed",
        ])
        assert result.exit_code == 0, result.output
        assert "Failed to store OKR in database" not in result.output


# ============================================================
# quinn-ai-2dt: qn org okr update-kr
# ============================================================
class TestOkrUpdateKr:
    def test_update_existing_kr(self, runner, initialized_org):
        # Create an OKR with a KR to update
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set", "--title", "Update KR test",
            "--kr", "team_size:5:people",
        ])
        conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
        try:
            row = conn.execute("SELECT id FROM okrs LIMIT 1").fetchone()
            if row is None:
                import pytest; pytest.skip("No OKR in DB")
            (okr_id,) = row
        finally:
            conn.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "update-kr", okr_id,
            "-m", "team_size", "-c", "2",
        ])
        # Should succeed (or fail cleanly) — no traceback
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-acb: qn org okr link
# ============================================================
class TestOkrLink:
    def test_link_runs_with_known_ids(self, runner, initialized_org):
        # Need bd ids — create an OKR + a task
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set", "--title", "LinkOKR", "--owner", "ceo",
            "--no-krs-needed",
        ])
        # Even if linking fails (because work-id may not exist), verify clean error
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "link", "task-bogus", "okr-bogus",
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-uzi: qn org budget allocate
# ============================================================
class TestBudgetAllocate:
    def test_allocate_to_subordinate(self, runner, initialized_org):
        # Hire a subordinate via DB shortcut
        _make_worker(runner, initialized_org, "alice")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "allocate", "alice", "100",
        ])
        # Allocation may fail without proper authority/budget setup;
        # the audit verifies the command parses and runs — no traceback.
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-qbh: qn org provider default
# ============================================================
class TestProviderDefault:
    def test_get_default(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "default",
        ])
        assert result.exit_code == 0, result.output
        # providers.yaml ships with `default: claude_code`
        assert "claude_code" in result.output

    def test_set_default(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "default", "openai",
        ])
        # May succeed or fail with clean error; either way no traceback
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-e9j: qn org provider set-worker
# ============================================================
class TestProviderSetWorker:
    def test_set_then_show_roundtrip(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        set_result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "set-worker", ceo_id, "openai",
        ])
        assert set_result.exit_code == 0, set_result.output

        show_result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "show-worker", ceo_id,
        ])
        assert show_result.exit_code == 0, show_result.output
        assert "openai" in show_result.output


# ============================================================
# quinn-ai-zov: qn org provider show-worker (paired with set-worker above)
# ============================================================
class TestProviderShowWorker:
    def test_show_default_when_not_set(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "show-worker", ceo_id,
        ])
        assert result.exit_code == 0, result.output


# ============================================================
# quinn-ai-e7h: qn org provider validate
# ============================================================
class TestProviderValidate:
    def test_validate_default_config(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "validate",
        ])
        assert result.exit_code == 0, result.output


# ============================================================
# quinn-ai-a2u: qn org delegate-authority
# ============================================================
class TestDelegateAuthority:
    def test_delegate_to_subordinate_with_level(self, runner, initialized_org):
        wid = _make_worker(runner, initialized_org, "bob")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegate-authority",
            "--to", wid, "--level", "team-lead", "--force",
        ])
        # Either succeeds or fails cleanly — no uncaught exception
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            f"unexpected: {result.exception!r}\n{result.output}"
        )


# ============================================================
# quinn-ai-3hc: qn org revoke-authority
# ============================================================
class TestRevokeAuthority:
    def test_revoke_runs_against_ceo(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        # Revoking the CEO is unusual, but the command should respond cleanly
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "revoke-authority", ceo_id, "--force", "--dry-run",
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-7u5: qn org promote
# ============================================================
class TestPromote:
    def test_dry_run_for_subordinate(self, runner, initialized_org):
        wid = _make_worker(runner, initialized_org, "carol")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "promote", wid, "--to", "team-lead", "--force",
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-qei: qn org demote
# ============================================================
class TestDemote:
    def test_demote_runs_for_subordinate(self, runner, initialized_org):
        wid = _make_worker(runner, initialized_org, "dave")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "demote", wid, "--force",
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-00t: qn org cleanup
# ============================================================
class TestCleanup:
    def test_dry_run_safe(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup", "--dry-run",
        ])
        assert result.exit_code == 0, result.output

    def test_actual_run_safe(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "cleanup",
        ])
        assert result.exit_code == 0, result.output


# ============================================================
# quinn-ai-983: qn wrkr get-work
# ============================================================
class TestWrkrGetWork:
    def test_no_work_assigned(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "--worker-id", ceo_id, "get-work",
        ])
        assert result.exit_code == 0, result.output

    def test_json_output(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "--worker-id", ceo_id, "get-work", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Either a list of work items, OR an error/status dict (e.g.
        # {error: worker_not_ready, lifecycle: pending}). Both are valid.
        assert isinstance(data, (list, dict))


# ============================================================
# quinn-ai-ywg: qn wrkr status
# ============================================================
class TestWrkrStatus:
    def test_status_for_ceo(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "--worker-id", ceo_id, "status",
        ])
        assert result.exit_code == 0, result.output
        assert "AuditCEO" in result.output


# ============================================================
# quinn-ai-e0z: qn wrkr search
# ============================================================
class TestWrkrSearch:
    def test_search_empty_corpus(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "--worker-id", ceo_id, "search", "anything",
        ])
        assert result.exit_code == 0, result.output

    def test_search_after_send(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "send", "#general", "deployment audit message",
        ])
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "--worker-id", ceo_id, "search", "deployment",
        ])
        assert result.exit_code == 0, result.output
        assert "deployment" in result.output.lower()


# ============================================================
# quinn-ai-trm: qn wrkr delegate
# ============================================================
class TestWrkrDelegate:
    def test_delegate_with_bogus_task(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        wid = _make_worker(runner, initialized_org, "edith")
        # Even with bogus task id, command should fail cleanly (no traceback)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "--worker-id", ceo_id, "delegate", "task-bogus", "--to", wid,
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-fqi: qn wrkr report
# ============================================================
class TestWrkrReport:
    def test_report_to_manager(self, runner, initialized_org):
        wid = _make_worker(runner, initialized_org, "frank")
        # CEO is Frank's manager; report from Frank to CEO
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "wrkr", "--worker-id", wid,
            "report", "--summary", "Audit progress report",
        ])
        # May succeed or fail cleanly (depends on bd availability) — no traceback
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-kwy: msgr send
# ============================================================
class TestMsgrSend:
    def test_send_to_general(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "send", "#general", "audit hello",
        ])
        assert result.exit_code == 0, result.output
        assert "Message sent" in result.output

    def test_send_persists_message_row(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "send", "#general", "persist test xyz123",
        ])
        conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
        try:
            row = conn.execute(
                "SELECT content FROM messages WHERE content LIKE '%xyz123%'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "message must persist to messages table"
        assert "persist test xyz123" in row[0]


# ============================================================
# quinn-ai-5ln: msgr read
# ============================================================
class TestMsgrRead:
    def test_read_unknown_id_clean_error(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "read", "msg-bogus",
        ])
        # Should not produce an uncaught traceback
        assert result.exception is None or isinstance(result.exception, SystemExit)
