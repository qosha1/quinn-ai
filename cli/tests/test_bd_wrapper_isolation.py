"""Regression test for quinn-ai-43d.

run_bd in cli/core/bd_wrapper.py was leaking writes into a parent-dir
.beads when invoked from inside a repo that has its own .beads (and
the target org's .beads is dolt-backed). Two co-causes:

1. subprocess.run was called without cwd= — bd inherited the test
   runner's cwd (the QuinnAI repo) and used its own discovery.
2. --db=<beads_dir>/beads.db points at a non-existent file when the
   org is dolt-backed (the actual storage is in embeddeddolt/).

Fix: pass cwd=org_path AND make the --db arg meaningful for dolt orgs.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from cli.core.bd_wrapper import run_bd, get_bundled_bd_path


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git required to bootstrap a fresh org's .beads",
)


def _make_org_with_beads(tmp_path: Path) -> Path:
    """Set up a minimal org dir with an initialized .beads/."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()
    # bd init expects to run in a git repo
    subprocess.run(["git", "init", "-q"], cwd=org_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=org_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=org_path,
        check=True,
    )
    # bd init via run_bd's same path: the actual init_beads helper
    bd_path = get_bundled_bd_path()
    env = os.environ.copy()
    env["BEADS_DIR"] = str(org_path / ".beads")
    subprocess.run(
        [str(bd_path), "init", "--skip-hooks", "--non-interactive"],
        cwd=org_path,
        env=env,
        check=True,
        capture_output=True,
    )
    return org_path


def test_run_bd_create_writes_to_target_org_not_parent_repo(tmp_path):
    """bd create through run_bd must write to the org_path's .beads,
    even when the calling process's cwd is a different repo with its
    own .beads/. Regression test for quinn-ai-43d."""
    org_path = _make_org_with_beads(tmp_path)

    # Confirm target org has zero issues to start.
    bd_path = get_bundled_bd_path()
    env_check = os.environ.copy()
    env_check["BEADS_DIR"] = str(org_path / ".beads")
    before = subprocess.run(
        [str(bd_path), "list", "--json"],
        cwd=org_path,
        env=env_check,
        capture_output=True,
        text=True,
    )
    # bd list --json may print non-JSON before the array; lenient parse
    import re
    m = re.search(r"\[.*\]", before.stdout, re.DOTALL)
    issue_count_before = len(json.loads(m.group(0))) if m else 0

    # Now invoke run_bd from a working directory that is NOT the org —
    # this simulates the test-runner cwd being elsewhere.
    original_cwd = os.getcwd()
    try:
        # Create the bead via run_bd
        result = run_bd(
            args=[
                "create", "Isolation test bead",
                "--type=task", "--priority=2",
                "--description=test",
            ],
            org_path=org_path,
            skip_permission_check=True,
            skip_lifecycle_check=True,
            skip_okr_check=True,
            capture_output=True,
        )
        assert result.returncode == 0, (
            f"bd create failed: stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        # Verify the bead landed in the TARGET org's .beads
        after = subprocess.run(
            [str(bd_path), "list", "--json"],
            cwd=org_path,
            env=env_check,
            capture_output=True,
            text=True,
        )
        m2 = re.search(r"\[.*\]", after.stdout, re.DOTALL)
        issue_count_after = len(json.loads(m2.group(0))) if m2 else 0

        assert issue_count_after == issue_count_before + 1, (
            f"Expected target org's .beads to gain 1 issue. "
            f"Before: {issue_count_before}, After: {issue_count_after}\n"
            f"List output:\n{after.stdout}"
        )
    finally:
        os.chdir(original_cwd)
