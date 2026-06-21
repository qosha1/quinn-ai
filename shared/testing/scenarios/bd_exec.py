"""Dolt-aware direct bd invocation for scenario ops + predicates.

Mirrors cli.core.bd_wrapper.run_bd's backend handling (quinn-ai-k9ff / boov):
dolt-backed orgs (the default since 1.0+) keep the database in
.beads/embeddeddolt/, NOT .beads/beads.db. Pinning --db=beads.db there opens a
separate, empty sqlite with no issue_prefix config, so bd writes fail
("issue_prefix config is missing") and reads find nothing ("qn-bd show
failed"). For dolt we drop --db, set BEADS_DIR, and prefer the system bd (the
bundled 0.43 mishandles dolt metadata); only legacy sqlite orgs pin --db.

Both op_create_bead/op_claim_bead (ops.py) and the bd-reading predicates
(predicates.py) route through here so the scenario harness talks to the same
backend the org actually uses.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def bd_exec(
    org_path: Path,
    args: list[str],
    *,
    timeout: int = 30,
    worker_id: str | None = None,
) -> subprocess.CompletedProcess:
    """Run a bd command against the org's beads backend, capturing output."""
    from cli.core.bd_wrapper import (
        get_bundled_bd_path,
        get_org_beads_dir,
        is_dolt_backend,
    )

    beads_dir = get_org_beads_dir(org_path)
    dolt_mode = is_dolt_backend(beads_dir)
    bd_path = get_bundled_bd_path(prefer_system=dolt_mode)

    env = os.environ.copy()
    env["BEADS_DIR"] = str(beads_dir)
    if worker_id:
        env["QUINN_WORKER_ID"] = worker_id
        env["BEADS_ASSIGNEE"] = worker_id

    cmd = [str(bd_path), "--sandbox"]
    if not dolt_mode:
        env["BEADS_DB"] = str(beads_dir / "beads.db")
        cmd.append(f"--db={beads_dir / 'beads.db'}")
    cmd += args
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env
    )
