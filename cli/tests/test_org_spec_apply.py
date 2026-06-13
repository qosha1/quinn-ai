"""Integration test for the org.yml loader (quinn-ai-a3pg.4.3).

Applies a small declarative org.yml against a fresh greenfield org and
asserts the instantiated structure (workers, teams, OKR owner) in the DB.
This is the write-first test gating the loader stages; it exercises the
real init_org + query helpers (so it needs git + bd available).
"""

import shutil
import sqlite3
import textwrap
from pathlib import Path

import pytest


def _bd_available() -> bool:
    if shutil.which("bd"):
        return True
    try:
        from cli.core.bd_wrapper import get_bundled_bd_path

        path = get_bundled_bd_path()
        return bool(path) and Path(path).exists()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _bd_available(), reason="bd not available")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


ORG_YML = """
    apiVersion: quinnai/v1
    metadata: { name: testorg }
    providers: { $ref: config/providers.yaml }
    ceo: { name: Quinn, role: CEO }
    structure:
      teams:
        - name: core
          manager: { name: Dana, role: Director }
          members:
            - { role: engineer, cost: 60 }
        - { name: app, manager: { name: Remy, role: Lead }, selfForm: true }
    okrs:
      - { title: "Reliability", owner: core/Dana, keyResults: [{ metric: coverage, target: 80, unit: "%" }] }
"""


def test_apply_builds_declared_structure(tmp_path):
    from cli.core.org_spec import apply_org_spec, load_org_spec

    src = tmp_path / "src"
    _write(
        src / "config" / "providers.yaml",
        """
        default: claude_code
        authorized_providers: [claude_code]
        providers:
          claude_code: { enabled: true }
        """,
    )
    _write(src / "org.yml", ORG_YML)

    spec = load_org_spec(src / "org.yml")
    org_dir = tmp_path / "org"
    org_dir.mkdir(parents=True)
    result = apply_org_spec(spec, target_path=org_dir)

    # init happened
    db_path = org_dir / "live" / "quinn.db"
    assert db_path.exists(), "org db should exist after apply"

    conn = sqlite3.connect(str(db_path))
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM workers WHERE status != 'terminated'"
            ).fetchall()
        }
        # CEO + core manager + 1 declared core member + app manager (self-form: no ICs)
        assert "Quinn" in names
        assert "Dana" in names
        assert "Remy" in names
        assert any(n.startswith("engineer-core") for n in names), names
        assert len(names) == 4, names

        team_names = {
            row[0] for row in conn.execute("SELECT name FROM teams").fetchall()
        }
        assert {"core", "app"} <= team_names

        # OKR seeded and owned by the core manager (Dana), not the CEO
        dana_id = result.worker_ids["core/Dana"]
        okr_owner = conn.execute(
            "SELECT owner_worker_id FROM okrs WHERE title = ?", ("Reliability",)
        ).fetchone()
        assert okr_owner is not None
        assert okr_owner[0] == dana_id
    finally:
        conn.close()

    # app team self-forms: no IC seats pre-hired under it
    assert "app/Remy" in result.worker_ids
    assert not any(h.startswith("app/") and h != "app/Remy" for h in result.worker_ids)
    assert result.okr_ids
