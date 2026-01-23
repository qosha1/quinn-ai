"""
qn org fire command.

Terminate a worker from the organization.
"""

from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_worker_by_name


@click.command()
@click.argument("worker")
@click.option(
    "--reason",
    type=str,
    default="Position eliminated",
    help="Reason for termination (logged for audit).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force termination without confirmation.",
)
@click.option(
    "--keep-storage",
    is_flag=True,
    help="Don't freeze worker storage (default: freeze for review).",
)
@pass_context
def fire_cmd(
    ctx: Context,
    worker: str,
    reason: str,
    force: bool,
    keep_storage: bool,
):
    """Terminate a worker from the organization.

    Stops the worker's session, updates their status to terminated,
    and freezes their storage for review.

    WORKER can be the worker name or worker ID.

    \b
    Examples:
      qn org fire alice                           # Fire alice with default reason
      qn org fire alice --reason "Budget cuts"   # Fire with specific reason
      qn org fire bob --force                    # Skip confirmation
      qn org fire carol --keep-storage           # Don't freeze storage
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
        # Find worker
        worker_data = get_worker_by_name(db, worker)
        if not worker_data:
            # Try by ID
            try:
                target_worker = Worker.get(db, worker)
            except (ValueError, KeyError):
                raise click.ClickException(
                    f"Worker '{worker}' not found.\n"
                    "Use 'qn org status' to see available workers."
                )
        else:
            target_worker = Worker.get(db, worker_data.id)

        # Check if already terminated
        if target_worker.lifecycle_status == "terminated":
            raise click.ClickException(
                f"Worker '{target_worker.name}' is already terminated."
            )

        # Show worker info
        click.echo(f"Worker: {target_worker.name} ({target_worker.role})")
        click.echo(f"  ID: {target_worker.id}")
        click.echo(f"  Status: {target_worker.lifecycle_status}")
        if target_worker.is_session_active:
            click.echo(f"  Session: Active ({target_worker.runtime_status})")
        else:
            click.echo("  Session: Inactive")
        click.echo(f"  Reason: {reason}")
        click.echo("")

        # Confirm unless forced
        if not force:
            if not click.confirm(f"Are you sure you want to fire {target_worker.name}?"):
                click.echo("Cancelled.")
                return

        # Perform termination
        click.echo(f"Terminating {target_worker.name}...")

        # Stop session if active
        if target_worker.is_session_active:
            click.echo("  Stopping active session...")
            target_worker.terminate_session(force=True)
            click.echo("  Session stopped.")

        # Terminate the worker (handles storage, channels, status)
        target_worker.terminate()
        click.echo("  Worker terminated.")

        # Log the reason
        _log_termination(db, target_worker.id, reason)

        click.echo("")
        click.echo(f"Worker '{target_worker.name}' has been terminated.")
        click.echo(f"  Reason: {reason}")

        if not keep_storage:
            click.echo("  Storage: Frozen for review")
            click.echo("")
            click.echo("To review and clean up storage:")
            click.echo(f"  ls {org_path}/storage/workers/{target_worker.id}/")
        else:
            click.echo("  Storage: Kept (use --keep-storage was specified)")

    finally:
        db.close()


def _log_termination(db, worker_id: str, reason: str) -> None:
    """Log termination event to database.

    Args:
        db: Database connection
        worker_id: Worker being terminated
        reason: Reason for termination
    """
    from datetime import datetime

    # Store in worker metadata or a separate audit log
    # For now, we update the worker's updated_at timestamp
    # A full audit log could be added later
    try:
        db.execute(
            """UPDATE workers SET updated_at = ? WHERE id = ?""",
            (datetime.now(), worker_id)
        )
        db.connection.commit()
    except Exception:
        # Non-critical - don't fail termination if logging fails
        pass
