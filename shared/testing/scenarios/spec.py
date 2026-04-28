"""ScenarioSpec — immutable scenario data, YAML-loaded with validation."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Imported lazily inside from_yaml() to avoid circular import on module load.


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    name: str
    setup: dict[str, Any]
    ops: list[dict[str, Any]]
    assertions: list[dict[str, Any]]
    # Test-only escape hatch so unit tests can construct specs with op/assertion
    # kinds that aren't registered yet (or marker ops). Production YAML-loaded
    # specs always go through validation.
    _allow_unknown_kinds: bool = field(default=False)

    @classmethod
    def from_yaml(cls, path: Path) -> "ScenarioSpec":
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"{path}: top-level YAML must be a mapping")

        for required in ("name", "setup", "ops", "assertions"):
            if required not in data:
                raise ValueError(f"{path}: missing required field {required!r}")

        # Validate op kinds and assertion kinds against registries.
        from .ops import OPS
        from .predicates import PREDICATES

        for i, op in enumerate(data.get("ops", []) or []):
            if not isinstance(op, dict) or "op" not in op:
                raise ValueError(f"{path}: ops[{i}] must be a mapping with an 'op' key")
            if op["op"] not in OPS:
                raise ValueError(
                    f"{path}: ops[{i}] unknown op kind {op['op']!r} "
                    f"(known: {sorted(OPS.keys())})"
                )

        for i, a in enumerate(data.get("assertions", []) or []):
            if not isinstance(a, dict) or "kind" not in a:
                raise ValueError(
                    f"{path}: assertions[{i}] must be a mapping with a 'kind' key"
                )
            if a["kind"] not in PREDICATES:
                raise ValueError(
                    f"{path}: assertions[{i}] unknown assertion kind "
                    f"{a['kind']!r} (known: {sorted(PREDICATES.keys())})"
                )

        return cls(
            name=data["name"],
            setup=data.get("setup") or {},
            ops=list(data.get("ops") or []),
            assertions=list(data.get("assertions") or []),
        )
