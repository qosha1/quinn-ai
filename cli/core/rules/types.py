"""Data model for the board rules engine.

Severity vocabulary (per c5hb §1, user-named):
    SUGGESTED  — stderr nudge, proceeds silently.
    ENCOURAGED — blocks unless --justify <bead-id> references a worker-owned non-empty bead.
    REQUIRED   — blocks unless --override <bead-id> references an approved bead whose
                 approver_id == worker.manager_id (direct-line manager, NOT board role).
    ABSOLUTE   — blocks unconditionally; no flag bypasses.

Decision-kind vocabulary (per t2zb §B / zm8a §2):
    ALLOW              — no rule matched, or rule matched but bypass conditions met.
    BLOCK              — ABSOLUTE match, or ENCOURAGED/REQUIRED with invalid bypass.
    ALLOW_WITH_NUDGE   — SUGGESTED match; action proceeds with stderr message.
    REQUIRES_JUSTIFY   — ENCOURAGED match; action blocked pending --justify.
    REQUIRES_OVERRIDE  — REQUIRED match; action blocked pending --override.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    SUGGESTED = "SUGGESTED"
    ENCOURAGED = "ENCOURAGED"
    REQUIRED = "REQUIRED"
    ABSOLUTE = "ABSOLUTE"


class DecisionKind(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    ALLOW_WITH_NUDGE = "allow_with_nudge"
    REQUIRES_JUSTIFY = "requires_justify"
    REQUIRES_OVERRIDE = "requires_override"


@dataclass(frozen=True)
class Pattern:
    kind: str
    target: str
    expr: str


@dataclass(frozen=True)
class Scope:
    env: Optional[str] = None
    worker_role: Optional[str] = None
    worker_role_min_level: Optional[int] = None
    target_path_prefix: Optional[str] = None


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    actions: tuple[str, ...]
    description: str
    pattern: Optional[Pattern] = None
    scope: Optional[Scope] = None
    artifact_required: bool = False
    notes: str = ""


@dataclass(frozen=True)
class RuleSet:
    version: int
    rules: tuple[Rule, ...]
    source_path: str


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    rule: Optional[Rule]
    message: str
    remediation: str = ""
