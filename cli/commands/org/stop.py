"""
qn org stop command.

Implements 7-phase org stop sequence via OrgStopController:
1. Validation and preparation
2. Send wrap-up requests to all workers
3. Wait for acknowledgements (with per-role timeouts)
4. Stop sessions (graceful then force)
5. Update worker states
6. Persist state and cleanup
7. Transition org to STOPPED
"""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path, Database
from cli.core.org import Org
from cli.core.stop_controller import OrgStopController, OrgStopResult
from cli.core.sessions import get_active_sessions, stop_all_sessions
from cli.core.worker import Worker
from shared import InvalidOrgTransition
from shared.enums import OrgStatus
from shared.exceptions import WorkerNotFound

_logger = logging.getLogger(__name__)


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
@click.option(
    "--graceful-timeout",
    type=int,
    default=None,
    help="Override per-role timeout for worker wrap-up (uses role-based defaults if not set).",
)
@click.option(
    "--yes", "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation prompts (for automation).",
)
@click.option(
    "--save-state/--no-save-state",
    default=True,
    help="Save worker state for resume (default: True).",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Show detailed phase-by-phase progress.",
)
@pass_context
def stop_cmd(
    ctx: Context,
    cleanup: bool,
    worker: Optional[str],
    force: bool,
    graceful_timeout: Optional[int],
    yes: bool,
    save_state: bool,
    verbose: bool,
):
    """Stop the organization.

    Gracefully stops all worker sessions and transitions the organization
    to stopped state. Workers are given role-based time to wrap up:
    - CEO: 120 seconds
    - Managers/Directors: 90 seconds
    - Workers: 60 seconds

    Use --force to skip graceful shutdown and kill sessions immediately.
    Use --yes to skip confirmation prompts.
    Use --graceful-timeout to override the per-role default timeouts.
    """
    org_path = ctx.org_path

    # Handle worker-specific stop (independent path)
    if worker:
        _stop_worker(org_path, worker, force, graceful_timeout or 60)
        return

    # ===================
    # PRE-VALIDATION
    # ===================

    db = _validate_org_stoppable(org_path, force)

    try:
        org = Org.load(db)

        # Check if already stopped (idempotent)
        if org.status == OrgStatus.STOPPED.value:
            click.echo("Organization is already stopped.")
            if force:
                _cleanup_zombie_sessions(db)
            return

        # Get active sessions for confirmation
        active_sessions = get_active_sessions(db)
        if not active_sessions:
            click.echo("No active sessions to stop.")
            # Continue to update org status anyway

        # Confirm stop (unless --yes)
        if active_sessions and not yes and not force:
            _confirm_stop(db, active_sessions)

        # ===================
        # EXECUTE STOP SEQUENCE
        # ===================

        controller = OrgStopController(db, org_path, org)
        result = controller.execute(
            force=force,
            save_state=save_state,
            cleanup=cleanup,
            graceful_timeout=graceful_timeout,
        )

        # Report results
        _report_result(result, org_path, verbose)

        # Handle failure
        if not result.success:
            raise click.ClickException(
                "Organization stop failed. See errors above.\n"
                "Use --force to force stop."
            )

    finally:
        db.close()


def _validate_org_stoppable(org_path: Path, force: bool) -> Database:
    """Validate org can be stopped.

    Returns:
        Database instance

    Raises:
        click.ClickException: If org cannot be stopped
    """
    db_path = get_org_db_path(org_path)
    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    # Check org status
    org = Org.load(db)
    if org.status not in [OrgStatus.RUNNING.value, OrgStatus.STOPPED.value]:
        db.close()
        raise click.ClickException(
            f"Cannot stop organization in '{org.status}' state.\n"
            "Organization must be 'running' or 'stopped'.\n"
            "Check current status with 'qn org status'."
        )

    return db


def _confirm_stop(db: Database, active_sessions: list) -> None:
    """Confirm org stop with user.

    Args:
        db: Database instance
        active_sessions: List of active session records

    Raises:
        click.Abort: If user cancels
    """
    click.echo(f"\nFound {len(active_sessions)} active worker session(s):")
    for session_row in active_sessions[:10]:  # Show first 10
        try:
            worker = Worker.get(db, session_row["worker_id"])
            runtime_status = worker.runtime_status or "unknown"
            click.echo(f"  - {worker.name} ({worker.role}) - {runtime_status}")
        except (sqlite3.Error, WorkerNotFound) as e:
            _logger.debug(f"Failed to load worker details: {e}")
            click.echo(f"  - {session_row['worker_id']} (unable to load worker)")

    if len(active_sessions) > 10:
        click.echo(f"  ... and {len(active_sessions) - 10} more")

    if not click.confirm("\nStop all workers and terminate sessions?"):
        click.echo("Cancelled.")
        raise click.Abort()


