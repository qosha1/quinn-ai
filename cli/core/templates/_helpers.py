"""Programmatic helpers the TemplateOrchestrator delegates to.

Per quinn-ai-u0h2 §11 + cutg §1: the orchestrator does NOT shell out to
click commands. It calls these module-level function bindings, which tests
can monkey-patch via `monkeypatch.setattr(orchestrator._helpers, name, fake)`.

In v0 these are thin shims around `cli.core.queries.worker.create_worker`
plus DB ops for fire / OKR. Phase-4 of the BOARD-RULES wiring epic established
the same pattern at the click level; future cleanup may extract richer
hire/fire helpers that mirror the click-command business logic.
"""

from __future__ import annotations

from typing import Any, Optional

from cli.core.db import Database
from cli.core.queries.worker import create_worker as _create_worker_query


def hire_worker(
    db: Database,
    ctx: Any,
    *,
    name: str,
    role: str,
    manager_id: str,
    cost: int,
) -> Any:
    """Programmatic hire of a single worker.

    Returns the new Worker object. The orchestrator places the worker into
    the right team via `add_team_member` after this returns. team_id on the
    workers row is set to whatever the most-recently-created team is — the
    orchestrator's add_team_member call is the authoritative team membership.
    """
    row = db.fetchone("SELECT id FROM teams ORDER BY created_at DESC LIMIT 1")
    team_id = row["id"] if row else "team-default"
    return _create_worker_query(
        db,
        name=name,
        role=role,
        team_id=team_id,
        cost=cost,
        manager_id=manager_id,
    )


def fire_worker(
    db: Database,
    ctx: Any,
    *,
    worker_id: str,
    reason: str = "hire-team rollback",
    terminate_immediately: bool = True,
) -> None:
    """Programmatic fire — used by the orchestrator's rollback path.

    For rollback (the typical caller), DELETE the worker row rather than just
    marking terminated. The worker only existed for milliseconds inside the
    failed transaction; leaving a terminated row pollutes the org's history.

    Cleanup also removes any team_members rows referencing the worker.
    """
    if reason == "hire-team rollback":
        db.execute("DELETE FROM team_members WHERE worker_id = ?", (worker_id,))
        db.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
    else:
        db.execute(
            "UPDATE workers SET status = 'terminated', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (worker_id,),
        )
    db.connection.commit()


def create_okr(
    db: Database,
    ctx: Any,
    *,
    title: str,
    description: str,
    owner_id: str,
    key_results: tuple[dict, ...] = (),
    parent_okr_id: Optional[str] = None,
) -> str:
    """Programmatic OKR creation. Returns the new OKR id."""
    import json

    from cli.core.queries.common import generate_id

    okr_id = generate_id("okr")
    krs_json = json.dumps([dict(kr) for kr in key_results]) if key_results else None
    db.execute(
        """INSERT INTO okrs (id, title, description, owner_worker_id, parent_okr_id, status, key_results)
           VALUES (?, ?, ?, ?, ?, 'active', ?)""",
        (okr_id, title, description, owner_id, parent_okr_id, krs_json),
    )
    db.connection.commit()
    return okr_id


def close_okr(
    db: Database,
    ctx: Any,
    *,
    okr_id: str,
    status: str = "cancelled",
    reason: str = "hire-team rollback",
) -> None:
    """Programmatic OKR close — used by the orchestrator's rollback path."""
    db.execute(
        "UPDATE okrs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, okr_id),
    )
    db.connection.commit()
