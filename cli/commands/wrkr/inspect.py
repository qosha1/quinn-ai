"""qn wrkr inspect — JSON dump of full worker state."""

import json
from datetime import datetime

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.queries import resolve_worker, get_worker_allocated_budget, get_worker_tools
from cli.core.storage import StorageManager


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


@click.command("inspect")
@click.argument("worker_name")
@pass_context
def inspect_cmd(ctx: Context, worker_name: str) -> None:
    """Output full worker state as JSON. Good for debugging and piping into jq.

    WORKER_NAME: Worker name or ID
    """
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        target = resolve_worker(db, worker_name)
        if target is None:
            raise click.ClickException(f"Worker '{worker_name}' not found.")

        wid = target.id

        # Session state
        session = db.fetchone(
            "SELECT * FROM sessions WHERE worker_id = ? ORDER BY started_at DESC LIMIT 1",
            (wid,),
        )
        runtime = db.fetchone("SELECT * FROM worker_state WHERE worker_id = ?", (wid,))

        # Budget
        try:
            allocated = get_worker_allocated_budget(db, wid)
        except Exception:
            allocated = None

        # Tools
        tools = get_worker_tools(db, wid)

        # Storage path
        try:
            storage = StorageManager(org_path, db=db)
            storage_path = str(storage.get_worker_path(wid))
        except Exception:
            storage_path = None

        # Active beads (best-effort via DB query on beads if table exists)
        active_beads: list = []
        try:
            bead_rows = db.fetchall(
                "SELECT id, title, status, priority FROM issues WHERE assignee = ? AND status NOT IN ('closed','done') LIMIT 10",
                (wid,),
            )
            active_beads = [dict(r) for r in (bead_rows or [])]
        except Exception:
            pass

        out = {
            "id": wid,
            "name": target.name,
            "role": target.role,
            "status": target.status,
            "manager_id": target.manager_id,
            "team_id": target.team_id,
            "cost": target.cost,
            "preferred_provider": getattr(target, "preferred_provider", None),
            "session": dict(session) if session else None,
            "runtime": dict(runtime) if runtime else None,
            "budget": {"allocated": allocated},
            "tools": tools,
            "storage": {"path": storage_path},
            "active_beads": active_beads,
        }

        click.echo(json.dumps(out, default=_serialize, indent=2))
    finally:
        db.close()
