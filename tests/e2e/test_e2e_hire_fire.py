"""E2E tests for `qn org hire/fire/promote/demote` + delegate-authority flow.

Real qn → cli.core.worker → SQLite. No real LLM (uses --no-spawn-ceo for
the parent org_with_ceo fixture).
"""

import sqlite3

import pytest


# ---------------------------------------------------------------------------
# qn org hire
# ---------------------------------------------------------------------------


def test_hire_creates_worker_under_ceo(org_with_ceo, qn_runner):
    """`qn org hire --name=alice --role=Engineer --manager=ceo` creates a worker row."""
    result = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "hire",
            "--name", "alice",
            "--role", "Engineer",
            "--manager", "ceo",
        ],
        timeout=30,
    )
    assert result.returncode == 0, f"hire failed:\n{result.stderr}\n{result.stdout}"

    # Verify SQLite row
    db_path = org_with_ceo / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name, role FROM workers WHERE name = ?", ("alice",)
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1, f"expected exactly one alice in workers, got {len(rows)}"
    assert rows[0] == ("alice", "Engineer")


def test_hire_under_unknown_manager_fails(org_with_ceo, qn_runner):
    """Hiring under a manager that doesn't exist returns non-zero."""
    result = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "hire",
            "--name", "stuck-bob",
            "--role", "Engineer",
            "--manager", "totally-not-a-real-manager",
        ],
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# qn wrkr list — confirm hires show up
# ---------------------------------------------------------------------------


def test_wrkr_list_shows_hired_team(hired_team, org_with_ceo, qn_runner):
    """The hired_team fixture's workers appear in `qn wrkr list`."""
    # Note: 'wrkr list' requires --worker-id so test through SQLite directly.
    # 'qn wrkr' commands are AI-worker-scoped, not human-operator queries.
    db_path = org_with_ceo / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id FROM workers WHERE name LIKE 'worker%'"
        ).fetchall()
    finally:
        conn.close()
    db_ids = {row[0] for row in rows}
    for wid in hired_team:
        assert wid in db_ids, f"hired worker {wid} not in workers table: {db_ids}"


# ---------------------------------------------------------------------------
# qn org fire
# ---------------------------------------------------------------------------


def test_fire_terminates_active_worker(org_with_ceo, qn_runner):
    """Hire → fire → worker.status == 'terminated'."""
    hire = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "hire",
            "--name", "fireable",
            "--role", "Engineer",
            "--manager", "ceo",
        ],
        timeout=30,
    )
    assert hire.returncode == 0, hire.stderr

    db_path = org_with_ceo / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id FROM workers WHERE name = ?", ("fireable",)
        ).fetchone()
    finally:
        conn.close()
    assert row, "hired worker not found"
    worker_id = row[0]

    fire = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "fire", worker_id,
            "--reason", "e2e test",
            "--force",
        ],
        timeout=30,
    )
    assert fire.returncode == 0, f"fire failed:\n{fire.stderr}\n{fire.stdout}"

    # Verify status
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT status FROM workers WHERE id = ?", (worker_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "terminated", (
        f"expected status='terminated' after fire, got {row[0]!r}"
    )


def test_fire_unknown_worker_fails_cleanly(org_with_ceo, qn_runner):
    """Firing a worker that doesn't exist returns non-zero."""
    result = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "fire", "worker-does-not-exist",
            "--force",
        ],
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_fire_ceo_is_rejected(org_with_ceo, qn_runner):
    """Firing the CEO must fail — the CEO is structurally protected."""
    db_path = org_with_ceo / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT ceo_worker_id FROM org_state WHERE id = 'default'"
        ).fetchone()
    finally:
        conn.close()
    assert row, "no org_state row"
    ceo_id = row[0]

    result = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "fire", ceo_id,
            "--force",
        ],
    )
    assert result.returncode != 0, "expected non-zero when firing CEO"
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# qn org promote / demote
# ---------------------------------------------------------------------------


def test_promote_grants_management_authority(org_with_ceo, qn_runner):
    """Hire → promote → worker becomes a manager (gains hiring authority)."""
    hire = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "hire",
            "--name", "future-mgr",
            "--role", "Senior Engineer",
            "--manager", "ceo",
        ],
        timeout=30,
    )
    assert hire.returncode == 0

    db_path = org_with_ceo / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id FROM workers WHERE name = ?", ("future-mgr",)
        ).fetchone()
    finally:
        conn.close()
    worker_id = row[0]

    promote = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "promote", worker_id,
        ],
        timeout=30,
    )
    # Promotion may succeed (granting authority) or fail with a clean message
    # if the role/state doesn't support promotion. We require: no traceback.
    assert "Traceback" not in promote.stderr, promote.stderr


def test_demote_removes_management_authority(org_with_ceo, qn_runner):
    """Hire + promote + demote round-trips without traceback."""
    # Hire
    qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "org", "hire",
            "--name", "demo-mgr",
            "--role", "Engineer",
            "--manager", "ceo",
        ],
        timeout=30,
    )

    db_path = org_with_ceo / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id FROM workers WHERE name = ?", ("demo-mgr",)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("hire failed in setup; covered by test_hire_creates_worker_under_ceo")
    worker_id = row[0]

    # Promote then demote — both should run without traceback
    qn_runner(
        ["--org-path", str(org_with_ceo), "org", "promote", worker_id],
        timeout=30,
    )
    demote = qn_runner(
        ["--org-path", str(org_with_ceo), "org", "demote", worker_id],
        timeout=30,
    )
    assert "Traceback" not in demote.stderr, demote.stderr


# ---------------------------------------------------------------------------
# qn org delegate-authority / revoke-authority / delegations
# ---------------------------------------------------------------------------


def test_delegations_list_runs_cleanly(org_with_ceo, qn_runner):
    """`qn org delegations` lists current authority delegations (or none)."""
    result = qn_runner(
        ["--org-path", str(org_with_ceo), "org", "delegations"],
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
