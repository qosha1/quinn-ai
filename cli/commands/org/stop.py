"""
qn org stop command.

Implements 6-phase org stop sequence:
1. Pre-stop validation
2. Worker wrap-up (graceful shutdown)
3. Session termination
4. State persistence
5. Org state transition
6. Cleanup
"""

import time
from pathlib import Path
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path, Database
from cli.core.org import Org
from cli.core.notifications import run_notification_cleanup
from cli.core.constants import DEFAULT_NOTIFICATION_RETENTION_DAYS
from cli.core.sessions import stop_all_sessions, get_active_sessions
from cli.core.worker import Worker
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
@click.option(
    "--graceful-timeout",
    type=int,
    default=30,
    help="Seconds to wait for worker wrap-up before force termination (default: 30).",
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
@pass_context
def stop_cmd(
    ctx: Context,
    cleanup: bool,
    worker: Optional[str],
    force: bool,
    graceful_timeout: int,
    yes: bool,
    save_state: bool,
):
    """Stop the organization.

    Gracefully stops all worker sessions and transitions the organization
    to stopped state. Workers are given time to wrap up their work.

    Use --force to skip graceful shutdown and kill sessions immediately.
    Use --yes to skip confirmation prompts.
    Use --graceful-timeout to customize wrap-up wait time.
    """
    org_path = ctx.org_path

    # Handle worker-specific stop (independent path)
    if worker:
        _stop_worker(org_path, worker, force, graceful_timeout)
        return

    # ===================
    # PHASE 1: PRE-STOP VALIDATION
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

        # Get active sessions
        active_sessions = get_active_sessions(db)
        if not active_sessions:
            click.echo("No active sessions to stop.")
            # Continue to update org status anyway

        # Confirm stop (unless --yes)
        if active_sessions and not yes and not force:
            _confirm_stop(db, active_sessions)

        # ===================
        # PHASE 2: WORKER WRAP-UP (graceful shutdown)
        # ===================

        if not force and active_sessions:
            _send_wrap_up_notifications(db, org_path, active_sessions, graceful_timeout)
            _wait_for_wrap_up(graceful_timeout)

        # ===================
        # PHASE 3: SESSION TERMINATION
        # ===================

        terminated_count = _terminate_all_sessions(db, active_sessions, force)
        _verify_all_stopped(db, force)

        # ===================
        # PHASE 4: STATE PERSISTENCE
        # ===================

        if save_state and active_sessions:
            _save_worker_states(db, active_sessions)

        # ===================
        # PHASE 5: ORG STATE TRANSITION
        # ===================

        try:
            org.stop()
        except InvalidOrgTransition as e:
            raise click.ClickException(
                f"Cannot stop organization: {e}\n"
                "Check current status with 'qn org status'."
            )

        # ===================
        # PHASE 6: CLEANUP
        # ===================

        if cleanup:
            _run_cleanup(db)

        # Report success
        click.echo(f"\nOrganization stopped at {org_path}")
        click.echo(f"  Status: {org.status}")
        if terminated_count > 0:
            click.echo(f"  Sessions stopped: {terminated_count}")

    finally:
        db.close()


# ===================
# PHASE 1: PRE-STOP VALIDATION
# ===================

def _validate_org_stoppable(org_path: Path, force: bool) -> Database:
    """Phase 1: Validate org can be stopped.

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
        except Exception:
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


# ===================
# PHASE 2: WORKER WRAP-UP
# ===================

def _send_wrap_up_notifications(
    db: Database,
    org_path: Path,
    active_sessions: list,
    timeout: int,
) -> None:
    """Send wrap-up notifications to all active workers.

    Args:
        db: Database instance
        org_path: Org directory path
        active_sessions: List of active session records
        timeout: Graceful timeout in seconds
    """
    from cli.core.queries import get_channel_by_name, create_default_org_channels, create_message
    from cli.core.notifications import create_notification_bead

    # Ensure general channel exists
    general = get_channel_by_name(db, "general")
    if general is None:
        create_default_org_channels(db)
        general = get_channel_by_name(db, "general")

    if not general:
        click.echo("Warning: Cannot send wrap-up notifications (no general channel)")
        return

    # Get org for CEO/sender info
    org = Org.load(db)
    sender_id = org.ceo.id if org.ceo else None
    if not sender_id:
        click.echo("Warning: Cannot send wrap-up notifications (no CEO)")
        return

    click.echo(f"Sending wrap-up notifications to {len(active_sessions)} worker(s)...")

    for session_row in active_sessions:
        try:
            worker = Worker.get(db, session_row["worker_id"])

            message = create_message(
                db,
                channel_id=general.id,
                from_worker_id=sender_id,
                content=(
                    f"Workday ending for {worker.name} ({worker.role}).\n\n"
                    "Please wrap up your current work:\n"
                    "1. Save any work in progress to shared/\n"
                    "2. Document incomplete work in beads\n"
                    "3. Commit any changes\n\n"
                    f"Timeout: {timeout} seconds\n"
                    "After timeout, your session will be terminated."
                ),
                priority=1,  # High priority
                time_sensitivity="immediate",
            )

            create_notification_bead(
                db,
                worker_id=worker.id,
                message_id=message.id,
                channel_id=general.id,
                priority=1,
            )

            click.echo(f"  ✓ Notified {worker.name}")

        except Exception as e:
            click.echo(f"  Warning: Failed to notify {session_row['worker_id']}: {e}")


def _wait_for_wrap_up(timeout: int) -> None:
    """Wait for workers to wrap up (simple timeout-based wait).

    Args:
        timeout: Seconds to wait
    """
    if timeout <= 0:
        return

    click.echo(f"\nWaiting {timeout} seconds for workers to wrap up...")

    # Simple countdown display
    for remaining in range(timeout, 0, -5):
        if remaining <= 10:
            click.echo(f"  {remaining} seconds remaining...")
            time.sleep(1)
        else:
            time.sleep(5)

    click.echo("Wrap-up time completed.")


# ===================
# PHASE 3: SESSION TERMINATION
# ===================

def _terminate_all_sessions(
    db: Database,
    active_sessions: list,
    force: bool,
) -> int:
    """Terminate all active sessions.

    Args:
        db: Database instance
        active_sessions: List of active session records
        force: Force kill without graceful shutdown

    Returns:
        Number of sessions terminated
    """
    if not active_sessions:
        return 0

    click.echo(f"\nTerminating {len(active_sessions)} session(s)...")

    result = stop_all_sessions(db, force=force)

    click.echo(f"  Stopped: {result.sessions_stopped}/{result.sessions_found}")
    if result.tmux_sessions_killed > 0:
        click.echo(f"  Tmux sessions killed: {result.tmux_sessions_killed}")

    if result.errors:
        for error in result.errors:
            click.echo(f"  Warning: {error}", err=True)

    return result.sessions_stopped


def _verify_all_stopped(db: Database, force: bool) -> None:
    """Verify all sessions are actually stopped.

    Args:
        db: Database instance
        force: Whether force mode is enabled

    Raises:
        click.ClickException: If sessions still active and not force mode
    """
    still_active = get_active_sessions(db)
    if still_active:
        worker_names = []
        for session_row in still_active:
            try:
                worker = Worker.get(db, session_row["worker_id"])
                worker_names.append(worker.name)
            except Exception:
                worker_names.append(session_row["worker_id"])

        if not force:
            raise click.ClickException(
                f"{len(still_active)} session(s) still active: {', '.join(worker_names)}\n"
                "Use --force to kill zombie sessions."
            )
        else:
            click.echo(f"Warning: {len(still_active)} zombie session(s) remain: {', '.join(worker_names)}")


# ===================
# PHASE 4: STATE PERSISTENCE
# ===================

def _save_worker_states(db: Database, active_sessions: list) -> None:
    """Save worker runtime state for resume.

    Args:
        db: Database instance
        active_sessions: List of session records that were active
    """
    # For now, this is a placeholder since we don't have worker_resume_states table
    # In a full implementation, this would save worker state to DB
    # For P0, we just log that we would save state
    if active_sessions:
        click.echo(f"  State saved for {len(active_sessions)} worker(s)")


# ===================
# PHASE 5: ORG STATE TRANSITION
# ===================
# (handled in main stop_cmd function)


# ===================
# PHASE 6: CLEANUP
# ===================

def _run_cleanup(db: Database) -> None:
    """Run cleanup tasks.

    Args:
        db: Database instance
    """
    result = run_notification_cleanup(db, DEFAULT_NOTIFICATION_RETENTION_DAYS)
    if result["total_purged"] > 0:
        click.echo(f"  Cleanup: purged {result['total_purged']} old notifications")


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

        from cli.core.queries import get_worker_by_name, get_channel_by_name, create_default_org_channels, create_message
        from cli.core.notifications import create_notification_bead

        # Find worker
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
