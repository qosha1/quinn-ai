"""Dataclasses for a parsed, validated declarative org.yml spec.

The OrgSpec is the in-memory representation produced by the loader
(loader.load_org_spec). It owns the org STRUCTURE (teams, delegations,
OKRs, host/toolchain) and carries the resolved content of the $ref'd
config files (providers / roles / team templates). OrgSpec.to_org_init_config
maps the init-phase fields onto the existing OrgInitConfig so the loader
can reuse init_org() unchanged (quinn-ai-a3pg.4.3.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cli.core.constants import ORG_SPEC_DEFAULT_CEO_ROLE
from cli.core.org_init.types import OrgInitConfig, OrgInitProviderConfig
from shared.exceptions import OrgSpecError


@dataclass
class HostSpec:
    """Host-mode target: the external project root workers operate on."""

    project_root: Path


@dataclass
class ToolchainSpec:
    """CLIs a worker session needs; checked by the org-start preflight."""

    require: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)


@dataclass
class MemberSpec:
    """A declared worker seat within a team."""

    role: str
    name: Optional[str] = None
    cost: Optional[int] = None
    skills: Optional[dict] = None


@dataclass
class ManagerSpec:
    """The manager seat for a team."""

    name: str
    role: str = "Manager"
    cost: Optional[int] = None


@dataclass
class DelegationSpec:
    """An authority grant applied after hiring (loader stage 3)."""

    to: str
    level: Optional[str] = None
    roles: Optional[list[str]] = None
    max_cost: Optional[int] = None
    budget: Optional[float] = None
    max_reports: Optional[int] = None
    expires: Optional[str] = None


@dataclass
class KeyResultSpec:
    """A measurable key result on an OKR."""

    metric: str
    target: float
    unit: str = ""


@dataclass
class TeamSpec:
    """A team in the org structure.

    Under the hybrid topology: a fully-declared team (e.g. core-infra)
    lists explicit members and the loader hires them all; a seeded team
    with self_form=True (e.g. an app-group) gets only its manager + OKRs,
    and its ICs are hired later by that manager via sensemaking.
    """

    name: str
    template: Optional[str] = None
    manager: Optional[ManagerSpec] = None
    members: list[MemberSpec] = field(default_factory=list)
    self_form: bool = False
    seed_okrs: list[str] = field(default_factory=list)


@dataclass
class OkrSpec:
    """A seeded OKR (loader stage 3 creates these post-hire)."""

    title: str
    owner: Optional[str] = None
    key_results: list[KeyResultSpec] = field(default_factory=list)
    priority: Optional[int] = None
    serves: Optional[str] = None
    handle: Optional[str] = None


@dataclass
class OrgSpec:
    """A fully parsed + validated org.yml."""

    name: str
    ceo_name: str
    ceo_role: str = ORG_SPEC_DEFAULT_CEO_ROLE
    profile: Optional[str] = None
    host: Optional[HostSpec] = None
    toolchain: Optional[ToolchainSpec] = None
    providers: dict = field(default_factory=dict)
    roles: dict = field(default_factory=dict)
    team_templates: dict = field(default_factory=dict)
    teams: list[TeamSpec] = field(default_factory=list)
    delegations: list[DelegationSpec] = field(default_factory=list)
    okrs: list[OkrSpec] = field(default_factory=list)
    # Per-team credential scopes: team -> list of env var NAMES (never values).
    # '*' applies to every worker. Default-deny; see cli/core/secrets_scope.py.
    secrets: dict = field(default_factory=dict)
    source_path: Optional[Path] = None

    def to_org_init_config(self, target_path: Optional[Path] = None) -> OrgInitConfig:
        """Map the init-phase fields onto OrgInitConfig.

        In host mode, the org is laid out under the project root. In
        greenfield mode the caller must supply target_path. OKRs are
        seeded post-hire by loader stage 3, so skip_okrs is forced True
        here to avoid CEO-owned init-time OKRs.

        Args:
            target_path: Required for greenfield (no host) specs; the
                directory the new org is created in.

        Returns:
            An OrgInitConfig ready for init_org().

        Raises:
            OrgSpecError: If greenfield and no target_path was given.
        """
        if self.host is not None:
            path = self.host.project_root
            host_mode = True
        else:
            if target_path is None:
                raise OrgSpecError(
                    "greenfield org.yml requires a target path "
                    "(no host.project_root declared)"
                )
            path = target_path
            host_mode = False

        providers: list[OrgInitProviderConfig] = []
        for provider_id, provider_cfg in (self.providers.get("providers") or {}).items():
            cfg = provider_cfg if isinstance(provider_cfg, dict) else {}
            providers.append(
                OrgInitProviderConfig(
                    id=provider_id,
                    enabled=bool(cfg.get("enabled", True)),
                    api_key=cfg.get("api_key"),
                )
            )

        return OrgInitConfig(
            path=path,
            name=self.name,
            ceo_name=self.ceo_name,
            ceo_role=self.ceo_role,
            providers=providers,
            host_mode=host_mode,
            skip_okrs=True,
        )
