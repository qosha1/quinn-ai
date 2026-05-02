"""qn org audit — structured audit log of org actions."""

import json
from datetime import datetime, timedelta, timezone

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path


def _parse_last(last: str) -> datetime:
    """Parse '24h', '7d', '1h' etc into a cutoff datetime."""
    now = datetime.now(timezone.utc)
    s = last.lower().strip()
    if s.endswith("h"):
        return now - timedelta(hours=float(s[:-1]))
    if s.endswith("d"):
        return now - timedelta(days=float(s[:-1]))
    if s.endswith("m"):
        return now - timedelta(minutes=float(s[:-1]))
    return now - timedelta(hours=24)


@click.command("audit")
@click.option("--last", default="24h", show_default=True, help="Time window (e.g. 24h, 7d).")
@click.option("--worker", default=None, help="Filter by worker name or ID.")
@click.option("--type", "event_type", default=None, help="Filter by event type.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@pass_context
def audit_cmd(ctx: Context, last: str, worker: str, event_type: str, as_json: bool) -> None:
    """Show structured audit trail of org actions."""
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        cutoff = _parse_last(last)
        params: list = [cutoff.isoformat()]
        sql = "SELECT e.*, w.name as actor_name FROM events e LEFT JOIN workers w ON e.actor_id = w.id WHERE e.created_at >= ?"

        if worker:
            sql += " AND (w.name LIKE ? OR e.actor_id = ?)"
            params += [f"%{worker}%", worker]
        if event_type:
            sql += " AND e.event_type = ?"
            params.append(event_type)

        sql += " ORDER BY e.created_at DESC LIMIT 200"
        rows = db.fetchall(sql, params) or []

        if as_json:
            click.echo(json.dumps([dict(r) for r in rows], default=str, indent=2))
            return

        if not rows:
            click.echo(f"No events in the last {last}.")
            return

        fmt = "{:<19}  {:<20}  {:<28}  {}"
        click.echo(fmt.format("TIME", "ACTOR", "TYPE", "DETAILS"))
        click.echo("─" * 90)
        for r in rows:
            ts = str(r["created_at"] or "")[:19]
            actor = (r["actor_name"] or r["actor_id"] or "system")[:20]
            etype = (r["event_type"] or "")[:28]
            details = str(r.get("details") or r.get("payload") or "")[:60]
            click.echo(fmt.format(ts, actor, etype, details))
    finally:
        db.close()
