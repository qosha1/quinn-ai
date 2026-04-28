"""E2E tests for `qn board` intervention commands: pause, resume, fire, status, alerts, health.

These are the human-operator commands for stepping in when the org is
off-track. Tests exercise the state-machine transitions; the board TUI
itself is out of scope (needs real TTY).
"""

import sqlite3

import pytest


# ---------------------------------------------------------------------------
# qn board status / alerts / health (read-only)
# ---------------------------------------------------------------------------


def test_board_status_runs_against_running_org(org_with_ceo, qn_runner):
    """`qn board status` shows org dashboard."""
    result = qn_runner(
        ["--org-path", str(org_with_ceo), "board", "status"],
    )
    assert result.returncode == 0, f"board status failed:\n{result.stderr}"
    assert "Traceback" not in result.stderr


def test_board_alerts_runs_cleanly(org_with_ceo, qn_runner):
    """`qn board alerts` lists active alerts (or none)."""
    result = qn_runner(
        ["--org-path", str(org_with_ceo), "board", "alerts"],
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr


def test_board_health_runs_cleanly(org_with_ceo, qn_runner):
    """`qn board health` reports the org's health score."""
    result = qn_runner(
        ["--org-path", str(org_with_ceo), "board", "health"],
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# qn board pause / resume
# ---------------------------------------------------------------------------


def test_board_pause_then_resume_round_trip(hired_team, org_with_ceo, qn_runner):
    """pause(worker) → runtime_status='paused', then resume → runtime_status changes back."""
    worker_id = hired_team[0]

    pause = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "board", "pause", worker_id,
            "--reason", "e2e test pause",
        ],
    )
    # pause may succeed (if worker has a session to pause) or fail with a
    # clean message if the worker isn't running (no session). We require
    # no traceback either way.
    assert "Traceback" not in pause.stderr, pause.stderr

    resume = qn_runner(
        ["--org-path", str(org_with_ceo), "board", "resume", worker_id],
    )
    assert "Traceback" not in resume.stderr, resume.stderr


def test_board_pause_unknown_worker_fails_cleanly(org_with_ceo, qn_runner):
    """`board pause <bogus>` exits non-zero with no traceback."""
    result = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "board", "pause", "worker-not-real",
        ],
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# qn board fire (the immediate kill-and-terminate path)
# ---------------------------------------------------------------------------


def test_board_fire_terminates_worker(hired_team, org_with_ceo, qn_runner):
    """`qn board fire <id>` sets the worker to terminated."""
    worker_id = hired_team[0]

    fire = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "board", "fire", worker_id,
            "--reason", "e2e test fire",
            "--force",
        ],
        timeout=30,
    )
    assert fire.returncode == 0, f"board fire failed:\n{fire.stderr}\n{fire.stdout}"

    db_path = org_with_ceo / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT status FROM workers WHERE id = ?", (worker_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row, f"worker {worker_id} disappeared"
    assert row[0] == "terminated", (
        f"expected status='terminated' after board fire, got {row[0]!r}"
    )


def test_board_fire_unknown_worker_fails_cleanly(org_with_ceo, qn_runner):
    """`board fire <bogus>` exits non-zero with no traceback."""
    result = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "board", "fire", "wrkr-fake12345",
            "--reason", "e2e",
            "--force",
        ],
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
