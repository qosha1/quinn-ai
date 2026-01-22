"""
qn wrkr get-work command.
"""

import os

import click

from commands.main import pass_context, Context
from core.db import open_database, get_org_db_path
from core.worker import Worker
from shared import WorkerNotFound


@click.command()
@pass_context
def get_work_cmd(ctx: Context):
    """Get next work item.

    Returns the next bead assigned to this worker, sorted by priority.
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
            click.echo(f"Worker cannot accept work.")
            click.echo(f"  Lifecycle: {worker.lifecycle_status}")
            click.echo(f"  Runtime: {worker.runtime_status or '(no session)'}")
            click.echo("")
            click.echo("Worker must be active with running/idle session to accept work.")
            return

        # TODO: Query beads-org for assigned work items
        # This requires the qn-bd wrapper (Sprint 2.3) to be implemented
        # For now, indicate no work available
        click.echo("No work items assigned.")
        click.echo("")
        click.echo("Note: beads-org integration pending (Sprint 2.3)")

    finally:
        db.close()
