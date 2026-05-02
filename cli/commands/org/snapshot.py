"""qn org snapshot — capture full org state to JSON."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


@click.command("snapshot")
@click.option("--out", "out_path", default=None, help="Output file path (default: stdout).")
@pass_context
def snapshot_cmd(ctx: Context, out_path: Optional[str]) -> None:
    """Capture full org state to JSON for auditing, debugging, or backup."""
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        snapshot = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "org_path": str(org_path),
            "org": {},
            "workers": [],
            "sessions": [],
            "okrs": [],
            "budget": {},
            "channels": [],
        }

        # Org state
        org_row = db.fetchone("SELECT * FROM org_state LIMIT 1")
        if org_row:
            snapshot["org"] = dict(org_row)

        # Workers
        workers = db.fetchall(
            """
            SELECT w.*, ws.runtime_status, ws.current_task_id
            FROM workers w
            LEFT JOIN worker_state ws ON ws.worker_id = w.id
            ORDER BY w.created_at
            """
        )
        snapshot["workers"] = [dict(r) for r in (workers or [])]

        # Sessions
        sessions = db.fetchall("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 100")
        snapshot["sessions"] = [dict(r) for r in (sessions or [])]

        # OKRs
        okrs = db.fetchall("SELECT * FROM okrs ORDER BY created_at")
        snapshot["okrs"] = [dict(r) for r in (okrs or [])]

        # Budget pools
        pools = db.fetchall("SELECT * FROM budget_pools")
        allocs = db.fetchall("SELECT * FROM budget_allocations")
        snapshot["budget"] = {
            "pools": [dict(r) for r in (pools or [])],
            "allocations": [dict(r) for r in (allocs or [])],
        }

        # Channels (names only, not messages)
        channels = db.fetchall("SELECT id, name, type, created_at FROM channels")
        snapshot["channels"] = [dict(r) for r in (channels or [])]

        text = json.dumps(snapshot, default=_serialize, indent=2)

        if out_path:
            Path(out_path).write_text(text)
            click.echo(f"Snapshot saved to {out_path}")
        else:
            click.echo(text)
    finally:
        db.close()
