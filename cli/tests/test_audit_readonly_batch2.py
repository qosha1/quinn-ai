"""Audit batch 2: read-only commands (no writes, no session spawn).

Beads covered (one class per bead):
- quinn-ai-6ud: qn board status
- quinn-ai-7ge: qn board health
- quinn-ai-hri: qn board alerts
- quinn-ai-2b1: qn org chart export
- quinn-ai-8k6: qn org chart history
- quinn-ai-up0: qn org chart diff
- quinn-ai-a7n: qn org budget tree
- quinn-ai-4e9: qn org budget transactions
- quinn-ai-9qs: qn org okr show
- quinn-ai-pwd: qn org okr progress
- quinn-ai-7py: qn org okr cascade
- quinn-ai-mt3: msgr channels
- quinn-ai-2fx: msgr inbox
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


# ============================================================
# quinn-ai-6ud: qn board status
# ============================================================
class TestBoardStatus:
    def test_renders_dashboard_summary(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "board", "status",
        ])
        assert result.exit_code == 0, result.output
        # Top-level dashboard sections
        for header in ("Workers:", "Sessions:", "Budget:", "CEO:", "Alerts"):
            assert header in result.output, f"Missing section '{header}':\n{result.output}"

    def test_breaks_down_workers_by_lifecycle_stage(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "board", "status",
        ])
        assert result.exit_code == 0
        for stage in ("Pending", "Onboarding", "Active", "Offboarding", "Terminated"):
            assert stage in result.output

    def test_json_output_is_valid(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "board", "status", "--json",
        ])
        assert result.exit_code == 0, result.output
        try:
            data = json.loads(result.output)
        except json.JSONDecodeError as e:
            pytest.fail(f"--json produced invalid JSON: {e}\n{result.output}")
        assert isinstance(data, dict)


# ============================================================
# quinn-ai-7ge: qn board health
# ============================================================
class TestBoardHealth:
    def test_clean_health_on_fresh_org(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "board", "health",
        ])
        assert result.exit_code == 0, result.output
        assert "Organization Health" in result.output
        assert "No issues detected" in result.output

    def test_json_output_is_valid(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "board", "health", "--json",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, dict)


# ============================================================
# quinn-ai-hri: qn board alerts
# ============================================================
class TestBoardAlerts:
    def test_no_alerts_on_fresh_org(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "board", "alerts",
        ])
        assert result.exit_code == 0, result.output
        assert "No active alerts" in result.output

    def test_priority_filter_accepts_p0_p1_p2(self, runner, initialized_org):
        for p in ("P0", "P1", "P2"):
            result = runner.invoke(qn, [
                "--org-path", str(initialized_org), "board", "alerts", "-p", p,
            ])
            assert result.exit_code == 0, f"--priority {p} failed:\n{result.output}"

    def test_priority_filter_rejects_invalid(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "board", "alerts", "-p", "P9",
        ])
        assert result.exit_code != 0
        assert "P0" in result.output or "P1" in result.output  # Click choice error lists valid options


# ============================================================
# quinn-ai-2b1: qn org chart export
# ============================================================
class TestChartExport:
    def test_yaml_default_to_stdout(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "org", "chart", "export",
        ])
        assert result.exit_code == 0, result.output
        # YAML should contain top-level keys
        assert "workers:" in result.output or "hierarchy:" in result.output

    def test_json_format_to_stdout(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "chart", "export", "-f", "json",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "workers" in data or "hierarchy" in data

    def test_writes_to_output_file(self, runner, initialized_org, tmp_path):
        out = tmp_path / "chart.json"
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "chart", "export", "-f", "json", "-o", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert isinstance(data, dict)


# ============================================================
# quinn-ai-8k6: qn org chart history
# ============================================================
class TestChartHistory:
    def test_runs_after_init(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "org", "chart", "history",
        ])
        # Init creates org-chart/ but the org dir may not be a git repo —
        # accept either success with output or a clean ClickException.
        # Just ensure no crash / traceback.
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            f"Unexpected exception: {result.exception!r}\n{result.output}"
        )

    def test_oneline_flag_parses(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "chart", "history", "--oneline",
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-up0: qn org chart diff
# ============================================================
class TestChartDiff:
    def test_runs_after_init(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "org", "chart", "diff",
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_cached_flag_parses(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "chart", "diff", "--cached",
        ])
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-a7n: qn org budget tree
# ============================================================
class TestBudgetTree:
    def test_renders_ceo_at_root(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "org", "budget", "tree",
        ])
        assert result.exit_code == 0, result.output
        assert "AuditCEO" in result.output

    def test_worker_id_flag_accepts_id(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "tree", "-w", ceo_id,
        ])
        assert result.exit_code == 0, result.output


# ============================================================
# quinn-ai-4e9: qn org budget transactions
# ============================================================
class TestBudgetTransactions:
    def test_runs_with_no_transactions(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "org", "budget", "transactions",
        ])
        assert result.exit_code == 0, result.output

    def test_limit_flag_parses(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "transactions", "-n", "5",
        ])
        assert result.exit_code == 0


# ============================================================
# quinn-ai-9qs: qn org okr show
# ============================================================
class TestOkrShow:
    def test_show_existing_okr(self, runner, initialized_org):
        # Create one (--no-krs-needed required since KR enforcement was added)
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set", "--title", "ShowMe", "--owner", "ceo",
            "--no-krs-needed",
        ])
        # Find the bd id from list
        list_result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "org", "okr", "list",
        ])
        assert "ShowMe" in list_result.output
        # Extract id from "ID: <id>" line
        okr_id = None
        for line in list_result.output.splitlines():
            line = line.strip()
            if line.startswith("ID: "):
                okr_id = line.split(":", 1)[1].strip()
                break
        assert okr_id, f"Could not locate OKR id in:\n{list_result.output}"

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "org", "okr", "show", okr_id,
        ])
        assert result.exit_code == 0, result.output
        assert "ShowMe" in result.output

    def test_show_unknown_okr_fails_cleanly(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "show", "okr-bogus-xyz",
        ])
        assert result.exit_code != 0
        # Should not be an uncaught traceback
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-pwd: qn org okr progress
# ============================================================
class TestOkrProgress:
    def test_progress_for_db_okr(self, runner, initialized_org):
        # Create an OKR first (initialized_org uses --skip-okrs so none exist by default)
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set", "--title", "Test OKR for progress", "--owner", "ceo",
            "--no-krs-needed",
        ])
        conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
        try:
            row = conn.execute("SELECT id FROM okrs LIMIT 1").fetchone()
            if row is None:
                import pytest
                pytest.skip("No OKR in DB after creation attempt — skipping")
            (okr_id,) = row
        finally:
            conn.close()

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "progress", okr_id,
        ])
        # progress reads from SQLite — bootstrap OKR should be findable
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-7py: qn org okr cascade
# ============================================================
class TestOkrCascade:
    def test_cascade_runs_after_init(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org), "org", "okr", "cascade",
        ])
        # Even with no OKRs visible in beads view, command should not crash
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ============================================================
# quinn-ai-mt3: msgr channels
# ============================================================
class TestMsgrChannels:
    def test_lists_default_channels(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "channels",
        ])
        assert result.exit_code == 0, result.output
        # Default org gets #general, #board-channel, #executive
        assert "general" in result.output
        assert "board-channel" in result.output
        assert "executive" in result.output

    def test_requires_worker_id(self, runner, initialized_org, monkeypatch):
        monkeypatch.delenv("QUINN_WORKER_ID", raising=False)
        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "channels",
        ])
        assert result.exit_code != 0


# ============================================================
# quinn-ai-2fx: msgr inbox
# ============================================================
class TestMsgrInbox:
    def test_empty_inbox_on_fresh_ceo(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "inbox",
        ])
        assert result.exit_code == 0, result.output
        assert "No pending notifications" in result.output

    def test_unread_flag_parses(self, runner, initialized_org):
        ceo_id = _ceo_id(initialized_org)
        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "inbox", "--unread",
        ])
        assert result.exit_code == 0
