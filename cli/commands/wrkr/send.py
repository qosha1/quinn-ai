"""
qn wrkr send command.
"""

import os

import click

from cli.commands.main import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_channel, create_message
from shared import WorkerNotFound


@click.command()
@click.option(
    "--to",
    "to_channel",
    required=True,
    help="Channel ID to send to.",
)
@click.option(
    "--priority",
    default=2,
    type=int,
    help="Message priority (0-4, lower is higher priority).",
)
@click.argument("message")
@pass_context
def send_cmd(ctx: Context, to_channel: str, priority: int, message: str):
    """Send a message.

    Sends a message to the specified channel.
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
            Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(f"Worker not found: {worker_id}")

        # Verify channel exists
        channel = get_channel(db, to_channel)
        if not channel:
            raise click.ClickException(f"Channel not found: {to_channel}")

        # Validate priority
        if not 0 <= priority <= 4:
            raise click.ClickException("Priority must be between 0 and 4")

        # Create the message
        msg = create_message(
            db=db,
            channel_id=to_channel,
            from_worker_id=worker_id,
            content=message,
            priority=priority,
        )

        click.echo(f"Message sent to {channel.name}")
        click.echo(f"ID: {msg.id}")

    finally:
        db.close()
