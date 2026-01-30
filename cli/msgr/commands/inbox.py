"""msgr inbox command - View pending notifications."""

import click
from datetime import datetime

from msgr.context import pass_context, MsgrContext
from core.notifications import get_pending_notifications
from core.queries.channel import get_channel
from core.queries.worker import get_worker


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
@pass_context
def inbox(ctx: MsgrContext, unread: bool, channel: str, limit: int):
    """View pending notifications.

    Shows notifications from all channels by default.
    Use --channel to filter to a specific channel.
    Use --unread to show only unread notifications.

    \b
    Examples:
      msgr inbox                  # All notifications
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
        from msgr.utils import resolve_channel
        try:
            channel_id = resolve_channel(db, channel, worker_id)
            notifications = [n for n in notifications if n["channel_id"] == channel_id]
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            raise click.Abort()

    # Filter by unread if specified
    if unread:
        notifications = [n for n in notifications if n["status"] == "pending"]

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
        # Get channel info
        chan = get_channel(db, notif["channel_id"])
        channel_name = f"#{chan.name}" if chan else notif["channel_id"]

        # Get sender info
        sender = get_worker(db, notif["from_worker_id"])
        sender_name = sender.name if sender else notif["from_worker_id"]

        # Format status
        status_icon = "🔵" if notif["status"] == "pending" else "✓"

        # Format time
        created_at = notif["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        time_str = created_at.strftime("%H:%M")

        # Format priority
        priority = notif.get("priority", 2)
        priority_icon = "🔴" if priority == 0 else "🟡" if priority == 1 else ""

        # Display notification
        click.echo(f"{status_icon} {priority_icon} {channel_name} • {sender_name} • {time_str}")
        click.echo(f"  {notif['message_id']}: {notif['content'][:100]}")
        if len(notif['content']) > 100:
            click.echo("  ...")
        click.echo()
