"""
qn wrkr send command.

Worker ID is passed explicitly through CLI context (via --worker-id option
on the wrkr group or QUINN_WORKER_ID envvar).
"""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_channel, create_message_with_notifications
from cli.core.permissions import (
    PermissionLevel,
    PermissionDenied,
    require_channel_permission,
)
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
        # Verify worker exists
        try:
            Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(
                f"Worker '{worker_id}' not found.\n"
                "Run 'qn org status' to see available workers."
            )

        # Verify channel exists
        channel = get_channel(db, to_channel)
        if not channel:
            raise click.ClickException(
                f"Channel '{to_channel}' not found.\n"
                "Verify the channel ID is correct."
            )

        # Check permission to send messages to this channel
        # Sending messages requires at least COMMENT level permission
        try:
            require_channel_permission(
                db=db,
                worker_id=worker_id,
                channel_id=to_channel,
                required_level=PermissionLevel.COMMENT,
                action="send_message",
            )
        except PermissionDenied as e:
            raise click.ClickException(
                f"Permission denied: Cannot send messages to channel '{channel.name}'.\n"
                "You need at least COMMENT permission on this channel."
            )

        # Validate priority
        if not 0 <= priority <= 4:
            raise click.ClickException(
                f"Invalid priority '{priority}'. Must be between 0 and 4.\n"
                "0=critical, 1=high, 2=medium (default), 3=low, 4=backlog"
            )

        # Create the message and notify subscribers
        msg = create_message_with_notifications(
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
