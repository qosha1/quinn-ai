"""
qn wrkr search command.

Search messages using full-text search. Supports FTS5 query syntax.
"""

import click

from commands.context import pass_context, Context
from core.db import open_database, get_org_db_path
from core.worker import Worker
from core.queries import search_messages, get_channel
from core.permissions import (
    PermissionLevel,
    can_worker_access_channel,
)
from shared import WorkerNotFound


@click.command()
@click.argument("query")
@click.option(
    "--channel", "-c",
    help="Filter to specific channel ID.",
)
@click.option(
    "--limit", "-n",
    default=20,
    help="Maximum messages to return. Default: 20",
)
@click.option(
    "--offset",
    default=0,
    help="Offset for pagination.",
)
@pass_context
def search_cmd(ctx: Context, query: str, channel: str, limit: int, offset: int):
    """Search messages using full-text search.

    Searches message content using FTS5 syntax. Supports:
    - Simple terms: error
    - Phrases: "connection refused"
    - AND/OR: error AND timeout
    - NOT: error NOT debug
    - Prefix: err*

    Examples:
      qn wrkr search "deployment failed"
      qn wrkr search error --channel #engineering
      qn wrkr search "status:blocked" --limit 50
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

        # Search messages
        messages = search_messages(
            db=db,
            query=query,
            channel_id=channel,
            limit=limit,
            offset=offset,
        )

        if not messages:
            click.echo(f"No messages found matching: {query}")
            return

        # Group by channel for display
        by_channel: dict[str, list] = {}
        skipped_no_permission = 0

        for msg in messages:
            # Check read permission
            if can_worker_access_channel(db, worker_id, msg.channel_id, PermissionLevel.READ):
                if msg.channel_id not in by_channel:
                    by_channel[msg.channel_id] = []
                by_channel[msg.channel_id].append(msg)
            else:
                skipped_no_permission += 1

        # Display results
        total_shown = 0
        for channel_id, channel_msgs in by_channel.items():
            chan = get_channel(db, channel_id)
            channel_name = chan.name if chan else channel_id

            click.echo(f"# {channel_name}")
            click.echo("-" * 40)

            for msg in channel_msgs:
                # Format timestamp
                timestamp = msg.created_at
                if hasattr(timestamp, 'strftime'):
                    timestamp = timestamp.strftime("%Y-%m-%d %H:%M")

                # Display message
                click.echo(f"[{timestamp}] {msg.from_worker_id}: {msg.content}")
                click.echo(f"    ID: {msg.id}")
                total_shown += 1

            click.echo("")

        # Summary
        click.echo(f"Found {total_shown} message(s) matching: {query}")

        if skipped_no_permission > 0:
            click.echo(f"({skipped_no_permission} messages hidden due to permission restrictions)")

        if offset > 0 or len(messages) == limit:
            click.echo(f"Use --offset {offset + limit} for more results.")

    finally:
        db.close()
