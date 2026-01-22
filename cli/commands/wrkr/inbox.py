"""
qn wrkr inbox command.
"""

import os

import click

from cli.commands.main import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_worker_channels, get_channel_messages
from shared import WorkerNotFound


@click.command()
@click.option(
    "--unread-only",
    is_flag=True,
    help="Show only unread messages.",
)
@click.option(
    "--limit",
    default=20,
    help="Maximum messages to show per channel.",
)
@pass_context
def inbox_cmd(ctx: Context, unread_only: bool, limit: int):
    """View inbox messages.

    Lists messages for this worker from subscribed channels.
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

        # Get subscribed channels
        channels = get_worker_channels(db, worker_id)

        if not channels:
            click.echo("No subscribed channels.")
            click.echo("")
            click.echo("Tip: Subscribe to channels to receive messages.")
            return

        # Get messages from each channel
        total_messages = 0
        for channel in channels:
            messages = get_channel_messages(db, channel.id, limit=limit)
            if messages:
                click.echo(f"# {channel.name} ({channel.type})")
                click.echo("-" * 40)
                for msg in messages:
                    timestamp = msg.created_at
                    if hasattr(timestamp, 'strftime'):
                        timestamp = timestamp.strftime("%Y-%m-%d %H:%M")
                    click.echo(f"[{timestamp}] {msg.from_worker_id}: {msg.content}")
                    total_messages += 1
                click.echo("")

        if total_messages == 0:
            click.echo("No messages in subscribed channels.")

    finally:
        db.close()
