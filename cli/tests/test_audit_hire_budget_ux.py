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


def _worker_id(org_path: Path, name: str) -> str:
    conn = sqlite3.connect(str(org_path / "live" / "quinn.db"))
    try:
        row = conn.execute(
            "SELECT id FROM workers WHERE lower(name)=lower(?)", (name,)
        ).fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


def _is_funded(org_path: Path, worker_id: str) -> bool:
    from cli.core.budget import BudgetService
    from cli.core.db import open_database, get_org_db_path

    db = open_database(get_org_db_path(org_path))
    try:
        bal = BudgetService(db).get_balance(worker_id)
        return bal is not None and bal.available > 0
    finally:
        db.close()


def test_manager_hired_worker_is_auto_funded(runner, initialized_org):
    """A worker hired by a MANAGER (not the CEO) must be auto-funded too.

    Regression quinn-ai-dkhs: the hire fallback delegated budget from
    org.ceo.id, but delegate_budget requires the source to be the worker's
    DIRECT manager. So a manager-hired worker tripped 'Worker X does not
    report to <CEO>', the fallback errored, and the worker booted unfunded —
    surfaced live in canary 04 (frank never started, hierarchy stalled).
    """
    ceo_id = _ceo_id(initialized_org)

    # CEO hires Diana, a manager.
    r1 = runner.invoke(qn, [
        "--org-path", str(initialized_org), "org", "hire",
        "--name", "diana", "--role", "manager", "--manager", ceo_id, "--cost", "50",
    ])
    assert r1.exit_code == 0, r1.output

    # Give Diana hiring authority.
    r2 = runner.invoke(qn, [
        "--org-path", str(initialized_org), "org", "promote", "diana",
        "--to", "team-lead", "--force",
    ])
    assert r2.exit_code == 0, r2.output

    # Diana hires Eve — this is the path that broke.
    r3 = runner.invoke(qn, [
        "--org-path", str(initialized_org), "org", "hire",
        "--name", "eve", "--role", "engineer", "--manager", "diana", "--cost", "50",
    ])
    assert r3.exit_code == 0, r3.output
    assert "Could not auto-allocate budget" not in r3.output, r3.output
    assert "does not report to" not in r3.output, r3.output

    eve_id = _worker_id(initialized_org, "eve")
    assert eve_id, "Eve was not created"
    assert _is_funded(initialized_org, eve_id), (
        "Eve (hired by manager Diana) booted UNFUNDED — the hire fallback must "
        "delegate from the worker's actual manager, not the CEO (dkhs)."
    )
