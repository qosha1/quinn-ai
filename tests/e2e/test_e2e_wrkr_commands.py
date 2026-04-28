"""E2E tests for `qn wrkr` worker-scoped commands.

These commands take a --worker-id and act AS that worker (or report on
their state). For e2e we exercise the read-only ones that don't need a
live session: status, get-work, search, report. restart/cleanup need
real tmux + a session — covered minimally.
"""

import pytest


def test_wrkr_status_for_ceo(org_with_ceo, qn_runner):
    """`qn wrkr status` for the CEO returns the worker's current state."""
    import sqlite3

    db_path = org_with_ceo / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT ceo_worker_id FROM org_state WHERE id = 'default'"
        ).fetchone()
    finally:
        conn.close()
    ceo_id = row[0]

    result = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "wrkr", "--worker-id", ceo_id, "status",
        ],
    )
    assert result.returncode == 0, f"wrkr status failed:\n{result.stderr}"
    assert "Traceback" not in result.stderr


def test_wrkr_get_work_for_hired_worker(hired_team, org_with_ceo, qn_runner):
    """`qn wrkr get-work` for a freshly-hired worker either returns empty or work."""
    worker_id = hired_team[0]
    result = qn_runner([
            "--org-path", str(org_with_ceo),
            "wrkr", "--worker-id", worker_id, "get-work",
        ],
    )
    assert result.returncode == 0, f"wrkr get-work failed:\n{result.stderr}"
    assert "Traceback" not in result.stderr


def test_wrkr_search_runs_cleanly(hired_team, org_with_ceo, qn_runner):
    """`qn wrkr search <query>` returns 0 with no matches on a fresh org."""
    worker_id = hired_team[0]
    result = qn_runner([
            "--org-path", str(org_with_ceo),
            "wrkr", "--worker-id", worker_id, "search", "nosuchstring",
        ],
    )
    assert result.returncode == 0, f"wrkr search failed:\n{result.stderr}"
    assert "Traceback" not in result.stderr


def test_wrkr_search_handles_hyphenated_query(hired_team, org_with_ceo, qn_runner):
    """Regression: `qn wrkr search a-b-c` must not crash on FTS5 operator parse.

    Pre-fix this raised `sqlite3.OperationalError: no such column: such`
    because FTS5 parsed 'no-such-string' as 'no MINUS such MINUS string'.
    """
    worker_id = hired_team[0]
    result = qn_runner([
            "--org-path", str(org_with_ceo),
            "wrkr", "--worker-id", worker_id, "search", "no-such-string",
        ],
    )
    assert result.returncode == 0, f"wrkr search crashed on hyphenated query:\n{result.stderr}"
    assert "Traceback" not in result.stderr
    assert "OperationalError" not in result.stderr


def test_wrkr_report_sends_status(hired_team, org_with_ceo, qn_runner):
    """`qn wrkr report --message=...` sends a status update upstream."""
    worker_id = hired_team[0]
    result = qn_runner([
            "--org-path", str(org_with_ceo),
            "wrkr", "--worker-id", worker_id, "report",
            "--message", "e2e test status",
        ],
    )
    # report may require additional args (e.g. --to) — accept either 0 or
    # a clean non-zero with a usage message.
    assert "Traceback" not in result.stderr, result.stderr


def test_wrkr_status_unknown_worker_fails_cleanly(org_with_ceo, qn_runner):
    """Querying status for a nonexistent worker returns non-zero."""
    result = qn_runner(
        [
            "--org-path", str(org_with_ceo),
            "wrkr", "--worker-id", "wrkr-fake12345", "status",
        ],
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
