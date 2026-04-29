"""Loader for org-templates YAML files.

Per quinn-ai-iabn §A and quinn-ai-u0h2:
- `load_templates(org_path)` reads `<org_path>/config/templates.yaml`.
- Falls back to the bundled default catalog when the file is absent.
- Empty `templates: []` (with `version: 1`) is valid and produces a zero-template
  registry — operator's explicit choice.
- Strict schema: unknown keys at template or member level are rejected.
- `requires` referencing an unknown template name is rejected at LOAD time
  (per iabn §C.2 — composition is reference-existing only).
- Templates sorted deterministically by `name`.
- Cost is an int in [0, 100] — strings/floats/bools rejected.
- Exactly one member with `is_manager: true` per template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cli.core.templates.types import (
    ChannelSpec,
    InitialOKR,
    Template,
    TemplateMember,
    TemplateRegistry,
)
from shared.exceptions import TemplateError


_TEMPLATE_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "members",
        "channel",
        "requires",
        "initial_okrs",
        "ttl_hours",
    }
)
_MEMBER_KEYS: frozenset[str] = frozenset({"role", "count", "cost", "is_manager"})
_CHANNEL_KEYS: frozenset[str] = frozenset({"auto_create", "name_template"})
_OKR_KEYS: frozenset[str] = frozenset({"title", "description", "key_results"})


class TemplateSchemaError(TemplateError):
    """Raised when templates.yaml fails schema validation."""

    def __init__(self, source_path: "Path | str", message: str):
        self.source_path = source_path
        super().__init__(f"Invalid templates schema in {source_path}: {message}")


def _default_catalog_path() -> Path:
    """Absolute path to the bundled default team-templates catalog."""
    return (
        Path(__file__).resolve().parents[2]
        / "config"
        / "default_team_templates.yaml"
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text()
    except OSError as exc:
        raise TemplateSchemaError(path, f"could not read file: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TemplateSchemaError(path, f"YAML parse error: {exc}") from exc

    if data is None:
        raise TemplateSchemaError(path, "file is empty; expected at least `version: 1`")
    if not isinstance(data, dict):
        raise TemplateSchemaError(
            path, f"top-level must be a mapping, got {type(data).__name__}"
        )
    return data


def _strict_keys(
    raw: dict[str, Any],
    allowed: frozenset[str],
    *,
    context: str,
    source_path: Path,
) -> None:
    extras = set(raw) - allowed
    if extras:
        raise TemplateSchemaError(
            source_path,
            f"{context}: unknown/unexpected key(s) {sorted(extras)} (allowed: {sorted(allowed)})",
        )


def _validate_cost(raw: Any, *, role: str, source_path: Path) -> int:
    # Bools are a subclass of int in Python; explicitly reject.
    if isinstance(raw, bool):
        raise TemplateSchemaError(
            source_path, f"member role={role!r}: cost must be int, got bool {raw!r}"
        )
    if not isinstance(raw, int):
        raise TemplateSchemaError(
            source_path,
            f"member role={role!r}: cost must be int in [0,100], got {type(raw).__name__} {raw!r}",
        )
    if not (0 <= raw <= 100):
        raise TemplateSchemaError(
            source_path,
            f"member role={role!r}: cost must be in [0,100], got {raw}",
        )
    return raw


def _build_member(raw: Any, *, source_path: Path) -> TemplateMember:
    if not isinstance(raw, dict):
        raise TemplateSchemaError(
            source_path,
            f"each member must be a mapping, got {type(raw).__name__}",
        )

    for required in ("role", "count", "cost"):
        if required not in raw:
            raise TemplateSchemaError(
                source_path,
                f"member missing required key {required!r}: {raw!r}",
            )

    _strict_keys(raw, _MEMBER_KEYS, context=f"member role={raw.get('role')!r}", source_path=source_path)

    role = raw["role"]
    if not isinstance(role, str) or not role:
        raise TemplateSchemaError(source_path, f"member.role must be a non-empty string: {role!r}")

    count = raw["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise TemplateSchemaError(
            source_path,
            f"member role={role!r}: count must be a positive int, got {count!r}",
        )

    cost = _validate_cost(raw["cost"], role=role, source_path=source_path)

    is_manager_raw = raw.get("is_manager", False)
    if not isinstance(is_manager_raw, bool):
        raise TemplateSchemaError(
            source_path,
            f"member role={role!r}: is_manager must be bool, got {is_manager_raw!r}",
        )

    return TemplateMember(role=role, count=count, cost=cost, is_manager=is_manager_raw)


def _build_channel(raw: Any, *, template_name: str, source_path: Path) -> ChannelSpec:
    if not isinstance(raw, dict):
        raise TemplateSchemaError(
            source_path,
            f"template {template_name!r}: channel must be a mapping, got {type(raw).__name__}",
        )
    _strict_keys(raw, _CHANNEL_KEYS, context=f"template {template_name!r} channel", source_path=source_path)
    auto_create = raw.get("auto_create", True)
    if not isinstance(auto_create, bool):
        raise TemplateSchemaError(
            source_path,
            f"template {template_name!r}: channel.auto_create must be bool",
        )
    name_template = raw.get("name_template", "")
    if not isinstance(name_template, str):
        raise TemplateSchemaError(
            source_path,
            f"template {template_name!r}: channel.name_template must be a string",
        )
    return ChannelSpec(auto_create=auto_create, name_template=name_template)


def _build_okr(raw: Any, *, template_name: str, source_path: Path) -> InitialOKR:
    if not isinstance(raw, dict):
        raise TemplateSchemaError(
            source_path,
            f"template {template_name!r}: each initial_okr must be a mapping",
        )
    _strict_keys(raw, _OKR_KEYS, context=f"template {template_name!r} initial_okr", source_path=source_path)
    for required in ("title", "description"):
        if required not in raw:
            raise TemplateSchemaError(
                source_path,
                f"template {template_name!r}: initial_okr missing required key {required!r}",
            )
    krs_raw = raw.get("key_results", [])
    if not isinstance(krs_raw, list):
        raise TemplateSchemaError(
            source_path,
            f"template {template_name!r}: initial_okr.key_results must be a list",
        )
    return InitialOKR(
        title=str(raw["title"]),
        description=str(raw["description"]),
        key_results=tuple(krs_raw),
    )


def _build_template(raw: Any, *, source_path: Path) -> Template:
    if not isinstance(raw, dict):
        raise TemplateSchemaError(
            source_path,
            f"each template must be a mapping, got {type(raw).__name__}",
        )

    for required in ("name", "description", "members"):
        if required not in raw:
            raise TemplateSchemaError(
                source_path,
                f"template missing required key {required!r}: {raw!r}",
            )

    name = raw["name"]
    if not isinstance(name, str) or not name:
        raise TemplateSchemaError(source_path, f"template.name must be a non-empty string: {name!r}")

    _strict_keys(raw, _TEMPLATE_KEYS, context=f"template {name!r}", source_path=source_path)

    description = raw["description"]
    if not isinstance(description, str):
        raise TemplateSchemaError(source_path, f"template {name!r}: description must be a string")

    members_raw = raw["members"]
    if not isinstance(members_raw, list) or not members_raw:
        raise TemplateSchemaError(
            source_path,
            f"template {name!r}: members must be a non-empty list",
        )
    members = tuple(_build_member(m, source_path=source_path) for m in members_raw)

    # Per iabn §A.2: exactly one is_manager per template.
    manager_count = sum(1 for m in members if m.is_manager)
    if manager_count != 1:
        raise TemplateSchemaError(
            source_path,
            f"template {name!r}: must have exactly one member with is_manager: true (found {manager_count})",
        )

    channel = (
        _build_channel(raw["channel"], template_name=name, source_path=source_path)
        if "channel" in raw
        else None
    )

    requires_raw = raw.get("requires", [])
    if not isinstance(requires_raw, list):
        raise TemplateSchemaError(
            source_path,
            f"template {name!r}: requires must be a list of template names",
        )
    requires = tuple(str(r) for r in requires_raw)

    initial_okrs_raw = raw.get("initial_okrs", [])
    if not isinstance(initial_okrs_raw, list):
        raise TemplateSchemaError(
            source_path,
            f"template {name!r}: initial_okrs must be a list",
        )
    initial_okrs = tuple(
        _build_okr(o, template_name=name, source_path=source_path)
        for o in initial_okrs_raw
    )

    ttl_hours_raw = raw.get("ttl_hours")
    if ttl_hours_raw is not None:
        if isinstance(ttl_hours_raw, bool) or not isinstance(ttl_hours_raw, int) or ttl_hours_raw < 1:
            raise TemplateSchemaError(
                source_path,
                f"template {name!r}: ttl_hours must be a positive int or null",
            )

    return Template(
        name=name,
        description=description,
        members=members,
        channel=channel,
        requires=requires,
        initial_okrs=initial_okrs,
        ttl_hours=ttl_hours_raw,
    )


def _build_registry(data: dict[str, Any], *, source_path: Path) -> TemplateRegistry:
    version = data.get("version")
    if version != 1:
        raise TemplateSchemaError(source_path, f"unsupported version: {version!r} (expected 1)")

    templates_raw = data.get("templates")
    if templates_raw is None:
        raise TemplateSchemaError(
            source_path, "missing 'templates' key (use `templates: []` for none)"
        )
    if not isinstance(templates_raw, list):
        raise TemplateSchemaError(
            source_path, f"'templates' must be a list, got {type(templates_raw).__name__}"
        )

    templates = tuple(_build_template(t, source_path=source_path) for t in templates_raw)

    # Reject duplicate template names.
    seen: set[str] = set()
    for tmpl in templates:
        if tmpl.name in seen:
            raise TemplateSchemaError(
                source_path, f"duplicate template name: {tmpl.name!r}"
            )
        seen.add(tmpl.name)

    # `requires` referential integrity at LOAD time.
    declared_names = {t.name for t in templates}
    for tmpl in templates:
        for required in tmpl.requires:
            if required not in declared_names:
                raise TemplateSchemaError(
                    source_path,
                    f"template {tmpl.name!r}: requires references unknown template {required!r}; "
                    f"known templates: {sorted(declared_names)}",
                )

    # Deterministic order by name.
    templates = tuple(sorted(templates, key=lambda t: t.name))

    return TemplateRegistry(
        version=version,
        templates=templates,
        source_path=str(source_path),
    )


def load_templates(org_path: Path) -> TemplateRegistry:
    """Read the org's templates.yaml. Fall back to bundled default catalog when absent.

    Args:
        org_path: Org root directory; loader reads `<org_path>/config/templates.yaml`.

    Returns:
        TemplateRegistry with templates sorted deterministically by name.

    Raises:
        TemplateSchemaError: malformed YAML, schema-violating content, or unknown
            template referenced via `requires`.
    """
    org_templates = org_path / "config" / "templates.yaml"
    if org_templates.exists():
        target = org_templates
    else:
        target = _default_catalog_path()

    data = _read_yaml(target)
    return _build_registry(data, source_path=target.resolve())
