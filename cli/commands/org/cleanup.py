"""
qn org cleanup command.
"""

import click

from commands.context import pass_context, Context
from core.db import open_database, get_org_db_path
from core.notifications import run_notification_cleanup
from core.constants import DEFAULT_NOTIFICATION_RETENTION_DAYS
from core.sessions.cleanup import (
    find_all_orphans,
    cleanup_orphaned_sessions,
)


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
@click.option(
    "--notifications/--no-notifications",
    default=True,
    help="Clean up old notifications (default: enabled).",
)
@click.option(
    "--sessions/--no-sessions",
    default=True,
    help="Clean up orphaned session resources (default: enabled).",
)
@click.option(
    "--delete-stale-sessions",
    is_flag=True,
    help="Delete stale session records instead of marking as crashed.",
)
@pass_context
def cleanup_cmd(
    ctx: Context,
    retention_days: int,
    dry_run: bool,
    notifications: bool,
    sessions: bool,
    delete_stale_sessions: bool,
):
    """Clean up old notifications and orphaned data.

    Purges closed notifications older than retention period and
    removes orphaned notifications for deleted messages/workers.

    Also cleans up orphaned session resources:
    - Kills tmux sessions that exist but aren't tracked in the database
    - Marks database session records as crashed if their tmux session is gone
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
            click.echo("Dry run - would clean up:")

            # Notification cleanup dry run
            if notifications:
                from datetime import datetime, timedelta
                cutoff = datetime.now() - timedelta(days=retention_days)

                old_count = db.fetchone(
                    "SELECT COUNT(*) as count FROM notification_beads WHERE status = 'closed' AND closed_at < ?",
                    (cutoff,)
                )["count"]

                expired_count = db.fetchone(
                    "SELECT COUNT(*) as count FROM notification_beads WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (datetime.now(),)
                )["count"]

                orphan_msg_count = db.fetchone(
                    "SELECT COUNT(*) as count FROM notification_beads WHERE message_id NOT IN (SELECT id FROM messages)"
                )["count"]

                orphan_worker_count = db.fetchone(
                    "SELECT COUNT(*) as count FROM notification_beads WHERE worker_id NOT IN (SELECT id FROM workers)"
                )["count"]

                click.echo("")
                click.echo("Notification cleanup:")
                click.echo(f"  Old closed notifications (>{retention_days} days): {old_count}")
                click.echo(f"  Expired notifications: {expired_count}")
                click.echo(f"  Orphaned notifications (missing message): {orphan_msg_count}")
                click.echo(f"  Orphaned notifications (missing worker): {orphan_worker_count}")
                click.echo(f"  Total notifications: {old_count + expired_count + orphan_msg_count + orphan_worker_count}")

            # Session cleanup dry run
            if sessions:
                orphans = find_all_orphans(db)
                tmux_orphans = [o for o in orphans if o.source == "tmux"]
                db_orphans = [o for o in orphans if o.source == "database"]

                click.echo("")
                click.echo("Session cleanup:")
                click.echo(f"  Orphaned tmux sessions (would kill): {len(tmux_orphans)}")
                for orphan in tmux_orphans:
                    click.echo(f"    - {orphan.session_name}")
                click.echo(f"  Stale DB records (would mark crashed): {len(db_orphans)}")
                for orphan in db_orphans:
                    click.echo(f"    - {orphan.session_id} (worker: {orphan.worker_id})")

            if not notifications and not sessions:
                click.echo("  Nothing to clean up (both --no-notifications and --no-sessions specified)")
        else:
            # Notification cleanup
            if notifications:
                result = run_notification_cleanup(db, retention_days)

                click.echo("Notification cleanup completed:")
                click.echo(f"  Old notifications purged: {result['old_notifications_purged']}")
                click.echo(f"  Expired notifications purged: {result['expired_notifications_purged']}")
                click.echo(f"  Orphaned notifications purged: {result['orphaned_notifications_purged']}")
                click.echo(f"  Total purged: {result['total_purged']}")

            # Session cleanup
            if sessions:
                session_result = cleanup_orphaned_sessions(
                    db=db,
                    kill_tmux=True,
                    update_db=True,
                    delete_stale=delete_stale_sessions,
                )

                click.echo("")
                click.echo("Session cleanup completed:")
                click.echo(f"  Orphaned tmux sessions killed: {session_result.tmux_sessions_killed}")
                click.echo(f"  Stale DB records updated: {session_result.db_records_updated}")
                if delete_stale_sessions:
                    click.echo(f"  Stale DB records deleted: {session_result.db_records_deleted}")

                if session_result.errors:
                    click.echo("")
                    click.echo("Errors encountered:")
                    for error in session_result.errors:
                        click.echo(f"  - {error}")

            if not notifications and not sessions:
                click.echo("Nothing to clean up (both --no-notifications and --no-sessions specified)")

    finally:
        db.close()
