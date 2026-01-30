"""msgr read command - Mark messages as read."""

import click

from msgr.context import pass_context, MsgrContext
from core.notifications import mark_notification_read


@click.command()
@click.argument("message_id")
@pass_context
def read(ctx: MsgrContext, message_id: str):
    """Mark a message as read.

    MESSAGE_ID is the message identifier from inbox output.

    This marks the notification as read, removing it from
    your pending notifications list.

    \b
    Examples:
      msgr read msg-abc123    # Mark message as read
    """
    db = ctx.db
    worker_id = ctx.worker_id

    # Find notification for this message and worker
    row = db.fetchone(
        """SELECT id FROM notification_beads
           WHERE message_id = ? AND worker_id = ? AND status = 'pending'""",
        (message_id, worker_id)
    )

    if not row:
        click.echo(f"No pending notification found for message {message_id}", err=True)
        click.echo("Message may already be read or you don't have a notification for it.")
        raise click.Abort()

    notification_id = row["id"]

    # Mark as read
    try:
        mark_notification_read(db, notification_id)
        click.echo(f"✓ Marked {message_id} as read")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()
