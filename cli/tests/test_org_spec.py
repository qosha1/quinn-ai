"""Tests for the declarative org.yml spec loader (quinn-ai-a3pg.4.2).

The loader parses an org.yml, resolves $ref pointers to the existing
config files (providers.yaml / worker-templates.yaml / templates.yaml),
validates the structure, and exposes a validated OrgSpec that maps onto
OrgInitConfig for the init phase of the loader (quinn-ai-a3pg.4.3.1).
"""

import textwrap
from pathlib import Path

import pytest

from cli.core.org_spec import OrgSpec, OrgSpecError, load_org_spec


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


def _make_org(tmp_path: Path, org_yml: str) -> Path:
    """Lay down the $ref'd config files + an org.yml; return the org.yml path."""
    _write(
        tmp_path / "config" / "providers.yaml",
        """
        default: claude_code
        authorized_providers: [claude_code]
        providers:
          claude_code: { enabled: true }
        """,
    )
    _write(
        tmp_path / "config" / "worker-templates.yaml",
        """
        templates:
          backend-engineer: { cost: 70 }
        """,
    )
    _write(
        tmp_path / "config" / "templates.yaml",
        """
        version: 1
        templates:
          - { name: core-infra, members: [] }
          - { name: app-group, members: [] }
        """,
    )
    org_path = tmp_path / "org.yml"
    _write(org_path, org_yml)
    return org_path


MINIMAL = """
    apiVersion: quinnai/v1
    metadata: { name: simpli }
    ceo: { name: Quinn, role: CEO }
    providers: { $ref: config/providers.yaml }
"""

FULL = """
    apiVersion: quinnai/v1
    metadata: { name: simpli, profile: simpli }
    host: { project_root: ./project }
    toolchain: { require: [node, pnpm], optional: [docker] }
    providers: { $ref: config/providers.yaml }
    roles: { $ref: config/worker-templates.yaml }
    teamTemplates: { $ref: config/templates.yaml }
    ceo: { name: Quinn, role: CEO }
    structure:
      teams:
        - template: core-infra
          name: core-infra
          manager: { name: Dana, role: Director }
          members:
            - { role: backend-engineer, cost: 70 }
        - { template: app-group, name: raise, manager: { name: Remy, role: Lead }, selfForm: true }
    delegations:
      - { to: core-infra/Dana, level: director, budget: 20000 }
    okrs:
      - { title: "Reliability", owner: core-infra/Dana, keyResults: [{ metric: coverage, target: 80, unit: "%" }] }
"""


def test_load_minimal(tmp_path):
    spec = load_org_spec(_make_org(tmp_path, MINIMAL))
    assert isinstance(spec, OrgSpec)
    assert spec.name == "simpli"
    assert spec.ceo_name == "Quinn"
    assert spec.ceo_role == "CEO"
    assert spec.host is None


def test_ref_resolution(tmp_path):
    spec = load_org_spec(_make_org(tmp_path, MINIMAL))
    # $ref replaced by the referenced file's parsed content
    assert spec.providers["default"] == "claude_code"
    assert "claude_code" in spec.providers["providers"]


def test_missing_name_raises(tmp_path):
    org = _make_org(
        tmp_path,
        """
        apiVersion: quinnai/v1
        metadata: {}
        ceo: { name: Quinn }
        """,
    )
    with pytest.raises(OrgSpecError):
        load_org_spec(org)


def test_missing_ceo_raises(tmp_path):
    org = _make_org(
        tmp_path,
        """
        apiVersion: quinnai/v1
        metadata: { name: simpli }
        """,
    )
    with pytest.raises(OrgSpecError):
        load_org_spec(org)


def test_bad_api_version_raises(tmp_path):
    org = _make_org(
        tmp_path,
        """
        apiVersion: quinnai/v2
        metadata: { name: simpli }
        ceo: { name: Quinn }
        """,
    )
    with pytest.raises(OrgSpecError):
        load_org_spec(org)


def test_missing_ref_file_raises(tmp_path):
    org = _make_org(
        tmp_path,
        """
        apiVersion: quinnai/v1
        metadata: { name: simpli }
        ceo: { name: Quinn }
        providers: { $ref: config/does-not-exist.yaml }
        """,
    )
    with pytest.raises(OrgSpecError):
        load_org_spec(org)


def test_full_parse(tmp_path):
    spec = load_org_spec(_make_org(tmp_path, FULL))
    assert spec.profile == "simpli"
    assert spec.toolchain is not None
    assert spec.toolchain.require == ["node", "pnpm"]
    assert spec.toolchain.optional == ["docker"]
    assert len(spec.teams) == 2

    core = spec.teams[0]
    assert core.template == "core-infra"
    assert core.name == "core-infra"
    assert core.self_form is False
    assert core.manager is not None and core.manager.name == "Dana"
    assert len(core.members) == 1 and core.members[0].role == "backend-engineer"
    assert core.members[0].cost == 70

    app = spec.teams[1]
    assert app.template == "app-group"
    assert app.self_form is True
    assert app.manager.name == "Remy"
    assert app.members == []

    assert len(spec.delegations) == 1
    assert spec.delegations[0].to == "core-infra/Dana"
    assert spec.delegations[0].level == "director"
    assert spec.delegations[0].budget == 20000

    assert len(spec.okrs) == 1
    assert spec.okrs[0].owner == "core-infra/Dana"
    assert spec.okrs[0].key_results[0].metric == "coverage"
    assert spec.okrs[0].key_results[0].target == 80


def test_host_project_root_resolved_to_abs(tmp_path):
    org = _make_org(tmp_path, FULL)
    (tmp_path / "project").mkdir()
    spec = load_org_spec(org)
    assert spec.host is not None
    assert spec.host.project_root.is_absolute()
    assert spec.host.project_root == (tmp_path / "project").resolve()


def test_to_org_init_config_host_mode(tmp_path):
    org = _make_org(tmp_path, FULL)
    (tmp_path / "project").mkdir()
    spec = load_org_spec(org)
    cfg = spec.to_org_init_config()
    assert cfg.ceo_name == "Quinn"
    assert cfg.ceo_role == "CEO"
    assert cfg.host_mode is True
    assert cfg.path == spec.host.project_root
    # OKRs are seeded post-hire by loader stage 3, not at init
    assert cfg.skip_okrs is True
    assert any(p.id == "claude_code" and p.enabled for p in cfg.providers)


def test_to_org_init_config_greenfield_requires_target(tmp_path):
    spec = load_org_spec(_make_org(tmp_path, MINIMAL))
    with pytest.raises(OrgSpecError):
        spec.to_org_init_config()  # no host, no target path
    cfg = spec.to_org_init_config(target_path=tmp_path / "neworg")
    assert cfg.host_mode is False
    assert cfg.path == tmp_path / "neworg"
