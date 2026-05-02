"""qn org ps — process list view for running workers."""

import json
from datetime import datetime, timezone
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.queries import get_workers_by_status, get_all_workers_for_topology


def _fmt_uptime(started_at: Optional[str]) -> str:
    if not started_at:
        return "-"
    try:
        ts = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h{m:02d}m"
        return f"{m}m{s:02d}s"
    except Exception:
        return "-"


@click.command("ps")
@click.option("--wide", is_flag=True, help="Show full worker IDs.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@pass_context
def ps_cmd(ctx: Context, wide: bool, as_json: bool) -> None:
    """List workers like unix ps — compact process view."""
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        rows = db.fetchall(
            """
            SELECT w.id, w.name, w.role, w.status,
                   ws.runtime_status, ws.current_task_id, ws.updated_at
            FROM workers w
            LEFT JOIN worker_state ws ON ws.worker_id = w.id
            WHERE w.status != 'terminated'
            ORDER BY w.manager_id NULLS FIRST, w.name
            """
        )
        if as_json:
            out = []
            for r in rows:
                wid = r["id"]
                out.append({
                    "id": wid if wide else wid[:12],
                    "name": r["name"],
                    "role": r["role"],
                    "status": r["status"],
                    "runtime": r["runtime_status"] or "stopped",
                    "task": r["current_task_id"] or "-",
                    "updated": str(r["updated_at"] or "-")[:16],
                })
            click.echo(json.dumps(out, indent=2))
            return

        id_width = 36 if wide else 12
        fmt = f"{{:<{id_width}}}  {{:<16}}  {{:<24}}  {{:<12}}  {{:<10}}  {{}}"
        click.echo(fmt.format("ID", "NAME", "ROLE", "LIFECYCLE", "RUNTIME", "TASK"))
        click.echo("─" * (id_width + 80))
        for r in rows:
            wid = r["id"] if wide else r["id"][:12]
            runtime = r["runtime_status"] or "stopped"
            task = (r["current_task_id"] or "-")[:30]
            click.echo(fmt.format(
                wid,
                (r["name"] or "")[:16],
                (r["role"] or "")[:24],
                (r["status"] or "")[:12],
                runtime[:10],
                task,
            ))
    finally:
        db.close()
