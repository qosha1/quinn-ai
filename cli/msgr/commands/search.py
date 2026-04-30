"""msgr search command - Full-text search across messages."""

import click

from cli.msgr.context import pass_context, MsgrContext
from cli.core.queries.messages import search_messages


@click.command()
@click.argument("query")
@click.option(
    "--channel",
    default=None,
    help="Limit search to this channel name",
)
@click.option(
    "--limit",
    default=20,
    type=int,
    help="Maximum results to return",
)
@pass_context
def search(ctx: MsgrContext, query: str, channel: str | None, limit: int):
    """Search messages across all channels.

    \b
    Examples:
      msgr search fundraise
      msgr search 'product brief' --channel general
      msgr search escalation --limit 5
    """
    db = ctx.db

    results = search_messages(db, query, channel_id=None, limit=limit)

    if channel:
        # Collect all channel IDs with this name (no UNIQUE constraint on name)
        rows = db.fetchall("SELECT id FROM channels WHERE name = ?", (channel,))
        valid_ids = {r["id"] for r in rows}
        results = [r for r in results if r.channel_id in valid_ids]

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"Found {len(results)} result(s) for '{query}':\n")
    for msg in results:
        ts = str(msg.created_at)[:16] if msg.created_at else "?"
        preview = msg.content.replace("\n", " ")[:100]
        click.echo(f"  [{ts}] {msg.channel_id} — {msg.from_worker_id}")
        click.echo(f"  {preview}")
        click.echo()