def _cleanup_zombie_sessions(db: Database) -> None:
    """Clean up zombie sessions (already stopped org with lingering sessions).

    Args:
        db: Database instance
    """
    active = get_active_sessions(db)
    if active:
        click.echo(f"Cleaning up {len(active)} zombie session(s)...")
        result = stop_all_sessions(db, force=True)
        click.echo(f"  Cleaned up {result.sessions_stopped} session(s)")


def _report_result(result: OrgStopResult, org_path: Path, verbose: bool) -> None:
    """Report stop sequence results to user.

    Args:
        result: OrgStopResult from controller
        org_path: Org path for display
        verbose: Show phase details
    """
    if verbose:
        click.echo("\n--- Stop Sequence Phases ---")
        for phase in result.phases:
            status = "OK" if phase.success else "FAILED"
            click.echo(f"  Phase {phase.phase}: {phase.name} [{status}]")
            click.echo(f"    {phase.message}")
            click.echo(f"    Duration: {phase.duration_seconds:.2f}s")
            if phase.details and verbose:
                for key, value in phase.details.items():
                    if key != "errors":
                        click.echo(f"    {key}: {value}")
        click.echo("")

    # Summary
    if result.success:
        click.echo(f"\nOrganization stopped at {org_path}")
        click.echo(f"  Workers stopped: {result.workers_stopped}")
        if result.workers_acked > 0:
            click.echo(f"  Workers acknowledged: {result.workers_acked}")
        if result.sessions_terminated > 0:
            click.echo(f"  Sessions terminated: {result.sessions_terminated}")
        if result.states_saved > 0:
            click.echo(f"  States saved for resume: {result.states_saved}")
        click.echo(f"  Total duration: {result.total_duration_seconds:.2f}s")

        # Surface unacked workers as a clear warning to stderr — these are
        # workers that didn't respond to the graceful-shutdown signal,
        # usually because the worker was idle/stuck and never processed
        # the wrap-up request. Without this, users only saw a buried log
        # line and no signal that the stop finished in degraded state.
        # (quinn-ai-ef4z)
        if result.unacked_workers:
            click.echo("", err=True)
            click.echo(
                f"  ⚠ {len(result.unacked_workers)} worker(s) did not acknowledge "
                f"graceful stop before timeout:",
                err=True,
            )
            for name in result.unacked_workers:
                click.echo(f"      - {name}", err=True)
            click.echo(
                "    These workers may have been idle, stuck, or never "
                "processed their initial prompt.",
                err=True,
            )
            click.echo(
                "    Stop completed via timeout fallback; sessions were "
                "force-terminated.",
                err=True,
            )
    else:
        click.echo("\nOrganization stop FAILED", err=True)

    # Errors
    if result.errors:
        click.echo("\nErrors:", err=True)
        for error in result.errors[:10]:  # Limit to 10
            click.echo(f"  - {error}", err=True)
        if len(result.errors) > 10:
            click.echo(f"  ... and {len(result.errors) - 10} more errors", err=True)


# ===================
# WORKER-SPECIFIC STOP
# ===================

def _stop_worker(
    org_path: Path,
    worker: str,
    force: bool,
    graceful_timeout: int,
) -> None:
    """Stop a workday for a specific worker (independent path).

    Args:
        org_path: Org directory path
        worker: Worker name or ID
        force: Force termination
        graceful_timeout: Wrap-up timeout

    Raises:
        click.ClickException: On error
    """
    db_path = get_org_db_path(org_path)
    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)
    try:
        org = Org.load(db)

        if org.status != OrgStatus.RUNNING.value:
            raise click.ClickException(
                "Organization is not running.\n"
                "Start the org before stopping a worker workday."
            )

        from cli.core.queries import resolve_worker, get_channel_by_name, create_default_org_channels, create_message
        from cli.core.notifications import create_notification_bead

        # Find worker
        worker_data = resolve_worker(db, worker)
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

        # Send wrap-up notification if not forcing
        if not force:
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
                        "Please wrap up your current work and save any durable outputs to shared/.\n\n"
                        f"Timeout: {graceful_timeout} seconds"
                    ),
                    priority=1,
                    time_sensitivity="immediate",
                )
                create_notification_bead(
                    db,
                    worker_id=worker_obj.id,
                    message_id=message.id,
                    channel_id=general.id,
                    priority=1,
                )

                click.echo(f"Sent wrap-up notification to {worker_obj.name}")
                click.echo(f"Waiting {graceful_timeout} seconds for wrap-up...")
                time.sleep(graceful_timeout)

        # Terminate session
        click.echo(f"Terminating session for {worker_obj.name}...")
        worker_obj.terminate_session(force=force)
        click.echo(f"Workday stopped for {worker_obj.name}")

    finally:
        db.close()
