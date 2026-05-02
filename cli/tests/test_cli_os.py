"""
Tests for CLI OS features: ps, exec, broadcast, gc, inspect, env, snapshot, tail, pause/resume, audit.
All tests FAIL until implementation exists.
"""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.core.db import open_database, get_org_db_path
from cli.core.org_init import OrgInitConfig, init_org


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def org(tmp_path):
    org_path = tmp_path / "org"
    org_path.mkdir()
    cfg = OrgInitConfig(path=org_path, name="TestOrg", ceo_name="Alice", ceo_role="CEO")
    result = init_org(cfg)
    assert result.success, result.error
    return org_path


# ---------------------------------------------------------------------------
# qn org ps
# ---------------------------------------------------------------------------

def test_org_ps_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "ps"])
    assert result.exit_code == 0, result.output


def test_org_ps_shows_worker_name(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "ps"])
    assert "alice" in result.output.lower() or "Alice" in result.output


def test_org_ps_shows_role(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "ps"])
    assert "CEO" in result.output or "ceo" in result.output.lower()


def test_org_ps_json_flag(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "ps", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "name" in data[0]
    assert "role" in data[0]
    assert "status" in data[0]


def test_org_ps_shows_status(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "ps"])
    # Should show lifecycle or runtime status for each worker
    status_words = ["active", "pending", "stopped", "running", "idle", "onboarding"]
    assert any(w in result.output.lower() for w in status_words)


# ---------------------------------------------------------------------------
# qn wrkr exec
# ---------------------------------------------------------------------------

def test_wrkr_exec_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "exec", "--help"])
    assert result.exit_code == 0
    assert "exec" in result.output.lower() or "directive" in result.output.lower() or "message" in result.output.lower()


def test_wrkr_exec_sends_dm_to_worker(runner, org):
    result = runner.invoke(qn, [
        "--org-path", str(org),
        "wrkr", "exec", "alice", "check your inbox and continue",
    ])
    assert result.exit_code == 0
    assert "sent" in result.output.lower() or "alice" in result.output.lower()


def test_wrkr_exec_fails_gracefully_for_unknown_worker(runner, org):
    result = runner.invoke(qn, [
        "--org-path", str(org),
        "wrkr", "exec", "nobody-real", "hello",
    ])
    assert result.exit_code != 0 or "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# qn org broadcast
# ---------------------------------------------------------------------------

def test_org_broadcast_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "broadcast", "--help"])
    assert result.exit_code == 0


def test_org_broadcast_sends_to_general(runner, org):
    result = runner.invoke(qn, [
        "--org-path", str(org),
        "org", "broadcast", "All hands: review your OKRs today",
    ])
    assert result.exit_code == 0
    assert "broadcast" in result.output.lower() or "sent" in result.output.lower() or "general" in result.output.lower()


def test_org_broadcast_channel_flag(runner, org):
    result = runner.invoke(qn, [
        "--org-path", str(org),
        "org", "broadcast", "Update", "--channel", "general",
    ])
    assert result.exit_code == 0


def test_org_broadcast_dry_run(runner, org):
    result = runner.invoke(qn, [
        "--org-path", str(org),
        "org", "broadcast", "test message", "--dry-run",
    ])
    assert result.exit_code == 0
    assert "dry" in result.output.lower() or "would" in result.output.lower() or "preview" in result.output.lower()


# ---------------------------------------------------------------------------
# qn org gc
# ---------------------------------------------------------------------------

def test_org_gc_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "gc", "--help"])
    assert result.exit_code == 0


def test_org_gc_runs_successfully(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "gc"])
    assert result.exit_code == 0


def test_org_gc_dry_run(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "gc", "--dry-run"])
    assert result.exit_code == 0
    assert "dry" in result.output.lower() or "would" in result.output.lower() or "clean" in result.output.lower()


def test_org_gc_reports_cleaned_count(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "gc"])
    assert result.exit_code == 0
    # Should report something about what was cleaned (even if 0)
    digits = [c for c in result.output if c.isdigit()]
    assert len(digits) >= 1 or "nothing" in result.output.lower() or "clean" in result.output.lower()


# ---------------------------------------------------------------------------
# qn wrkr inspect
# ---------------------------------------------------------------------------

def test_wrkr_inspect_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "inspect", "--help"])
    assert result.exit_code == 0


def test_wrkr_inspect_outputs_json(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "inspect", "alice"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "id" in data
    assert "name" in data
    assert "role" in data


def test_wrkr_inspect_includes_budget(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "inspect", "alice"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "budget" in data or "allocated" in str(data)


def test_wrkr_inspect_includes_storage_path(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "inspect", "alice"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "storage" in data or "storage_path" in str(data)


def test_wrkr_inspect_unknown_worker(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "inspect", "nobody"])
    assert result.exit_code != 0 or "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# qn org env
# ---------------------------------------------------------------------------

def test_org_env_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "env", "--help"])
    assert result.exit_code == 0


def test_org_env_shows_worker_env_vars(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "env"])
    assert result.exit_code == 0
    # Should show standard worker env vars
    assert "WORKER" in result.output or "STORAGE" in result.output or "ORG" in result.output


def test_org_env_worker_flag(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "env", "--worker", "alice"])
    assert result.exit_code == 0
    assert "WORKER_ID" in result.output or "WORKER_NAME" in result.output


# ---------------------------------------------------------------------------
# qn org snapshot
# ---------------------------------------------------------------------------

def test_org_snapshot_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "snapshot", "--help"])
    assert result.exit_code == 0


def test_org_snapshot_outputs_json(runner, org, tmp_path):
    out = tmp_path / "snap.json"
    result = runner.invoke(qn, [
        "--org-path", str(org),
        "org", "snapshot", "--out", str(out),
    ])
    assert result.exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert "workers" in data
    assert "org" in data


def test_org_snapshot_to_stdout(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "snapshot"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "workers" in data


def test_org_snapshot_includes_okrs(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "snapshot"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "okrs" in data


# ---------------------------------------------------------------------------
# qn org audit
# ---------------------------------------------------------------------------

def test_org_audit_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "audit", "--help"])
    assert result.exit_code == 0


def test_org_audit_runs_without_error(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "audit"])
    assert result.exit_code == 0


def test_org_audit_json_flag(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "audit", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)


def test_org_audit_last_flag(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "org", "audit", "--last", "24h"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# qn wrkr pause / resume
# ---------------------------------------------------------------------------

def test_wrkr_pause_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "pause", "--help"])
    assert result.exit_code == 0


def test_wrkr_resume_command_exists(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "resume", "--help"])
    assert result.exit_code == 0


def test_wrkr_pause_sends_message(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "pause", "alice"])
    assert result.exit_code == 0
    assert "pause" in result.output.lower() or "alice" in result.output.lower()


def test_wrkr_resume_sends_message(runner, org):
    result = runner.invoke(qn, ["--org-path", str(org), "wrkr", "resume", "alice"])
    assert result.exit_code == 0
    assert "resume" in result.output.lower() or "alice" in result.output.lower()
