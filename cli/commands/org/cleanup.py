"""
qn org cleanup command.
"""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.notifications import run_notification_cleanup
from cli.core.constants import DEFAULT_NOTIFICATION_RETENTION_DAYS


@click.command()
@click.option(
    "--retention-days",
    default=DEFAULT_NOTIFICATION_RETENTION_DAYS,
    help=f"Days to retain closed notifications (default: {DEFAULT_NOTIFICATION_RETENTION_DAYS}).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be cleaned up without deleting.",
)
@pass_context
def cleanup_cmd(ctx: Context, retention_days: int, dry_run: bool):
    """Clean up old notifications and orphaned data.

    Purges closed notifications older than retention period and
    removes orphaned notifications for deleted messages/workers.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        if dry_run:
            # Count what would be cleaned up
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=retention_days)

            old_count = db.fetchone(
                "SELECT COUNT(*) as count FROM notification_beads WHERE status = 'closed' AND closed_at < ?",
                (cutoff,)
            )["count"]

            orphan_msg_count = db.fetchone(
                "SELECT COUNT(*) as count FROM notification_beads WHERE message_id NOT IN (SELECT id FROM messages)"
            )["count"]

            orphan_worker_count = db.fetchone(
                "SELECT COUNT(*) as count FROM notification_beads WHERE worker_id NOT IN (SELECT id FROM workers)"
            )["count"]

            click.echo("Dry run - would clean up:")
            click.echo(f"  Old closed notifications (>{retention_days} days): {old_count}")
            click.echo(f"  Orphaned notifications (missing message): {orphan_msg_count}")
            click.echo(f"  Orphaned notifications (missing worker): {orphan_worker_count}")
            click.echo(f"  Total: {old_count + orphan_msg_count + orphan_worker_count}")
        else:
            result = run_notification_cleanup(db, retention_days)

            click.echo("Cleanup completed:")
            click.echo(f"  Old notifications purged: {result['old_notifications_purged']}")
            click.echo(f"  Orphaned notifications purged: {result['orphaned_notifications_purged']}")
            click.echo(f"  Total purged: {result['total_purged']}")

    finally:
        db.close()
