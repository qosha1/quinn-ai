"""$0, 100%-repeatable unit tests for the isolated host-repo canary scaffolding.

No LLM, no network — proves the throwaway Simpli repo + LOCAL bare remote + org
build + branch_on_remote predicate all work deterministically. This is what
makes the (paid, gated) host-mode canaries safe and repeatable: the only git
remote is a local bare repo, so a worker "pushing a PR" has zero blast radius.
"""

import shutil
import subprocess
import types
from pathlib import Path

import pytest

from shared.testing.canary.host_repo import (
    build_simpli_host_repo,
    pred_branch_on_remote,
    write_host_org_spec,
)


def _bd_available() -> bool:
    if shutil.which("bd"):
        return True
    try:
        from cli.core.bd_wrapper import get_bundled_bd_path

        p = get_bundled_bd_path()
        return bool(p) and Path(p).exists()
    except Exception:
        return False


def test_build_simpli_host_repo_is_isolated(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    bare = build_simpli_host_repo(project)

    # Simpli-shaped tree
    assert (project / "CLAUDE.md").exists()
    assert (project / "packages" / "utils" / "src" / "index.ts").exists()
    assert (project / "apps" / "raise").is_dir()

    # The ONLY remote is the local bare repo (no network).
    remotes = subprocess.run(
        ["git", "-C", str(project), "remote", "-v"], capture_output=True, text=True
    ).stdout
    assert "origin" in remotes
    assert str(bare) in remotes
    assert "github.com" not in remotes and "://" not in remotes.replace("file://", "")

    # main was pushed to the bare remote
    ls = subprocess.run(
        ["git", "ls-remote", "--heads", bare], capture_output=True, text=True
    ).stdout
    assert "refs/heads/main" in ls


def test_branch_on_remote_predicate(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    bare = build_simpli_host_repo(project)
    run = types.SimpleNamespace(context={"bare_remote": bare})

    # No worker branch yet -> predicate reports a violation.
    assert pred_branch_on_remote(run, {"pattern": "quinnai/"}) is not None

    # Simulate a worker shipping: push a quinnai/* branch to the bare remote.
    subprocess.run(["git", "-C", str(project), "checkout", "-q", "-b", "quinnai/quinn-ai-x-do"], check=True)
    (project / "feature.txt").write_text("x\n")
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "ship"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "push", "-q", "-u", "origin", "quinnai/quinn-ai-x-do"], check=True, capture_output=True)

    # Now the predicate passes.
    assert pred_branch_on_remote(run, {"pattern": "quinnai/"}) is None


def test_write_host_org_spec_shapes(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    spec_dir = tmp_path / "spec"

    org_yml = write_host_org_spec(spec_dir, project, app_worker=False)
    text = org_yml.read_text()
    assert "profile: simpli" in text
    assert f"project_root: {project}" in text
    assert "$ref: config/providers.yaml" in text
    assert "structure:" not in text  # CEO-only

    org_yml2 = write_host_org_spec(spec_dir, project, app_worker=True)
    assert "Remy" in org_yml2.read_text()  # app-group worker declared


@pytest.mark.skipif(not _bd_available(), reason="bd not available")
def test_host_org_builds_from_generated_spec(tmp_path):
    """The generated org.yml builds a real host-mode org (deterministic, no LLM)."""
    import sqlite3

    from cli.core.org_spec import apply_org_spec, load_org_spec

    project = tmp_path / "project"
    project.mkdir()
    (project / ".quinnai").mkdir()  # mirror the harness host_mode layout
    build_simpli_host_repo(project)
    spec_dir = tmp_path / "spec"
    org_yml = write_host_org_spec(spec_dir, project, app_worker=True)

    apply_org_spec(load_org_spec(org_yml), update=True)

    db = project / ".quinnai" / "live" / "quinn.db"
    assert db.exists()
    conn = sqlite3.connect(str(db))
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM workers")}
        root = conn.execute(
            "SELECT project_root FROM org_state WHERE id='default'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert "Quinn" in names and "Remy" in names  # CEO + app-group worker
    assert root == str(project)  # host mode points at the throwaway repo
    # profile persisted for the live CEO's briefing
    assert (project / ".quinnai" / "config" / "profile.yaml").exists()
