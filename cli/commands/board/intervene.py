"""
qn board intervention commands.

Manual worker control for board oversight:
- pause: Pause a worker (stop session, preserve state)
- resume: Resume a paused worker
- fire: Terminate a worker immediately

Per CLAUDE.md: "Board = Gutterguards. Humans intervene only when org is off-track."
"""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import update_worker_runtime_status
from shared import WorkerNotFound, InvalidStateTransition


@click.command()
@click.argument("worker_id")
@click.option("--reason", "-r", help="Reason for pausing (for audit trail)")
@pass_context
def pause_cmd(ctx: Context, worker_id: str, reason: str):
    """Pause a worker.

    Stops the worker's session and sets runtime status to 'stopped'.
    The worker's lifecycle status remains unchanged (still 'active').
    Use 'qn board resume' to restart the worker.

    WORKER_ID: The worker ID to pause.
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
        try:
            worker = Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(f"Worker not found: {worker_id}")

        # Check current state
        runtime = worker.runtime_status
        lifecycle = worker.lifecycle_status

        if lifecycle != "active":
            raise click.ClickException(
                f"Cannot pause worker in '{lifecycle}' lifecycle state. "
                "Only active workers can be paused."
            )

        if runtime in ("stopped", "crashed", None):
            raise click.ClickException(
                f"Worker session already stopped (runtime: {runtime})"
            )

        click.echo(f"Pausing worker: {worker.name} ({worker_id})")
        click.echo(f"  Current lifecycle: {lifecycle}")
        click.echo(f"  Current runtime: {runtime}")

        # Stop the session
        try:
            worker.stop_session()
        except InvalidStateTransition as e:
            raise click.ClickException(f"Cannot pause: {e}")

        click.echo("")
        click.echo("Worker paused successfully.")
        click.echo(f"  Runtime status: stopped")
        if reason:
            click.echo(f"  Reason: {reason}")
        click.echo("")
        click.echo("Use 'qn board resume' to restart this worker.")

    finally:
        db.close()


@click.command()
@click.argument("worker_id")
@pass_context
def resume_cmd(ctx: Context, worker_id: str):
    """Resume a paused worker.

    Restarts the worker's session. The worker must have been previously
    paused with 'qn board pause'.

    Note: This sets the runtime to 'starting'. The actual session needs
    to be spawned separately using the session management system.

    WORKER_ID: The worker ID to resume.
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
        try:
            worker = Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(f"Worker not found: {worker_id}")

        # Check current state
        runtime = worker.runtime_status
        lifecycle = worker.lifecycle_status

        if lifecycle != "active":
            raise click.ClickException(
                f"Cannot resume worker in '{lifecycle}' lifecycle state. "
                "Only active workers can be resumed."
            )

        if runtime not in ("stopped", "crashed"):
            raise click.ClickException(
                f"Worker is not paused (runtime: {runtime}). "
                "Use 'qn board pause' first."
            )

        click.echo(f"Resuming worker: {worker.name} ({worker_id})")
        click.echo(f"  Current lifecycle: {lifecycle}")
        click.echo(f"  Current runtime: {runtime}")

        # Update runtime status to starting
        # The actual session spawn will happen through the session system
        update_worker_runtime_status(db, worker_id, "starting")

        click.echo("")
        click.echo("Worker resume initiated.")
        click.echo("  Runtime status: starting")
        click.echo("")
        click.echo("The worker session will be spawned by the org session manager.")

    finally:
        db.close()


@click.command()
@click.argument("worker_id")
@click.option("--reason", "-r", required=True, help="Reason for termination (required for audit)")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@pass_context
def fire_cmd(ctx: Context, worker_id: str, reason: str, force: bool):
    """Terminate a worker immediately.

    This is a hard intervention that:
    1. Stops the worker's session immediately
    2. Freezes worker storage for review
    3. Unsubscribes from all channels
    4. Transitions lifecycle to 'terminated'
    5. Updates org-chart

    This action cannot be undone.

    WORKER_ID: The worker ID to terminate.
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
        try:
            worker = Worker(db, worker_id, org_path=org_path)
            # Load worker data to verify exists
            _ = worker.name
        except WorkerNotFound:
            raise click.ClickException(f"Worker not found: {worker_id}")

        lifecycle = worker.lifecycle_status

        if lifecycle == "terminated":
            raise click.ClickException(
                f"Worker already terminated."
            )

        # Check if this is the CEO
        from cli.core.org import Org
        org = Org.load(db)
        is_ceo = org.ceo_worker_id == worker_id

        click.echo(f"Terminating worker: {worker.name} ({worker_id})")
        click.echo(f"  Role: {worker.role}")
        click.echo(f"  Lifecycle: {lifecycle}")
        click.echo(f"  Runtime: {worker.runtime_status or '(no session)'}")
        if is_ceo:
            click.echo("")
            click.echo("WARNING: This is the CEO. Terminating the CEO will:")
            click.echo("  - Leave the organization without leadership")
            click.echo("  - Require appointing a new CEO")
        click.echo("")
        click.echo(f"Reason: {reason}")
        click.echo("")

        if not force:
            # Confirmation prompt
            confirm = click.prompt(
                f"Type '{worker.name.upper()}' to confirm termination",
                default="",
            )
            if confirm != worker.name.upper():
                click.echo("Termination cancelled.")
                return

        click.echo("")
        click.echo("Terminating worker...")

        # First transition to offboarding if active
        if lifecycle == "active":
            try:
                worker.start_offboarding()
                click.echo("  Lifecycle: active -> offboarding")
            except InvalidStateTransition:
                pass  # Already not in active state

        # Then terminate
        try:
            worker.terminate()
            click.echo("  Lifecycle: -> terminated")
            click.echo("  Session: stopped")
            click.echo("  Storage: frozen")
            click.echo("  Channels: unsubscribed")
        except InvalidStateTransition as e:
            raise click.ClickException(f"Cannot terminate: {e}")

        click.echo("")
        click.echo(f"Worker {worker.name} terminated.")
        click.echo(f"Reason logged: {reason}")

        if is_ceo:
            click.echo("")
            click.echo("Next steps:")
            click.echo("  1. Organization needs a new CEO")
            click.echo("  2. Review terminated worker's frozen storage")
            click.echo("  3. Reassign or close any open work items")

    finally:
        db.close()
