"""msgr channels command - List available channels."""

import click

from cli.msgr.context import pass_context, MsgrContext
from cli.msgr.utils import format_channel_name
from cli.core.queries.channel import get_worker_channels


@click.command()
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Show all channels (default: subscribed only)",
)
@pass_context
def channels(ctx: MsgrContext, show_all: bool):
    """List available channels.

    Shows channels you're subscribed to by default.
    Use --all to see all channels in the org.

    \b
    Channel types:
      #general    - Topic channels (org-wide)
      #eng        - Team channels (team members only)
      @alice↔bob  - Direct messages (2 participants)

    \b
    Examples:
      msgr channels         # Your subscribed channels
      msgr channels --all   # All org channels
    """
    db = ctx.db
    worker_id = ctx.worker_id

    # Get channels
    if show_all:
        # Get all channels from database
        rows = db.fetchall("SELECT * FROM channels ORDER BY name")
        channel_list = [
            {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "subscribed": False,  # We'll check this below
            }
            for row in rows
        ]

        # Check which ones worker is subscribed to
        subscribed_ids = {
            c.id for c in get_worker_channels(db, worker_id)
        }
        for chan in channel_list:
            chan["subscribed"] = chan["id"] in subscribed_ids
    else:
        # Get subscribed channels only
        subscribed = get_worker_channels(db, worker_id)
        channel_list = [
            {
                "id": c.id,
                "name": c.name,
                "type": c.type,
                "subscribed": True,
            }
            for c in subscribed
        ]

    # Display channels
    if not channel_list:
        if show_all:
            click.echo("No channels in org")
        else:
            click.echo("Not subscribed to any channels")
            click.echo("Use 'msgr channels --all' to see all available channels")
        return

    click.echo(f"📡 {len(channel_list)} channel(s):\n")

    # Group by type
    topic_channels = [c for c in channel_list if c["type"] == "topic"]
    team_channels = [c for c in channel_list if c["type"] == "team"]
    direct_channels = [c for c in channel_list if c["type"] == "direct"]

    # Display topic channels
    if topic_channels:
        click.echo("Topic channels (org-wide):")
        for chan in topic_channels:
            name = format_channel_name(chan["name"], chan["type"])
            sub_marker = "✓" if chan["subscribed"] else " "
            click.echo(f"  [{sub_marker}] {name}")
        click.echo()

    # Display team channels
    if team_channels:
        click.echo("Team channels:")
        for chan in team_channels:
            name = format_channel_name(chan["name"], chan["type"])
            sub_marker = "✓" if chan["subscribed"] else " "
            click.echo(f"  [{sub_marker}] {name}")
        click.echo()

    # Display direct channels
    if direct_channels:
        click.echo("Direct messages:")
        for chan in direct_channels:
            name = format_channel_name(chan["name"], chan["type"])
            click.echo(f"  {name}")
        click.echo()
