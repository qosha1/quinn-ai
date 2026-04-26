"""Regression test for quinn-ai-41v.

`qn org hire` against a fresh org auto-tries to spawn a session, but the
new worker has no per-worker budget allocation. The original UX:

  Hired alice (engineer)
    ID: wrkr-...
  Starting worker session...
  Warning: Failed to start session: No budget allocation found for worker
  You can start manually with: qn org start

After the fix, the no-budget case should be a normal-looking informational
message (not a 'Warning: Failed') and explicitly point at the right next
step ('qn org budget allocate' before 'qn org start --worker NAME').
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


def test_hire_no_budget_does_not_say_warning_failed(runner, initialized_org):
    """The no-budget path is expected on a fresh org — it should not be
    framed as a 'Warning: Failed' (which implies something went wrong)."""
    ceo_id = _ceo_id(initialized_org)
    result = runner.invoke(qn, [
        "--org-path", str(initialized_org),
        "org", "hire",
        "--name", "alice", "--role", "engineer",
        "--manager", ceo_id, "--cost", "50",
    ])
    assert result.exit_code == 0, result.output
    # Worker IS hired; session-spawn warning is a separate concern.
    assert "Hired 'alice'" in result.output
    assert "Warning: Failed to start session" not in result.output, (
        f"Expected the no-budget path to be informational, not 'Warning: Failed'. "
        f"Output:\n{result.output}"
    )


def test_hire_no_budget_points_at_budget_allocate(runner, initialized_org):
    """The fix message should explicitly mention the 'qn org budget allocate'
    next step so users don't have to guess."""
    ceo_id = _ceo_id(initialized_org)
    result = runner.invoke(qn, [
        "--org-path", str(initialized_org),
        "org", "hire",
        "--name", "bob", "--role", "engineer",
        "--manager", ceo_id, "--cost", "50",
    ])
    assert result.exit_code == 0, result.output
    assert "qn org budget allocate" in result.output, (
        f"Expected the no-budget message to point at 'qn org budget allocate'. "
        f"Output:\n{result.output}"
    )
