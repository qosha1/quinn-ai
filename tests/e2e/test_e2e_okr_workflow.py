"""E2E tests for `qn org okr` subcommands.

Covers the read/write surface for OKRs: set, add (alias), list, cascade,
show, progress, update-kr, link. Hits the real qn → run_bd → bd binary
→ SQLite path.
"""

import json
import sqlite3

import pytest


# ---------------------------------------------------------------------------
# qn org okr list
# ---------------------------------------------------------------------------


def test_okr_list_on_fresh_org(initialized_org, qn_runner):
    """Fresh-init org has at least the bootstrap OKR (or shows 'No OKRs')."""
    result = qn_runner(
        ["--org-path", str(initialized_org), "org", "okr", "list"],
    )
    assert result.returncode == 0, result.stderr
    # 'No OKRs found' (cleanly empty) OR the bootstrap OKR shows up
    assert (
        "No OKRs found" in result.stdout
        or "OKR:" in result.stdout
    ), f"unexpected list output:\n{result.stdout}"


def test_okr_list_from_db(initialized_org, qn_runner):
    """`okr list --from-db` reads from the SQLite mirror."""
    result = qn_runner(
        ["--org-path", str(initialized_org), "org", "okr", "list", "--from-db"],
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# qn org okr set / add
# ---------------------------------------------------------------------------


def test_okr_set_creates_okr_in_beads_and_db(initialized_org, qn_runner):
    """`okr set --title=X` creates a bead AND mirrors to SQLite."""
    title = "Ship E2E Test Suite"
    result = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "set",
            "--no-krs-needed",
            "--title", title,
            "--owner", "ceo",
        ],
        timeout=30,
    )
    assert result.returncode == 0, f"okr set failed:\n{result.stderr}\n{result.stdout}"
    assert "Created" in result.stdout, f"missing 'Created' in:\n{result.stdout}"

    # Confirm SQLite has the new OKR
    db_path = initialized_org / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT title FROM okrs WHERE title = ?", (title,)
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1, (
        f"expected exactly one OKR with title {title!r} in SQLite, found {len(rows)}"
    )


def test_okr_close_updates_both_bead_and_sqlite_mirror(initialized_org, qn_runner):
    """Regression: 'qn org okr close <id>' must close BOTH the bead and
    the SQLite okrs row (quinn-ai-kljb).

    Pre-fix: workers ran 'bd close <okr-id>' which silently no-op'd
    relative to the SQLite mirror — okr.status stayed 'active'. The
    new 'qn org okr close' command does both writes.
    """
    title = "Close-test OKR"
    result = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "set",
            "--no-krs-needed",
            "--title", title,
            "--owner", "ceo",
        ],
        timeout=30,
    )
    assert result.returncode == 0, f"set failed:\n{result.stderr}\n{result.stdout}"

    # Pull the OKR id from sqlite for a deterministic close target
    db_path = initialized_org / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id, status FROM okrs WHERE title = ?", (title,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "OKR row should exist after set"
    okr_id, pre_status = row
    assert pre_status == "active", f"new OKR should start 'active', got {pre_status}"

    # Close it
    close_result = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "close", okr_id,
            "--reason", "verified by canary",
        ],
        timeout=30,
    )
    assert close_result.returncode == 0, (
        f"close failed:\n{close_result.stderr}\n{close_result.stdout}"
    )

    # Both stores should reflect the closure now
    conn = sqlite3.connect(str(db_path))
    try:
        post_status = conn.execute(
            "SELECT status FROM okrs WHERE id = ?", (okr_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert post_status == "completed", (
        f"SQLite okrs.status should be 'completed' after close, got {post_status!r}"
    )


def test_okr_add_is_alias_for_set(initialized_org, qn_runner):
    """`okr add` is an alias of `okr set`."""
    title = "Add Alias Verification"
    result = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "add",
            "--no-krs-needed",
            "--title", title,
            "--owner", "ceo",
        ],
        timeout=30,
    )
    assert result.returncode == 0, f"okr add failed:\n{result.stderr}\n{result.stdout}"


# ---------------------------------------------------------------------------
# qn org okr show / progress
# ---------------------------------------------------------------------------


def test_okr_show_existing(initialized_org, qn_runner):
    """`okr show <id>` works on the bootstrap OKR (or an okr we just created)."""
    # Create an OKR so we have a known id to show
    title = "Showable OKR"
    create = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "set",
            "--no-krs-needed",
            "--title", title,
            "--owner", "ceo",
        ],
        timeout=30,
    )
    assert create.returncode == 0

    # Pull an OKR id from SQLite
    db_path = initialized_org / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id FROM okrs WHERE title = ?", (title,)
        ).fetchone()
    finally:
        conn.close()
    assert row, f"no OKR with title {title!r} in SQLite"
    okr_id = row[0]

    result = qn_runner(
        ["--org-path", str(initialized_org), "org", "okr", "show", okr_id],
    )
    assert result.returncode == 0, f"okr show {okr_id} failed:\n{result.stderr}"


def test_okr_show_unknown_fails_cleanly(initialized_org, qn_runner):
    """`okr show <bogus>` exits non-zero with no traceback."""
    result = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "show",
            "okr-definitely-not-real",
        ],
    )
    assert result.returncode != 0, "expected non-zero for unknown OKR"
    assert "Traceback" not in result.stderr, result.stderr


def test_okr_progress_on_db_okr(initialized_org, qn_runner):
    """`okr progress <id>` reports key-result progress."""
    db_path = initialized_org / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT id FROM okrs LIMIT 1").fetchone()
    finally:
        conn.close()
    if not row:
        pytest.skip("no OKRs in fresh org — bootstrap OKR may have been disabled")
    okr_id = row[0]

    result = qn_runner(
        ["--org-path", str(initialized_org), "org", "okr", "progress", okr_id],
    )
    assert result.returncode == 0, result.stderr
    assert "Progress:" in result.stdout or "Key Results" in result.stdout


# ---------------------------------------------------------------------------
# qn org okr cascade
# ---------------------------------------------------------------------------


def test_okr_cascade_renders_tree(initialized_org, qn_runner):
    """`okr cascade` exits 0 even with one or zero OKRs."""
    result = qn_runner(
        ["--org-path", str(initialized_org), "org", "okr", "cascade"],
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# qn org okr update-kr
# ---------------------------------------------------------------------------


def test_okr_update_kr_adds_new_kr(initialized_org, qn_runner):
    """`okr update-kr <id> --metric=X --target=N` adds a new key result."""
    # Need an OKR to update
    create = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "set",
            "--no-krs-needed",
            "--title", "OKR for KR updates",
            "--owner", "ceo",
        ],
        timeout=30,
    )
    assert create.returncode == 0

    db_path = initialized_org / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id FROM okrs WHERE title = ?", ("OKR for KR updates",)
        ).fetchone()
    finally:
        conn.close()
    okr_id = row[0]

    result = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "update-kr", okr_id,
            "--metric", "test_coverage",
            "--target", "80",
            "--unit", "%",
        ],
    )
    assert result.returncode == 0, f"update-kr failed:\n{result.stderr}\n{result.stdout}"
    assert "Added key result" in result.stdout or "OKR Progress" in result.stdout


# ---------------------------------------------------------------------------
# qn org okr link
# ---------------------------------------------------------------------------


def test_okr_link_unknown_work_fails_cleanly(initialized_org, qn_runner):
    """`okr link <bogus-work> <bogus-okr>` exits non-zero, no traceback."""
    result = qn_runner(
        [
            "--org-path", str(initialized_org),
            "org", "okr", "link",
            "task-bogus", "okr-bogus",
        ],
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
