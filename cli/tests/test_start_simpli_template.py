"""Capstone: the committed start-simpli template builds end-to-end (quinn-ai-a3pg).

Validates the actual example_orgs/org-scripts/start-simpli/org.yml through the
real loader — parse (topology) and apply (full org instantiation). Deterministic,
no live LLM. The paid live-LLM canary (CEO edits a real Simpli package) is the
opt-in capstone tracked separately.
"""

import shutil
import sqlite3
from pathlib import Path

import cli
import pytest

REPO_ROOT = Path(cli.__file__).resolve().parent.parent
SCAFFOLD = REPO_ROOT / "example_orgs" / "org-scripts" / "start-simpli" / "org.yml"


def _bd_available() -> bool:
    if shutil.which("bd"):
        return True
    try:
        from cli.core.bd_wrapper import get_bundled_bd_path

        path = get_bundled_bd_path()
        return bool(path) and Path(path).exists()
    except Exception:
        return False


def test_scaffold_org_yml_exists():
    assert SCAFFOLD.is_file(), f"start-simpli template missing at {SCAFFOLD}"


def test_scaffold_topology_parses():
    from cli.core.org_spec import load_org_spec

    spec = load_org_spec(SCAFFOLD)
    assert spec.name == "simpli"
    assert spec.profile == "simpli"
    assert spec.host is not None  # host-mode against the start-simpli checkout
    assert spec.toolchain is not None and "pnpm" in spec.toolchain.require

    teams = {t.name: t for t in spec.teams}
    assert {"core-infra", "raise", "market"} <= set(teams)

    core = teams["core-infra"]
    assert core.self_form is False
    assert len(core.members) == 3  # backend / platform / package-maintainer

    assert teams["raise"].self_form is True
    assert teams["market"].self_form is True

    assert len(spec.delegations) == 3
    assert len(spec.okrs) == 3


@pytest.mark.skipif(not _bd_available(), reason="bd not available")
def test_scaffold_builds_full_org(tmp_path):
    """Apply the real template (greenfield) and assert the Simpli org is built."""
    from cli.core.org_spec import apply_org_spec, load_org_spec

    spec = load_org_spec(SCAFFOLD)
    # Build in a throwaway greenfield org instead of the real start-simpli repo.
    spec.host = None

    org_dir = tmp_path / "org"
    org_dir.mkdir(parents=True)
    result = apply_org_spec(spec, target_path=org_dir)

    db_path = org_dir / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM workers WHERE status != 'terminated'"
            ).fetchall()
        }
        # CEO + core-infra (Dana + 3 declared ICs) + raise Lead + market Lead = 7
        assert {"Quinn", "Dana", "Remy", "Mara"} <= names
        assert len(names) == 7, names

        team_names = {r[0] for r in conn.execute("SELECT name FROM teams").fetchall()}
        assert {"core-infra", "raise", "market"} <= team_names

        okr_count = conn.execute("SELECT COUNT(*) FROM okrs").fetchone()[0]
        assert okr_count == 3
    finally:
        conn.close()

    # profile + toolchain persisted from the real template
    assert (org_dir / "config" / "profile.yaml").exists()
    assert (org_dir / "config" / "toolchain.yaml").exists()
    assert len(result.okr_ids) == 3
