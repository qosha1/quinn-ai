"""
qn org stop command.
"""

import click
from typing import Optional

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.notifications import run_notification_cleanup
from cli.core.constants import DEFAULT_NOTIFICATION_RETENTION_DAYS
from cli.core.sessions import stop_all_sessions
from shared import InvalidOrgTransition
from shared.enums import OrgStatus


@click.command()
@click.option(
    "--cleanup/--no-cleanup",
    default=True,
    help="Run notification cleanup on stop (default: True).",
)
@click.option(
    "--worker",
    help="Stop a workday for a specific worker (name or ID).",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force kill sessions without waiting for graceful shutdown.",
)
@pass_context
def stop_cmd(ctx: Context, cleanup: bool, worker: Optional[str], force: bool):
    """Stop the organization.

    Gracefully stops all worker sessions and transitions the organization
    to stopped state.

    By default, runs notification cleanup to purge old closed notifications.
    Use --no-cleanup to skip this step.
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
        org = Org.load(db)

        if worker:
            if org.status != OrgStatus.RUNNING.value:
                raise click.ClickException(
                    "Organization is not running.\n"
                    "Start the org before stopping a worker workday."
                )

            from cli.core.queries import get_worker_by_name, get_channel_by_name, create_default_org_channels, create_message
            from cli.core.notifications import create_notification_bead
            from cli.core.worker import Worker

            worker_data = get_worker_by_name(db, worker)
            if not worker_data:
                try:
                    worker_obj = Worker.get(db, worker)
                except (ValueError, KeyError):
                    raise click.ClickException(
                        f"Worker '{worker}' not found.\n"
                        "Use 'qn org status' to see available workers."
                    )
            else:
                worker_obj = Worker(db, worker_data.id, org_path=org_path)

            # Request wrap-up before stopping session
            general = get_channel_by_name(db, "general")
            if general is None:
                create_default_org_channels(db)
                general = get_channel_by_name(db, "general")

            if general:
                sender_id = worker_obj.manager_id or (org.ceo.id if org.ceo else worker_obj.id)
                message = create_message(
                    db,
                    channel_id=general.id,
                    from_worker_id=sender_id,
                    content=(
                        f"Workday ending for {worker_obj.name} ({worker_obj.role}).\n\n"
                        "Please wrap up your current work and save any durable outputs to shared/."
                    ),
                    priority=2,
                    time_sensitivity="hours",
                )
                create_notification_bead(
                    db,
                    worker_id=worker_obj.id,
                    message_id=message.id,
                    channel_id=general.id,
                    priority=2,
                )

            # Close session after wrap-up request
            worker_obj.terminate_session(force=force)
            click.echo(f"Workday stopped for {worker_obj.name}")
            return

        if org.status == OrgStatus.STOPPED.value:
            click.echo("Organization is already stopped.")
            return

        if org.status != OrgStatus.RUNNING.value:
            raise click.ClickException(
                f"Cannot stop organization in '{org.status}' state.\n"
                "Organization must be 'running' to stop.\n"
                "Check current status with 'qn org status'."
            )

        # Stop all worker sessions first
        session_result = stop_all_sessions(db, force=force)
        if session_result.sessions_found > 0:
            click.echo(
                f"Stopped {session_result.sessions_stopped}/{session_result.sessions_found} sessions"
            )
            if session_result.tmux_sessions_killed > 0:
                click.echo(f"  Tmux sessions killed: {session_result.tmux_sessions_killed}")
            if session_result.errors:
                for error in session_result.errors:
                    click.echo(f"  Warning: {error}")

        # Transition org to stopped state
        try:
            org.stop()
        except InvalidOrgTransition as e:
            raise click.ClickException(
                f"Cannot stop organization: {e}\n"
                "Check current status with 'qn org status'."
            )

        click.echo(f"Organization stopped at {org_path}")
        click.echo(f"Status: {org.status}")

        # Run cleanup if requested
        if cleanup:
            result = run_notification_cleanup(db, DEFAULT_NOTIFICATION_RETENTION_DAYS)
            if result["total_purged"] > 0:
                click.echo(f"Cleanup: purged {result['total_purged']} old notifications")

    finally:
        db.close()
