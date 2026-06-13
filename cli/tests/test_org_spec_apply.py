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


DELEGATION_ORG_YML = """
    apiVersion: quinnai/v1
    metadata: { name: delorg }
    providers: { $ref: config/providers.yaml }
    ceo: { name: Quinn, role: CEO }
    structure:
      teams:
        - { name: app, manager: { name: Remy, role: Lead }, selfForm: true }
    delegations:
      - { to: app/Remy, level: team-lead, budget: 500 }
"""


def test_apply_applies_delegations(tmp_path):
    """org.yml delegations grant the delegate authority+budget so they can hire.

    Write-first for quinn-ai-a3pg.4.3.3.1 — fails until _apply_delegations lands.
    """
    from cli.core.db import get_org_db_path, open_database
    from cli.core.org_spec import apply_org_spec, load_org_spec
    from cli.core.worker import Worker

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
    _write(src / "org.yml", DELEGATION_ORG_YML)

    spec = load_org_spec(src / "org.yml")
    org_dir = tmp_path / "org"
    org_dir.mkdir(parents=True)
    result = apply_org_spec(spec, target_path=org_dir)

    remy_id = result.worker_ids["app/Remy"]
    db = open_database(get_org_db_path(result.org_path))
    try:
        remy = Worker(db, remy_id)
        scope = remy.hiring_authority_scope
        assert set(scope.allowed_roles) == {"engineer", "designer", "qa"}, scope.allowed_roles
        assert scope.max_cost == 60
        assert remy.delegated_budget == 500
        # The whole point: the self-form Lead can now hire an IC.
        can_hire, reason = remy.can_hire("engineer", 50)
        assert can_hire, reason
    finally:
        db.close()


PROFILE_ORG_YML = """
    apiVersion: quinnai/v1
    metadata: { name: proforg, profile: simpli }
    providers: { $ref: config/providers.yaml }
    ceo: { name: Quinn, role: CEO }
"""


def test_apply_persists_profile_overlay(tmp_path):
    """org.yml profile resolves profiles/<name>.yaml and persists it to org config.

    Write-first for quinn-ai-a3pg.4.4 — fails until _apply_profile lands.
    """
    import yaml

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
    _write(
        src / "profiles" / "simpli.yaml",
        """
        profile: simpli
        conventions:
          - "Shared packages over app src"
          - "camelCase on the wire"
        """,
    )
    _write(src / "org.yml", PROFILE_ORG_YML)

    spec = load_org_spec(src / "org.yml")
    org_dir = tmp_path / "org"
    org_dir.mkdir(parents=True)
    result = apply_org_spec(spec, target_path=org_dir)

    persisted = org_dir / "config" / "profile.yaml"
    assert persisted.exists(), "profile overlay should be persisted to org config"
    data = yaml.safe_load(persisted.read_text())
    assert data["profile"] == "simpli"
    assert "Shared packages over app src" in data["conventions"]
    assert not result.warnings, result.warnings


TOOLCHAIN_ORG_YML = """
    apiVersion: quinnai/v1
    metadata: { name: toolorg }
    providers: { $ref: config/providers.yaml }
    toolchain: { require: [node, pnpm], optional: [docker] }
    ceo: { name: Quinn, role: CEO }
"""


def test_apply_persists_toolchain_contract(tmp_path):
    """org.yml toolchain is persisted for the org-start preflight (quinn-ai-a3pg.1.2)."""
    import yaml

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
    _write(src / "org.yml", TOOLCHAIN_ORG_YML)

    spec = load_org_spec(src / "org.yml")
    org_dir = tmp_path / "org"
    org_dir.mkdir(parents=True)
    apply_org_spec(spec, target_path=org_dir)

    persisted = org_dir / "config" / "toolchain.yaml"
    assert persisted.exists()
    data = yaml.safe_load(persisted.read_text())
    assert data["require"] == ["node", "pnpm"]
    assert data["optional"] == ["docker"]


def test_init_from_cli(tmp_path):
    """E2E: `qn org init --from org.yml` builds the declared org (quinn-ai-a3pg.3.6)."""
    from click.testing import CliRunner

    from cli.commands.main import qn

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

    org_dir = tmp_path / "org"
    org_dir.mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        qn,
        ["--org-path", str(org_dir), "org", "init", "--from", str(src / "org.yml")],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "testorg" in result.output

    conn = sqlite3.connect(str(org_dir / "live" / "quinn.db"))
    try:
        worker_count = conn.execute(
            "SELECT COUNT(*) FROM workers WHERE status != 'terminated'"
        ).fetchone()[0]
        assert worker_count == 4, result.output
        team_count = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        assert team_count >= 2
        okr_count = conn.execute("SELECT COUNT(*) FROM okrs").fetchone()[0]
        assert okr_count == 1
    finally:
        conn.close()
