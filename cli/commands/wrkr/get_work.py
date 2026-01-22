"""
qn wrkr get-work command.
"""

import os
import json

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.bd_wrapper import run_bd
from cli.core.permissions import (
    PermissionLevel,
    can_worker_access_bead,
)
from shared import WorkerNotFound


@click.command()
@click.option(
    "--limit",
    default=10,
    help="Maximum work items to show.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON.",
)
@pass_context
def get_work_cmd(ctx: Context, limit: int, as_json: bool):
    """Get assigned work items.

    Returns beads assigned to this worker, sorted by priority.
    Requires beads-org integration (qn-bd wrapper).
    """
    worker_id = os.environ.get("QUINN_WORKER_ID")
    if not worker_id:
        raise click.ClickException(
            "QUINN_WORKER_ID environment variable not set"
        )

    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        # Verify worker exists
        try:
            worker = Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(f"Worker not found: {worker_id}")

        # Check if worker can accept work
        if not worker.can_work:
            if as_json:
                click.echo(json.dumps({
                    "error": "worker_not_ready",
                    "lifecycle": worker.lifecycle_status,
                    "runtime": worker.runtime_status,
                }))
            else:
                click.echo(f"Worker cannot accept work.")
                click.echo(f"  Lifecycle: {worker.lifecycle_status}")
                click.echo(f"  Runtime: {worker.runtime_status or '(no session)'}")
                click.echo("")
                click.echo("Worker must be active with running/idle session to accept work.")
            return

        # Query beads for assigned work items
        try:
            result = run_bd(
                [
                    "list",
                    f"--assignee={worker_id}",
                    "--status=open",
                    "--status=in_progress",
                    "--json",
                ],
                org_path=org_path,
                worker_id=worker_id,
                capture_output=True,
            )

            if result.returncode != 0:
                # bd command failed - might not be initialized
                if as_json:
                    click.echo(json.dumps({
                        "error": "beads_error",
                        "message": result.stderr.strip() if result.stderr else "Beads query failed",
                    }))
                else:
                    click.echo("No work items found.")
                    if result.stderr:
                        click.echo(f"Note: {result.stderr.strip()}")
                return

            # Parse beads output
            if not result.stdout or result.stdout.strip() == "[]":
                if as_json:
                    click.echo(json.dumps({"items": [], "count": 0}))
                else:
                    click.echo("No work items assigned.")
                return

            try:
                items = json.loads(result.stdout)
            except json.JSONDecodeError:
                if as_json:
                    click.echo(json.dumps({
                        "error": "parse_error",
                        "raw": result.stdout[:200],
                    }))
                else:
                    click.echo("No work items assigned.")
                return

            # Filter by permission and sort by priority (P0 first)
            if isinstance(items, list):
                # Filter to only beads the worker has READ permission on
                permitted_items = []
                for item in items:
                    bead_id = item.get("id")
                    if bead_id and can_worker_access_bead(db, worker_id, bead_id, PermissionLevel.READ):
                        permitted_items.append(item)
                items = permitted_items
                items.sort(key=lambda x: x.get("priority", 4))
                items = items[:limit]
            else:
                items = []

            if as_json:
                click.echo(json.dumps({"items": items, "count": len(items)}))
            else:
                if not items:
                    click.echo("No work items assigned.")
                    return

                click.echo(f"Work items assigned ({len(items)}):")
                click.echo("-" * 40)
                for item in items:
                    priority = item.get("priority", "?")
                    status = item.get("status", "unknown")
                    title = item.get("title", "(no title)")
                    item_id = item.get("id", "?")
                    item_type = item.get("type", "task")

                    # Priority display
                    p_display = f"P{priority}" if isinstance(priority, int) else priority

                    click.echo(f"[{p_display}] [{status}] {item_id}: {title}")
                    click.echo(f"    Type: {item_type}")

                    # Show description snippet if available
                    desc = item.get("description", "")
                    if desc:
                        desc_line = desc.split("\n")[0][:60]
                        if len(desc) > 60:
                            desc_line += "..."
                        click.echo(f"    {desc_line}")
                    click.echo("")

                click.echo(f"Use 'qn-bd show <id>' to view details.")
                click.echo(f"Use 'qn-bd update <id> --status=in_progress' to claim work.")

        except FileNotFoundError:
            if as_json:
                click.echo(json.dumps({
                    "error": "beads_not_found",
                    "message": "Beads binary not found. Run 'scripts/build-beads.sh' to bundle it.",
                }))
            else:
                click.echo("No work items found.")
                click.echo("")
                click.echo("Note: beads binary not found. Run 'scripts/build-beads.sh' to bundle it.")

        except ValueError as e:
            if as_json:
                click.echo(json.dumps({
                    "error": "config_error",
                    "message": str(e),
                }))
            else:
                click.echo(f"Configuration error: {e}")

    finally:
        db.close()
