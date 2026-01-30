"""
qn wrkr status command.

Worker ID is passed explicitly through CLI context (via --worker-id option
on the wrkr group or QUINN_WORKER_ID envvar).
"""

import click

from commands.context import pass_context, Context
from core.db import open_database, get_org_db_path
from core.worker import Worker
from shared import WorkerNotFound


@click.command()
@pass_context
def status_cmd(ctx: Context):
    """Show worker status.

    Displays lifecycle status, runtime status, and current task.
    """
    worker_id = ctx.worker_id
    if not worker_id:
        raise click.ClickException(
            "Worker ID not specified.\n"
            "Use --worker-id option or set QUINN_WORKER_ID environment variable."
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
        try:
            worker = Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(
                f"Worker '{worker_id}' not found.\n"
                "Run 'qn org status' to see available workers."
            )

        click.echo(f"Worker: {worker.name}")
        click.echo(f"Role: {worker.role}")
        click.echo(f"ID: {worker_id}")
        click.echo("")

        # Lifecycle status
        click.echo(f"Lifecycle: {worker.lifecycle_status}")

        # Runtime status
        runtime = worker.runtime_status
        if runtime:
            click.echo(f"Runtime: {runtime}")
            if worker.current_task_id:
                click.echo(f"Current Task: {worker.current_task_id}")
        else:
            click.echo("Runtime: (no session)")

        # Capabilities
        click.echo("")
        click.echo(f"Can work: {'yes' if worker.can_work else 'no'}")
        click.echo(f"Session active: {'yes' if worker.is_session_active else 'no'}")

    finally:
        db.close()
