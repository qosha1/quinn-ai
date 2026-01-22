"""
qn wrkr inbox command.

Worker ID is passed explicitly through CLI context (via --worker-id option
on the wrkr group or QUINN_WORKER_ID envvar).
"""

from collections import defaultdict

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_message, get_channel
from cli.core.notifications import (
    get_worker_notifications,
    get_pending_notifications,
    count_pending_notifications,
    mark_notification_read,
)
from cli.core.permissions import (
    PermissionLevel,
    can_worker_access_channel,
)
from shared import WorkerNotFound


@click.command()
@click.option(
    "--pending-only",
    is_flag=True,
    default=True,
    help="Show only pending (unread) notifications. Default: True",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Show all notifications including read/actioned.",
)
@click.option(
    "--mark-read",
    is_flag=True,
    help="Mark displayed notifications as read.",
)
@click.option(
    "--limit",
    default=50,
    help="Maximum notifications to show.",
)
@pass_context
def inbox_cmd(ctx: Context, pending_only: bool, show_all: bool, mark_read: bool, limit: int):
    """View inbox notifications.

    Lists notification beads for this worker. Notifications are ephemeral
    work units created when messages are sent to channels you're subscribed to.

    By default, shows only pending (unread) notifications. Use --all to see
    all notifications including read/actioned ones.
    """
    worker_id = ctx.worker_id
    if not worker_id:
        raise click.ClickException(
            "Worker ID not specified. Use --worker-id or set QUINN_WORKER_ID."
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

        # Get notifications
        if show_all:
            notifications = get_worker_notifications(db, worker_id, limit=limit)
            status_filter = "all"
        else:
            notifications = get_pending_notifications(db, worker_id, limit=limit)
            status_filter = "pending"

        if not notifications:
            pending_count = count_pending_notifications(db, worker_id)
            if pending_count == 0:
                click.echo("No notifications.")
            else:
                click.echo(f"No {status_filter} notifications. ({pending_count} total pending)")
            return

        # Group by channel for display, filtering by permission
        by_channel: dict[str, list] = defaultdict(list)
        skipped_no_permission = 0
        for notif in notifications:
            # Check if worker has READ permission on the channel
            if can_worker_access_channel(db, worker_id, notif.channel_id, PermissionLevel.READ):
                by_channel[notif.channel_id].append(notif)
            else:
                skipped_no_permission += 1

        # Display notifications
        total_shown = 0
        for channel_id, channel_notifs in by_channel.items():
            channel = get_channel(db, channel_id)
            channel_name = channel.name if channel else channel_id

            click.echo(f"# {channel_name}")
            click.echo("-" * 40)

            for notif in channel_notifs:
                # Get the message
                message = get_message(db, notif.message_id)
                if not message:
                    continue

                # Format timestamp
                timestamp = notif.created_at
                if hasattr(timestamp, 'strftime'):
                    timestamp = timestamp.strftime("%Y-%m-%d %H:%M")

                # Status indicator
                status_icon = {
                    "pending": "●",
                    "read": "○",
                    "actioned": "✓",
                    "closed": "✗",
                }.get(notif.status, "?")

                # Display notification
                click.echo(f"[{status_icon}] [{timestamp}] {message.from_worker_id}: {message.content}")
                click.echo(f"    ID: {notif.id} | Priority: P{notif.priority}")
                total_shown += 1

                # Optionally mark as read
                if mark_read and notif.status == "pending":
                    mark_notification_read(db, notif.id)

            click.echo("")

        # Summary
        pending_count = count_pending_notifications(db, worker_id)
        click.echo(f"Showing {total_shown} notification(s). {pending_count} pending total.")

        if skipped_no_permission > 0:
            click.echo(f"({skipped_no_permission} notifications hidden due to permission restrictions)")

        if mark_read:
            click.echo("Displayed notifications marked as read.")

    finally:
        db.close()
