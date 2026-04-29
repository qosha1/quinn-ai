"""Audit tests for `qn org init` (bead quinn-ai-772).

Covers gaps left by test_cli.py / test_org_init_okrs.py:
- cwd fallback when --org-path / QUINN_ORG_PATH are unset (quinn-ai-1aj fix)
- bd init no longer installs git hooks (quinn-ai-aa3 fix; --skip-hooks)
- create_initial_tasks no longer logs a FK-constraint warning (quinn-ai-6se fix)
"""

import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.commands.main import qn


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_org():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_init_falls_back_to_cwd_when_org_path_unset(runner, temp_org, monkeypatch):
    """quinn-ai-1aj: `qn org init` from cwd with no flags must succeed,
    not crash with AttributeError on org_path.name."""
    monkeypatch.delenv("QUINN_ORG_PATH", raising=False)
    monkeypatch.chdir(temp_org)

    result = runner.invoke(qn, ["org", "init", "--skip-okrs"])

    assert result.exit_code == 0, (
        f"init should succeed from cwd. exit={result.exit_code}\n"
        f"output:\n{result.output}\n"
        f"exception: {result.exception!r}"
    )
    assert "Initialized organization" in result.output
    assert (temp_org / "live" / "quinn.db").exists()


def test_init_does_not_install_bd_git_hooks(runner, temp_org):
    """quinn-ai-aa3: init_beads passes --skip-hooks; .beads/hooks/ must not exist.
    Without this, bd's pre-commit hook deadlocks on macOS (no `timeout(1)`)."""
    result = runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--skip-okrs"])
    assert result.exit_code == 0, result.output

    hooks_dir = temp_org / ".beads" / "hooks"
    assert not hooks_dir.exists(), (
        f".beads/hooks/ should NOT exist (bd was called with --skip-hooks). "
        f"Found: {list(hooks_dir.iterdir()) if hooks_dir.exists() else 'n/a'}"
    )


def test_init_does_not_log_fk_constraint_warning(runner, temp_org):
    """quinn-ai-6se: create_initial_tasks must use ceo_id (not 'system') so the
    activity_signals FK to workers.id holds. Output must not contain the
    'Failed to create initial tasks' warning."""
    result = runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--skip-okrs"])
    assert result.exit_code == 0, result.output
    assert "Failed to create initial tasks" not in result.output, (
        f"Init should not log FK warning. Output:\n{result.output}"
    )
    assert "FOREIGN KEY constraint failed" not in result.output, (
        f"Init should not show FK error. Output:\n{result.output}"
    )


def test_init_skip_okrs_creates_no_bootstrap_okr(runner, temp_org):
    """--skip-okrs must create zero OKRs (regression for quinn-ai-6odb).

    Earlier behavior was that --skip-okrs only suppressed the wizard prompt
    but still planted a 'Establish organizational foundation' bootstrap OKR.
    That defeated the flag's purpose for canaries and tests that need to
    plant their own OKRs without a phantom bootstrap one derailing the CEO.
    """
    import sqlite3

    result = runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--skip-okrs"])
    assert result.exit_code == 0, result.output

    db_path = temp_org / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT id, title FROM okrs").fetchall()
    finally:
        conn.close()

    assert rows == [], f"--skip-okrs must create no OKRs, got: {rows}"
