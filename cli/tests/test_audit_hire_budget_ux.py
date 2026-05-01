"""Regression tests for hire + budget UX.

Original bug (quinn-ai-41v): `qn org hire` against a fresh org failed with
'Warning: Failed to start session: No budget allocation' — bad UX.

First fix: showed informational message pointing at qn org budget allocate.
Current fix: auto-allocates DEFAULT_WORKER_BUDGET_ALLOCATION credits from CEO
and starts the session immediately — no manual step required.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest
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


def test_hire_starts_session_without_manual_budget_step(runner, initialized_org):
    """Hiring a worker auto-allocates budget and starts the session immediately.
    No manual 'qn org budget allocate' step required."""
    ceo_id = _ceo_id(initialized_org)
    result = runner.invoke(qn, [
        "--org-path", str(initialized_org),
        "org", "hire",
        "--name", "alice", "--role", "engineer",
        "--manager", ceo_id, "--cost", "50",
    ])
    assert result.exit_code == 0, result.output
    assert "Hired 'alice'" in result.output
    assert "Warning: Failed to start session" not in result.output
    # Session should have started (auto-budget path)
    assert "Session started for alice" in result.output


def test_hire_auto_allocates_budget(runner, initialized_org):
    """Hire auto-allocates credits from CEO so session can start."""
    ceo_id = _ceo_id(initialized_org)
    result = runner.invoke(qn, [
        "--org-path", str(initialized_org),
        "org", "hire",
        "--name", "bob", "--role", "engineer",
        "--manager", ceo_id, "--cost", "50",
    ])
    assert result.exit_code == 0, result.output
    assert "Auto-allocated" in result.output or "Session started for bob" in result.output
