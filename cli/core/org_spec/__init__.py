"""Declarative org.yml spec: parse, resolve $refs, validate (quinn-ai-a3pg.4.2).

Public surface:
    load_org_spec(path) -> OrgSpec
    OrgSpec (+ HostSpec, ToolchainSpec, TeamSpec, ManagerSpec, MemberSpec,
             DelegationSpec, OkrSpec, KeyResultSpec)
    OrgSpecError (raised on invalid/unresolvable specs)
"""

from shared.exceptions import OrgSpecError

from .apply import ApplyResult, apply_org_spec
from .loader import load_org_spec
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

__all__ = [
    "load_org_spec",
    "apply_org_spec",
    "ApplyResult",
    "OrgSpec",
    "OrgSpecError",
    "HostSpec",
    "ToolchainSpec",
    "TeamSpec",
    "ManagerSpec",
    "MemberSpec",
    "DelegationSpec",
    "OkrSpec",
    "KeyResultSpec",
]
