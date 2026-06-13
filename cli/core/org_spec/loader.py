"""Load + resolve + validate a declarative org.yml spec.

Pipeline: read YAML -> resolve {$ref: path} pointers against the org.yml's
directory -> validate required fields and the schema version -> build a
typed OrgSpec. Pure (no DB / no side effects beyond reading config files)
so it is cheap to unit-test and reuse from the loader CLI (stage 4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cli.core.constants import (
    ORG_SPEC_API_VERSION,
    ORG_SPEC_DEFAULT_CEO_ROLE,
    ORG_SPEC_KEY_API_VERSION,
    ORG_SPEC_KEY_CEO,
    ORG_SPEC_KEY_DELEGATIONS,
    ORG_SPEC_KEY_HOST,
    ORG_SPEC_KEY_METADATA,
    ORG_SPEC_KEY_OKRS,
    ORG_SPEC_KEY_PROVIDERS,
    ORG_SPEC_KEY_ROLES,
    ORG_SPEC_KEY_STRUCTURE,
    ORG_SPEC_KEY_TEAM_TEMPLATES,
    ORG_SPEC_KEY_TOOLCHAIN,
    ORG_SPEC_REF_KEY,
)
from shared.exceptions import OrgSpecError

from .types import (
    DelegationSpec,
    HostSpec,
    KeyResultSpec,
    ManagerSpec,
    MemberSpec,
    OkrSpec,
    OrgSpec,
    TeamSpec,
    ToolchainSpec,
)


def load_org_spec(path: Path) -> OrgSpec:
    """Parse, resolve $refs, validate, and return an OrgSpec.

    Args:
        path: Path to the org.yml file.

    Returns:
        A validated OrgSpec.

    Raises:
        OrgSpecError: On missing file, parse failure, unresolvable $ref,
            unsupported apiVersion, or missing required fields.
    """
    path = Path(path)
    if not path.is_file():
        raise OrgSpecError(f"org spec not found: {path}")

    base_dir = path.parent
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise OrgSpecError(f"failed to parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise OrgSpecError(f"org spec must be a mapping, got {type(raw).__name__}")

    raw = _resolve_refs(raw, base_dir)

    _validate_api_version(raw)
    metadata = _require_mapping(raw, ORG_SPEC_KEY_METADATA, default_empty=True)
    name = metadata.get("name")
    if not name:
        raise OrgSpecError("metadata.name is required")

    ceo = _require_mapping(raw, ORG_SPEC_KEY_CEO, default_empty=True)
    ceo_name = ceo.get("name")
    if not ceo_name:
        raise OrgSpecError("ceo.name is required")

    return OrgSpec(
        name=str(name),
        ceo_name=str(ceo_name),
        ceo_role=str(ceo.get("role", ORG_SPEC_DEFAULT_CEO_ROLE)),
        profile=metadata.get("profile"),
        host=_parse_host(raw.get(ORG_SPEC_KEY_HOST), base_dir),
        toolchain=_parse_toolchain(raw.get(ORG_SPEC_KEY_TOOLCHAIN)),
        providers=_as_mapping(raw.get(ORG_SPEC_KEY_PROVIDERS), ORG_SPEC_KEY_PROVIDERS),
        roles=_as_mapping(raw.get(ORG_SPEC_KEY_ROLES), ORG_SPEC_KEY_ROLES),
        team_templates=_as_mapping(
            raw.get(ORG_SPEC_KEY_TEAM_TEMPLATES), ORG_SPEC_KEY_TEAM_TEMPLATES
        ),
        teams=_parse_teams(raw.get(ORG_SPEC_KEY_STRUCTURE)),
        delegations=_parse_delegations(raw.get(ORG_SPEC_KEY_DELEGATIONS)),
        okrs=_parse_okrs(raw.get(ORG_SPEC_KEY_OKRS)),
        source_path=path,
    )


def _resolve_refs(node: Any, base_dir: Path) -> Any:
    """Recursively replace {"$ref": "rel/path"} with the file's parsed content."""
    if isinstance(node, dict):
        if ORG_SPEC_REF_KEY in node:
            return _load_ref(node[ORG_SPEC_REF_KEY], base_dir)
        return {key: _resolve_refs(value, base_dir) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(item, base_dir) for item in node]
    return node


