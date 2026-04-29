"""msgr inbox command - View pending notifications."""

import click
from datetime import datetime

from cli.msgr.context import pass_context, MsgrContext
from cli.core.notifications import get_pending_notifications
from cli.core.queries.channel import get_channel
from cli.core.queries.messages import get_message
from cli.core.queries.worker import get_worker


@click.command()
@click.option(
    "--unread",
    is_flag=True,
    default=False,
    help="Show only unread notifications (default: all pending)",
)
@click.option(
    "--channel",
    help="Filter by channel (#general, @worker-id, or chan-id)",
)
@click.option(
    "--limit",
    type=int,
    default=50,
    help="Maximum notifications to show (default: 50)",
)
@click.option(
    "--full", "--content", "full",
    is_flag=True,
    default=False,
    help="Show full message content (default: truncated to 200 chars).",
)
@pass_context
def inbox(ctx: MsgrContext, unread: bool, channel: str, limit: int, full: bool):
    """View pending notifications.

    Shows notifications from all channels by default.
    Use --channel to filter to a specific channel.
    Use --unread to show only unread notifications.
    Use --full (or --content) to print untruncated message bodies.

    \b
    Examples:
      msgr inbox                  # All notifications, 200-char preview
      msgr inbox --full           # Full content
      msgr inbox --unread         # Only unread
      msgr inbox --channel=#eng   # Engineering channel only
      msgr inbox --limit=10       # Last 10 notifications
    """
    db = ctx.db
    worker_id = ctx.worker_id

    # Get pending notifications
    notifications = get_pending_notifications(db, worker_id, limit=limit)

    # Filter by channel if specified
    if channel:
        from cli.msgr.utils import resolve_channel
        try:
            channel_id = resolve_channel(db, channel, worker_id)
            notifications = [n for n in notifications if n.channel_id == channel_id]
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            raise click.Abort()

    # Filter by unread if specified
    if unread:
        notifications = [n for n in notifications if n.status == "pending"]

    # Display notifications
    if not notifications:
        if unread:
            click.echo("No unread notifications")
        elif channel:
            click.echo(f"No notifications in {channel}")
        else:
            click.echo("No pending notifications")
        return

    click.echo(f"📬 {len(notifications)} notification(s):\n")

    for notif in notifications:
        # NotificationBead points to a message; load it for sender + content.
        msg = get_message(db, notif.message_id)
        content = msg.content if msg else "(message deleted)"
        from_worker_id = msg.from_worker_id if msg else None

        # Get channel info
        chan = get_channel(db, notif.channel_id)
        channel_name = f"#{chan.name}" if chan else notif.channel_id

        # Get sender info
        sender = get_worker(db, from_worker_id) if from_worker_id else None
        sender_name = sender.name if sender else (from_worker_id or "unknown")

        # Format status
        status_icon = "🔵" if notif.status == "pending" else "✓"

        # Format time
        created_at = notif.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        time_str = created_at.strftime("%H:%M") if created_at else "??:??"

        # Format priority
        priority = notif.priority if notif.priority is not None else 2
        priority_icon = "🔴" if priority == 0 else "🟡" if priority == 1 else ""

        # Display notification
        click.echo(f"{status_icon} {priority_icon} {channel_name} • {sender_name} • {time_str}")
        if full:
            click.echo(f"  {notif.message_id}:")
            for line in content.splitlines() or [content]:
                click.echo(f"    {line}")
        else:
            click.echo(f"  {notif.message_id}: {content[:200]}")
            if len(content) > 200:
                click.echo("  ...  (use --full to see all)")
        click.echo()
