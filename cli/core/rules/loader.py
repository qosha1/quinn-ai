"""Loader for board-rules YAML files.

Per quinn-ai-t2zb §G + quinn-ai-zm8a:
- `load_rules(org_path)` reads `<org_path>/config/rules.yaml`.
- Falls back to the bundled default catalog when the file is absent.
- Empty `rules: []` (with `version: 1`) is valid and produces a zero-rule RuleSet.
- Fails closed (raises RuleSetLoadError) on YAML parse, schema validation, or
  regex compile errors. The error message cites the source path + parse location.
- Rules are sorted by `id` for deterministic engine ordering.
- Pattern blocks are compiled at load time; compiled regex lives in a side-cache
  keyed by Rule.id so the frozen `Pattern` dataclass stays immutable.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from cli.core.rules.types import (
    Pattern,
    Rule,
    RuleSet,
    Scope,
    Severity,
)
from shared.exceptions import RuleSetLoadError

# Side-cache for compiled regex patterns; populated at load time, read by engine.
# Keyed by Rule.id.
_COMPILED_PATTERNS: dict[str, re.Pattern[str]] = {}


def _default_catalog_path() -> Path:
    """Absolute path to the bundled default rules catalog."""
    return (Path(__file__).resolve().parents[2] / "config" / "default_rules.yaml")


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read and parse YAML. Raises RuleSetLoadError on parse failure."""
    try:
        text = path.read_text()
    except OSError as exc:
        raise RuleSetLoadError(path, f"could not read file: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        # PyYAML's MarkedYAMLError carries .problem_mark with line/column info;
        # str(exc) usually contains "line N, column M".
        raise RuleSetLoadError(path, f"YAML parse error: {exc}") from exc

    if data is None:
        # Empty file
        raise RuleSetLoadError(path, "file is empty; expected at least `version: 1`")
    if not isinstance(data, dict):
        raise RuleSetLoadError(
            path, f"top-level must be a mapping, got {type(data).__name__}"
        )
    return data


def _build_pattern(raw: Any, *, rule_id: str, source_path: Path) -> Pattern:
    if not isinstance(raw, dict):
        raise RuleSetLoadError(
            source_path,
            f"rule '{rule_id}': pattern must be a mapping, got {type(raw).__name__}",
        )
    for required_key in ("kind", "target", "expr"):
        if required_key not in raw:
            raise RuleSetLoadError(
                source_path,
                f"rule '{rule_id}': pattern missing required key '{required_key}'",
            )
    kind = raw["kind"]
    target = raw["target"]
    expr = raw["expr"]

    # Compile regex patterns at load time; fail closed on bad regex.
    if kind == "regex":
        try:
            _COMPILED_PATTERNS[rule_id] = re.compile(expr)
        except re.error as exc:
            raise RuleSetLoadError(
                source_path,
                f"rule '{rule_id}': invalid regex in pattern.expr: {exc}",
            ) from exc

    return Pattern(kind=kind, target=target, expr=expr)


def _build_scope(raw: Any, *, rule_id: str, source_path: Path) -> Scope:
    if not isinstance(raw, dict):
        raise RuleSetLoadError(
            source_path,
            f"rule '{rule_id}': scope must be a mapping, got {type(raw).__name__}",
        )
    return Scope(
        env=raw.get("env"),
        worker_role=raw.get("worker_role"),
        worker_role_min_level=raw.get("worker_role_min_level"),
        target_path_prefix=raw.get("target_path_prefix"),
    )


def _build_rule(raw: Any, *, source_path: Path) -> Rule:
    if not isinstance(raw, dict):
        raise RuleSetLoadError(
            source_path, f"each rule must be a mapping, got {type(raw).__name__}"
        )

    for required_key in ("id", "severity", "actions", "description"):
        if required_key not in raw:
            raise RuleSetLoadError(
                source_path,
                f"rule missing required key '{required_key}': {raw!r}",
            )

    rule_id = raw["id"]
    if not isinstance(rule_id, str) or not rule_id:
        raise RuleSetLoadError(source_path, f"rule.id must be a non-empty string: {rule_id!r}")

    severity_raw = raw["severity"]
    try:
        severity = Severity(severity_raw)
    except ValueError as exc:
        valid = ", ".join(s.value for s in Severity)
        raise RuleSetLoadError(
            source_path,
            f"rule '{rule_id}': unknown severity {severity_raw!r}; valid values are {valid}",
        ) from exc

    actions_raw = raw["actions"]
    if not isinstance(actions_raw, list) or not actions_raw:
        raise RuleSetLoadError(
            source_path,
            f"rule '{rule_id}': actions must be a non-empty list",
        )
    actions = tuple(str(a) for a in actions_raw)

    description = raw["description"]
    if not isinstance(description, str):
        raise RuleSetLoadError(
            source_path, f"rule '{rule_id}': description must be a string"
        )

    pattern = (
        _build_pattern(raw["pattern"], rule_id=rule_id, source_path=source_path)
        if "pattern" in raw
        else None
    )
    scope = (
        _build_scope(raw["scope"], rule_id=rule_id, source_path=source_path)
        if "scope" in raw
        else None
    )

    return Rule(
        id=rule_id,
        severity=severity,
        actions=actions,
        description=description,
        pattern=pattern,
        scope=scope,
        artifact_required=bool(raw.get("artifact_required", False)),
        notes=str(raw.get("notes", "")),
    )


def _build_ruleset(data: dict[str, Any], *, source_path: Path) -> RuleSet:
    version = data.get("version")
    if version != 1:
        raise RuleSetLoadError(
            source_path,
            f"unsupported version: {version!r} (expected 1)",
        )

    rules_raw = data.get("rules")
    if rules_raw is None:
        raise RuleSetLoadError(source_path, "missing 'rules' key (use `rules: []` for none)")
    if not isinstance(rules_raw, list):
        raise RuleSetLoadError(source_path, f"'rules' must be a list, got {type(rules_raw).__name__}")

    rules = tuple(_build_rule(r, source_path=source_path) for r in rules_raw)

    # Reject duplicate ids (per ip00 / vh1i acceptance).
    seen: set[str] = set()
    for rule in rules:
        if rule.id in seen:
            raise RuleSetLoadError(
                source_path, f"duplicate rule id: {rule.id!r}"
            )
        seen.add(rule.id)

    # Deterministic order by id.
    rules = tuple(sorted(rules, key=lambda r: r.id))

    return RuleSet(
        version=version,
        rules=rules,
        source_path=str(source_path),
    )


def load_rules(org_path: Path) -> RuleSet:
    """Read the org's rules.yaml. Fall back to bundled default catalog when absent.

    Args:
        org_path: Org root directory; loader reads `<org_path>/config/rules.yaml`.

    Returns:
        RuleSet with rules sorted deterministically by id.

    Raises:
        RuleSetLoadError: malformed YAML, schema-violating content, or invalid regex.
    """
    org_rules = org_path / "config" / "rules.yaml"
    if org_rules.exists():
        target = org_rules
    else:
        target = _default_catalog_path()

    data = _read_yaml(target)
    return _build_ruleset(data, source_path=target.resolve())


def get_compiled_pattern(rule_id: str) -> re.Pattern[str] | None:
    """Lookup helper for the engine: returns the pre-compiled regex for a rule, if any.

    The compile happened at `load_rules()` time so the engine never pays the cost
    on the hot path. Returns None for non-regex patterns or unknown rule ids.
    """
    return _COMPILED_PATTERNS.get(rule_id)
