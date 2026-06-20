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
    # Optional correctness-scoring config (samples / pass_threshold /
    # consistency_threshold). None => strict legacy gate (every assertion must
    # pass, single run). See shared.testing.canary.scoring.ScoringPolicy.
    scoring: dict[str, Any] | None = field(default=None)
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
            if "weight" in a:
                w = a["weight"]
                if not isinstance(w, (int, float)) or isinstance(w, bool) or w < 0:
                    raise ValueError(
                        f"{path}: assertions[{i}] weight must be a number >= 0, "
                        f"got {w!r}"
                    )
            if "critical" in a and not isinstance(a["critical"], bool):
                raise ValueError(
                    f"{path}: assertions[{i}] critical must be a bool, "
                    f"got {a['critical']!r}"
                )

        scoring = cls._validate_scoring(path, data.get("scoring"))

        return cls(
            name=data["name"],
            setup=data.get("setup") or {},
            ops=list(data.get("ops") or []),
            assertions=list(data.get("assertions") or []),
            scoring=scoring,
        )

    @staticmethod
    def _validate_scoring(path: Path, scoring: Any) -> dict[str, Any] | None:
        """Validate the optional `scoring` block; returns it or None if absent.

        Enforces known keys + value ranges up front so a malformed gate fails at
        load time rather than mid-canary. Range validation is delegated to
        ScoringPolicy so there is one source of truth.
        """
        if scoring is None:
            return None
        if not isinstance(scoring, dict):
            raise ValueError(
                f"{path}: scoring must be a mapping, got {type(scoring).__name__}"
            )
        allowed = {"samples", "pass_threshold", "consistency_threshold"}
        unknown = set(scoring) - allowed
        if unknown:
            raise ValueError(
                f"{path}: scoring has unknown key(s) {sorted(unknown)} "
                f"(allowed: {sorted(allowed)})"
            )
        # Construct the policy to reuse its range validation (raises ValueError).
        from shared.testing.canary.scoring import ScoringPolicy

        ScoringPolicy.from_spec(scoring)
        return dict(scoring)
