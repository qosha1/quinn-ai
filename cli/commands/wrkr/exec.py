"""qn wrkr exec — send a directive to a worker's inbox from the CLI."""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.queries import resolve_worker, get_or_create_direct_channel, create_message


@click.command("exec")
@click.argument("worker_name")
@click.argument("directive")
@click.option("--priority", default=1, show_default=True, help="Message priority (0-5).")
@pass_context
def exec_cmd(ctx: Context, worker_name: str, directive: str, priority: int) -> None:
    """Send a directive to a worker's inbox. They receive it as a DM and act on it.

    WORKER_NAME: Worker name or ID
    DIRECTIVE:   Message / instruction to send
    """
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        org = Org.load(db)
        if org.ceo is None:
            raise click.ClickException("No CEO found — cannot determine sender.")
        sender_id = org.ceo.id

        target = resolve_worker(db, worker_name)
        if target is None:
            raise click.ClickException(f"Worker '{worker_name}' not found.")

        channel = get_or_create_direct_channel(db, sender_id, target.id)
        create_message(
            db,
            channel_id=channel.id,
            from_worker_id=sender_id,
            content=directive,
            priority=priority,
            time_sensitivity="immediate",
        )
        click.echo(f"Directive sent to {target.name}.")
    finally:
        db.close()
