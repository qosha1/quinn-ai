"""qn org gc — garbage collect dead sessions and stale state."""

import subprocess

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path


@click.command("gc")
@click.option("--dry-run", is_flag=True, help="Preview without making changes.")
@pass_context
def gc_cmd(ctx: Context, dry_run: bool) -> None:
    """Clean up terminated workers, orphaned tmux sessions, and stale session records."""
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    total = 0
    try:
        # 1. Stale session records for terminated workers
        stale_sessions = db.fetchall(
            """
            SELECT s.id, s.worker_id, s.tmux_session_name
            FROM sessions s
            JOIN workers w ON s.worker_id = w.id
            WHERE w.status = 'terminated'
              AND s.state NOT IN ('stopped', 'cleaned')
            """
        ) or []
        if stale_sessions:
            if dry_run:
                click.echo(f"[dry-run] Would clean {len(stale_sessions)} stale session record(s) for terminated workers")
            else:
                for row in stale_sessions:
                    db.execute(
                        "UPDATE sessions SET state = 'stopped' WHERE id = ?", (row["id"],)
                    )
                db.connection.commit()
                click.echo(f"Cleaned {len(stale_sessions)} stale session record(s) for terminated workers.")
            total += len(stale_sessions)

        # 2. Orphaned tmux sessions (in DB but not running in tmux)
        active_sessions = db.fetchall(
            "SELECT tmux_session_name FROM sessions WHERE state IN ('running','idle','starting') AND tmux_session_name IS NOT NULL"
        ) or []
        orphaned = []
        for row in active_sessions:
            tmux_name = row["tmux_session_name"]
            result = subprocess.run(
                ["tmux", "has-session", "-t", tmux_name],
                capture_output=True,
            )
            if result.returncode != 0:
                orphaned.append(tmux_name)

        if orphaned:
            if dry_run:
                click.echo(f"[dry-run] Would mark {len(orphaned)} orphaned tmux session(s) as stopped: {', '.join(orphaned)}")
            else:
                for name in orphaned:
                    db.execute(
                        "UPDATE sessions SET state = 'stopped' WHERE tmux_session_name = ?", (name,)
                    )
                db.connection.commit()
                click.echo(f"Marked {len(orphaned)} orphaned tmux session(s) as stopped.")
            total += len(orphaned)

        # 3. Stale worker_state rows for terminated workers
        stale_states = db.fetchall(
            """
            SELECT ws.worker_id FROM worker_state ws
            JOIN workers w ON ws.worker_id = w.id
            WHERE w.status = 'terminated'
              AND ws.runtime_status NOT IN ('stopped')
            """
        ) or []
        if stale_states:
            if dry_run:
                click.echo(f"[dry-run] Would reset {len(stale_states)} stale worker_state row(s)")
            else:
                for row in stale_states:
                    db.execute(
                        "UPDATE worker_state SET runtime_status = 'stopped' WHERE worker_id = ?",
                        (row["worker_id"],),
                    )
                db.connection.commit()
                click.echo(f"Reset {len(stale_states)} stale worker_state row(s).")
            total += len(stale_states)

        if total == 0:
            click.echo("Nothing to clean up.")
        elif not dry_run:
            click.echo(f"gc complete: {total} item(s) cleaned.")
        else:
            click.echo(f"[dry-run] Total: {total} item(s) would be cleaned.")
    finally:
        db.close()
