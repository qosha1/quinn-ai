"""qn org broadcast — send a message to a channel or all workers."""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.queries import (
    get_channel_by_name, get_workers_by_status,
    create_message, get_or_create_direct_channel,
    create_default_org_channels,
)


@click.command("broadcast")
@click.argument("message")
@click.option("--channel", default="general", show_default=True, help="Target channel name.")
@click.option("--all-workers", "all_workers", is_flag=True, help="DM every active worker.")
@click.option("--dry-run", is_flag=True, help="Preview without sending.")
@pass_context
def broadcast_cmd(ctx: Context, message: str, channel: str, all_workers: bool, dry_run: bool) -> None:
    """Broadcast a message to a channel or DM all active workers."""
    org_path = ctx.org_path
    db = open_database(get_org_db_path(org_path))
    try:
        org = Org.load(db)
        sender = org.ceo
        if sender is None:
            raise click.ClickException("No CEO found — cannot determine sender.")
        sender_id = sender.id

        if all_workers:
            workers = get_workers_by_status(db, "active")
            targets = [w for w in workers if w.id != sender_id]
            if dry_run:
                click.echo(f"[dry-run] Would DM {len(targets)} workers: {message!r}")
                return
            sent = 0
            for w in targets:
                ch = get_or_create_direct_channel(db, sender_id, w.id)
                create_message(db, channel_id=ch.id, from_worker_id=sender_id, content=message)
                sent += 1
            click.echo(f"Broadcast sent to {sent} workers.")
            return

        # Channel broadcast
        ch = get_channel_by_name(db, channel)
        if ch is None:
            create_default_org_channels(db)
            ch = get_channel_by_name(db, channel)
        if ch is None:
            raise click.ClickException(f"Channel #{channel} not found.")

        if dry_run:
            click.echo(f"[dry-run] Would send to #{channel}: {message!r}")
            return

        create_message(db, channel_id=ch.id, from_worker_id=sender_id, content=message)
        click.echo(f"Broadcast sent to #{channel}.")
    finally:
        db.close()
