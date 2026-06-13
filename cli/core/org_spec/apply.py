"""Apply a declarative org.yml: instantiate an org from an OrgSpec.

Pipeline (quinn-ai-a3pg.4.3):
  Stage 1 (.4.3.1)  init    — init_org(spec.to_org_init_config) creates org + CEO.
  Stage 2 (.4.3.2)  structure — create each team; hire its manager; for a
                    fully-declared team also hire the declared members; a
                    self_form team gets its manager seat only (ICs self-form
                    later via sensemaking — the hybrid-topology decision).
  Stage 3 (.4.3.3)  seed OKRs with their declared owners (delegation grants
                    are the remaining part of .4.3.3).

Structure is created with the low-level query helpers (create_team /
hire_worker / add_team_member), the same ones TemplateOrchestrator uses. This
is an operator action (like init creating the CEO), so it does not run the
runtime hiring-authority gate — that gate governs in-session worker hires, not
the declarative build. No sessions are spawned; `qn org start` does that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

from cli.core.constants import (
    ORG_SPEC_DEFAULT_WORKER_COST,
    ORG_SPEC_MEMBERSHIP_LEAD,
    ORG_SPEC_MEMBERSHIP_MEMBER,
    ORG_SPEC_OWNER_CEO,
    WORKER_HANDLE_SEP,
)
from cli.core.org_init import init_org
from shared.exceptions import OrgSpecError

from .types import OrgSpec, TeamSpec


@dataclass
class ApplyResult:
    """Outcome of applying an OrgSpec.

    Attributes:
        org_path: The org-metadata root (project/.quinnai in host mode).
        ceo_id: The created CEO worker id.
        team_ids: team name -> team id.
        worker_ids: handle -> worker id, where handle is "ceo" or "<team>/<Name>".
        okr_ids: created OKR ids in declaration order.
        warnings: non-fatal issues (e.g. unresolved OKR owners).
    """

    org_path: Path
    ceo_id: str
    team_ids: dict[str, str] = field(default_factory=dict)
    worker_ids: dict[str, str] = field(default_factory=dict)
    okr_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def apply_org_spec(spec: OrgSpec, target_path: Optional[Path] = None) -> ApplyResult:
    """Instantiate an org from a validated OrgSpec.

    Args:
        spec: The parsed/validated org spec (see load_org_spec).
        target_path: Required for greenfield specs (no host.project_root);
            the directory the new org is created in. Ignored in host mode.

    Returns:
        An ApplyResult describing what was created.

    Raises:
        OrgSpecError: If the init phase fails.
    """
    init_result = init_org(spec.to_org_init_config(target_path))
    if not init_result.success:
        raise OrgSpecError(f"org init failed: {init_result.error}")

    from cli.core.db import get_org_db_path, open_database

    org_path = init_result.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        result = ApplyResult(org_path=org_path, ceo_id=init_result.ceo_id)
        result.worker_ids[ORG_SPEC_OWNER_CEO] = init_result.ceo_id
        ctx = SimpleNamespace(db=db, org_path=org_path, worker_id=None)

        for team in spec.teams:
            _apply_team(db, ctx, team, init_result.ceo_id, result)

        _apply_okrs(db, ctx, spec, result)
        return result
    finally:
        db.close()


def _apply_team(
    db: Any,
    ctx: Any,
    team: TeamSpec,
    ceo_id: str,
    result: ApplyResult,
) -> None:
    """Create a team, hire its manager, and (unless self_form) its members."""
    from cli.core.queries.team import add_team_member, create_team
    from cli.core.templates._helpers import hire_worker

    team_row = create_team(
        db, name=team.name, parent_team_id=None, lead_id=None, auto_create_channel=False
    )
    team_id = _row_id(team_row)
    result.team_ids[team.name] = team_id

    manager_id = ceo_id
    if team.manager is not None:
        manager = hire_worker(
            db,
            ctx,
            name=team.manager.name,
            role=team.manager.role,
            manager_id=ceo_id,
            cost=team.manager.cost or ORG_SPEC_DEFAULT_WORKER_COST,
        )
        manager_id = _worker_id(manager)
        add_team_member(db, team_id, manager_id, ORG_SPEC_MEMBERSHIP_LEAD)
        db.execute("UPDATE teams SET lead_id = ? WHERE id = ?", (manager_id, team_id))
        db.connection.commit()
        result.worker_ids[_handle(team.name, team.manager.name)] = manager_id

    if team.self_form:
        return

    for index, member in enumerate(team.members):
        member_name = member.name or f"{member.role}-{team.name}-{index + 1}"
        worker = hire_worker(
            db,
            ctx,
            name=member_name,
            role=member.role,
            manager_id=manager_id,
            cost=member.cost or ORG_SPEC_DEFAULT_WORKER_COST,
        )
        worker_id = _worker_id(worker)
        add_team_member(db, team_id, worker_id, ORG_SPEC_MEMBERSHIP_MEMBER)
        result.worker_ids[_handle(team.name, member_name)] = worker_id


def _apply_okrs(db: Any, ctx: Any, spec: OrgSpec, result: ApplyResult) -> None:
    """Seed OKRs, resolving each declared owner handle to a worker id."""
    from cli.core.templates._helpers import create_okr

    for okr in spec.okrs:
        owner_id = _resolve_owner(okr.owner, result)
        if owner_id is None:
            owner_id = result.ceo_id
            if okr.owner:
                result.warnings.append(
                    f"OKR {okr.title!r}: owner {okr.owner!r} did not resolve; "
                    f"assigned to CEO"
                )
        key_results = tuple(
            {"metric": kr.metric, "target": kr.target, "unit": kr.unit, "current": 0}
            for kr in okr.key_results
        )
        okr_id = create_okr(
            db,
            ctx,
            title=okr.title,
            description=okr.title,
            owner_id=owner_id,
            key_results=key_results,
        )
        result.okr_ids.append(okr_id)


def _resolve_owner(owner: Optional[str], result: ApplyResult) -> Optional[str]:
    """Resolve an OKR owner handle ("ceo" or "<team>/<Name>") to a worker id."""
    if not owner:
        return None
    if owner == ORG_SPEC_OWNER_CEO:
        return result.ceo_id
    if owner in result.worker_ids:
        return result.worker_ids[owner]
    # Tolerate a bare "<team>/<Name>" whose name half matches a known handle.
    for handle, worker_id in result.worker_ids.items():
        if handle.endswith(f"{WORKER_HANDLE_SEP}{owner.split(WORKER_HANDLE_SEP)[-1]}"):
            return worker_id
    return None


def _handle(team_name: str, worker_name: str) -> str:
    return f"{team_name}{WORKER_HANDLE_SEP}{worker_name}"


def _row_id(row: Any) -> str:
    """Extract an id from a team row (object with .id or a mapping)."""
    if hasattr(row, "id"):
        return row.id
    return row["id"]


def _worker_id(worker: Any) -> str:
    """Extract an id from a hired worker (object with .id or a mapping)."""
    if hasattr(worker, "id"):
        return worker.id
    return worker["id"]
