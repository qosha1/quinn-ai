"""E2E full-lifecycle test — one composed workflow from init through stop.

The 'golden path' that proves a fresh user can drive QuinnAI end-to-end.
Slower than the per-command tests; marked @pytest.mark.timeout(180).
"""

import sqlite3

import pytest


@pytest.mark.timeout(180)
def test_full_lifecycle_init_okrs_hire_intervene_fire_stop(temp_org_dir, qn_runner):
    """Walk every major lifecycle phase against a single org instance.

    Phases:
      1. init
      2. start (--no-spawn-ceo)
      3. status check
      4. set OKR
      5. hire
      6. board fire (intervention)
      7. stop
    """
    org = temp_org_dir
    args = lambda *cmd: ["--org-path", str(org)] + list(cmd)

    # --- 1. init ---
    # Use the default CEO name ('CEO'/'ceo') so '--manager ceo' resolves below.
    init = qn_runner(args("org", "init"), timeout=60)
    assert init.returncode == 0, f"init failed:\n{init.stderr}\n{init.stdout}"
    assert (org / "live" / "quinn.db").exists(), "quinn.db missing after init"
    assert (org / ".beads").exists(), ".beads dir missing after init"

    # --- 2. start ---
    start = qn_runner(
        args("org", "start", "--no-spawn-ceo", "--skip-config-validation"),
        timeout=60,
    )
    assert start.returncode == 0, f"start failed:\n{start.stderr}\n{start.stdout}"

    # --- 3. status ---
    status = qn_runner(args("org", "status"))
    assert status.returncode == 0
    assert "running" in status.stdout.lower(), (
        f"expected 'running' in status output:\n{status.stdout}"
    )

    # --- 4. set OKR ---
    okr = qn_runner(
        args(
            "org", "okr", "set",
            "--title", "Lifecycle test OKR",
            "--owner", "ceo",
            "--no-krs-needed",
        ),
        timeout=30,
    )
    assert okr.returncode == 0, f"okr set failed:\n{okr.stderr}\n{okr.stdout}"

    # --- 5. hire ---
    hire = qn_runner(
        args(
            "org", "hire",
            "--name", "lifecycle-eng",
            "--role", "Engineer",
            "--manager", "ceo",
        ),
        timeout=30,
    )
    assert hire.returncode == 0, f"hire failed:\n{hire.stderr}\n{hire.stdout}"

    db_path = org / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id FROM workers WHERE name = ?", ("lifecycle-eng",)
        ).fetchone()
    finally:
        conn.close()
    assert row, "hired worker not in db"
    worker_id = row[0]

    # --- 6. board fire (intervention) ---
    fire = qn_runner(
        args("board", "fire", worker_id, "--reason", "lifecycle e2e", "--force"),
        timeout=30,
    )
    assert fire.returncode == 0, f"board fire failed:\n{fire.stderr}\n{fire.stdout}"

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT status FROM workers WHERE id = ?", (worker_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "terminated", (
        f"expected status=terminated after board fire, got {row[0]!r}"
    )

    # --- 7. stop ---
    stop = qn_runner(
        args("org", "stop", "--force", "--yes"),
        timeout=60,
    )
    assert stop.returncode == 0, f"stop failed:\n{stop.stderr}\n{stop.stdout}"

    # Final status confirms not running
    final = qn_runner(args("org", "status"))
    assert final.returncode == 0
    assert "running" not in final.stdout.lower() or "stopped" in final.stdout.lower()
