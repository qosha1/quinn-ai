"""msgr send command - Send messages to channels."""

import click

from cli.msgr.context import pass_context, MsgrContext
from cli.msgr.utils import resolve_channel, ChannelResolutionError
from cli.core.queries.channel import create_message_with_notifications
from cli.core.rules import requires_rule_check


@click.command()
@click.argument("channel")
@click.argument("message")
@click.option(
    "--priority",
    type=click.IntRange(0, 4),
    default=2,
    help="Message priority (0=critical, 1=high, 2=normal, 3=low, 4=backlog)",
)
@click.option(
    "--time-sensitivity",
    type=click.Choice(["immediate", "hours", "days", "weeks", "whenever"]),
    default="whenever",
    help="When message needs attention",
)
@requires_rule_check("msgr.send")
@pass_context
def send(
    ctx: MsgrContext,
    channel: str,
    message: str,
    priority: int,
    time_sensitivity: str,
):
    """Send a message to a channel.

    CHANNEL can be:
    - #channel-name (e.g., #general)
    - @worker-id (DM to worker)
    - channel-id (raw ID)

    MESSAGE is the message text to send.

    \b
    Examples:
      msgr send #general 'Team meeting at 3pm'
      msgr send @alice 'Can you review PR #42?'
      msgr send #eng 'Bug fixed in production' --priority=1
    """
    db = ctx.db
    worker_id = ctx.worker_id

    # Resolve channel reference to ID
    try:
        channel_id = resolve_channel(db, channel, worker_id)
    except ChannelResolutionError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()

    # Send message with notifications
    try:
        msg = create_message_with_notifications(
            db=db,
            channel_id=channel_id,
            from_worker_id=worker_id,
            content=message,
            priority=priority,
            time_sensitivity=time_sensitivity,
        )

        click.echo(f"✓ Message sent to {channel}")
        click.echo(f"  ID: {msg.id}")

    except Exception as e:
        click.echo(f"Error sending message: {e}", err=True)
        raise click.Abort()