def _load_ref(ref: Any, base_dir: Path) -> Any:
    """Load and parse a $ref'd YAML file relative to base_dir."""
    if not isinstance(ref, str):
        raise OrgSpecError(f"{ORG_SPEC_REF_KEY} value must be a string, got {ref!r}")
    ref_path = (base_dir / ref).resolve()
    if not ref_path.is_file():
        raise OrgSpecError(f"{ORG_SPEC_REF_KEY} target not found: {ref} (resolved {ref_path})")
    try:
        return yaml.safe_load(ref_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise OrgSpecError(f"failed to parse {ORG_SPEC_REF_KEY} {ref_path}: {exc}") from exc


def _validate_api_version(raw: dict) -> None:
    version = raw.get(ORG_SPEC_KEY_API_VERSION)
    if version != ORG_SPEC_API_VERSION:
        raise OrgSpecError(
            f"unsupported {ORG_SPEC_KEY_API_VERSION} {version!r}; "
            f"expected {ORG_SPEC_API_VERSION!r}"
        )


def _require_mapping(raw: dict, key: str, *, default_empty: bool = False) -> dict:
    value = raw.get(key)
    if value is None:
        if default_empty:
            return {}
        raise OrgSpecError(f"{key} is required")
    if not isinstance(value, dict):
        raise OrgSpecError(f"{key} must be a mapping, got {type(value).__name__}")
    return value


def _as_mapping(value: Any, key: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise OrgSpecError(f"{key} must be a mapping, got {type(value).__name__}")
    return value


def _parse_host(value: Any, base_dir: Path) -> HostSpec | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise OrgSpecError(f"host must be a mapping, got {type(value).__name__}")
    project_root = value.get("project_root")
    if not project_root:
        raise OrgSpecError("host.project_root is required when host is present")
    resolved = (base_dir / str(project_root)).resolve()
    return HostSpec(project_root=resolved)


def _parse_toolchain(value: Any) -> ToolchainSpec | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise OrgSpecError(f"toolchain must be a mapping, got {type(value).__name__}")
    return ToolchainSpec(
        require=list(value.get("require", []) or []),
        optional=list(value.get("optional", []) or []),
    )


def _parse_teams(structure: Any) -> list[TeamSpec]:
    if structure is None:
        return []
    if not isinstance(structure, dict):
        raise OrgSpecError(f"structure must be a mapping, got {type(structure).__name__}")
    teams_raw = structure.get("teams", []) or []
    if not isinstance(teams_raw, list):
        raise OrgSpecError("structure.teams must be a list")

    teams: list[TeamSpec] = []
    for index, team in enumerate(teams_raw):
        if not isinstance(team, dict):
            raise OrgSpecError(f"structure.teams[{index}] must be a mapping")
        team_name = team.get("name")
        if not team_name:
            raise OrgSpecError(f"structure.teams[{index}].name is required")
        teams.append(
            TeamSpec(
                name=str(team_name),
                template=team.get("template"),
                manager=_parse_manager(team.get("manager")),
                members=_parse_members(team.get("members"), team_name),
                self_form=bool(team.get("selfForm", False)),
                seed_okrs=list(team.get("seedOkrs", []) or []),
            )
        )
    return teams


def _parse_manager(value: Any) -> ManagerSpec | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise OrgSpecError(f"team.manager must be a mapping, got {type(value).__name__}")
    name = value.get("name")
    if not name:
        raise OrgSpecError("team.manager.name is required when a manager is declared")
    return ManagerSpec(
        name=str(name),
        role=str(value.get("role", "Manager")),
        cost=value.get("cost"),
    )


def _parse_members(value: Any, team_name: str) -> list[MemberSpec]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OrgSpecError(f"team '{team_name}' members must be a list")
    members: list[MemberSpec] = []
    for index, member in enumerate(value):
        if not isinstance(member, dict):
            raise OrgSpecError(f"team '{team_name}' members[{index}] must be a mapping")
        role = member.get("role")
        if not role:
            raise OrgSpecError(f"team '{team_name}' members[{index}].role is required")
        members.append(
            MemberSpec(
                role=str(role),
                name=member.get("name"),
                cost=member.get("cost"),
                skills=member.get("skills"),
            )
        )
    return members


def _parse_delegations(value: Any) -> list[DelegationSpec]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OrgSpecError("delegations must be a list")
    grants: list[DelegationSpec] = []
    for index, grant in enumerate(value):
        if not isinstance(grant, dict):
            raise OrgSpecError(f"delegations[{index}] must be a mapping")
        to = grant.get("to")
        if not to:
            raise OrgSpecError(f"delegations[{index}].to is required")
        grants.append(
            DelegationSpec(
                to=str(to),
                level=grant.get("level"),
                roles=grant.get("roles"),
                max_cost=grant.get("max_cost"),
                budget=grant.get("budget"),
                max_reports=grant.get("max_reports"),
                expires=grant.get("expires"),
            )
        )
    return grants


def _parse_okrs(value: Any) -> list[OkrSpec]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OrgSpecError("okrs must be a list")
    okrs: list[OkrSpec] = []
    for index, okr in enumerate(value):
        if not isinstance(okr, dict):
            raise OrgSpecError(f"okrs[{index}] must be a mapping")
        title = okr.get("title")
        if not title:
            raise OrgSpecError(f"okrs[{index}].title is required")
        okrs.append(
            OkrSpec(
                title=str(title),
                owner=okr.get("owner"),
                key_results=_parse_key_results(okr.get("keyResults"), index),
                priority=okr.get("priority"),
                serves=okr.get("serves"),
                handle=okr.get("id"),
            )
        )
    return okrs


def _parse_key_results(value: Any, okr_index: int) -> list[KeyResultSpec]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OrgSpecError(f"okrs[{okr_index}].keyResults must be a list")
    results: list[KeyResultSpec] = []
    for kr_index, kr in enumerate(value):
        if not isinstance(kr, dict):
            raise OrgSpecError(f"okrs[{okr_index}].keyResults[{kr_index}] must be a mapping")
        metric = kr.get("metric")
        if not metric:
            raise OrgSpecError(
                f"okrs[{okr_index}].keyResults[{kr_index}].metric is required"
            )
        results.append(
            KeyResultSpec(
                metric=str(metric),
                target=float(kr.get("target", 0)),
                unit=str(kr.get("unit", "")),
            )
        )
    return results
