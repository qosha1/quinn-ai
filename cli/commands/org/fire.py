"""
qn org fire command.

Terminate a worker from the organization.
"""

from typing import Optional
import logging
import sqlite3

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.rules import requires_rule_check
from cli.core.worker import Worker
from cli.core.queries import resolve_worker
from cli.core.org import Org
from shared.exceptions import WorkerNotFound

_logger = logging.getLogger(__name__)


@click.command()
@click.argument("worker")
@click.option(
    "--reason",
    type=str,
    default="Position eliminated",
    help="Reason for termination (logged for audit).",
)
@click.option(
    "--manager",
    help="Manager authorizing termination. Defaults to worker's manager.",
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
@click.option(
    "--reassign-to",
    "reassign_to",
    help="Reassign pending work to this worker (optional).",
)
@requires_rule_check("qn-org.fire")
@pass_context
def fire_cmd(
    ctx: Context,
    worker: str,
    reason: str,
    manager: Optional[str],
    force: bool,
    keep_storage: bool,
    reassign_to: Optional[str],
):
    """Terminate a worker from the organization.

    Stops the worker's session, updates their status to terminated,
    and freezes their storage for review. Only the worker's manager
    (or CEO) can authorize termination.

    WORKER can be the worker name or worker ID.

    \b
    Examples:
      qn org fire alice --reason "Budget cuts"   # Fire with specific reason
      qn org fire bob --force                    # Skip confirmation
      qn org fire carol --reassign-to dave       # Reassign work first
      qn org fire diana --keep-storage           # Don't freeze storage
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
        # Load org to get CEO info
        org = Org.load(db)

        # Find worker to terminate
        worker_data = resolve_worker(db, worker)
        if not worker_data:
            # Try by ID
            try:
                target_worker = Worker.get(db, worker)
            except (ValueError, KeyError, WorkerNotFound):
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

        # Cannot fire the CEO
        if target_worker.id == org.ceo_worker_id:
            raise click.ClickException(
                "Cannot terminate the CEO.\n"
                "The CEO can only be removed through board action."
            )

        # Determine and verify authorizing manager
        if manager:
            manager_data = resolve_worker(db, manager)
            if not manager_data:
                try:
                    auth_manager = Worker.get(db, manager)
                except (ValueError, KeyError, WorkerNotFound):
                    raise click.ClickException(
                        f"Manager '{manager}' not found.\n"
                        "Use 'qn org status' to see available workers."
                    )
            else:
                auth_manager = Worker.get(db, manager_data.id)
        elif target_worker.manager_id:
            # Default to worker's manager
            auth_manager = Worker.get(db, target_worker.manager_id)
        else:
            raise click.ClickException(
                f"Worker '{target_worker.name}' has no manager.\n"
                "Specify --manager to authorize termination."
            )

        # Verify authorization: must be worker's manager or CEO
        is_direct_manager = auth_manager.id == target_worker.manager_id
        is_ceo = auth_manager.id == org.ceo_worker_id

        if not (is_direct_manager or is_ceo):
            raise click.ClickException(
                f"'{auth_manager.name}' cannot terminate '{target_worker.name}'.\n"
                f"Only the worker's direct manager or CEO can authorize termination."
            )

        # Find reassignment target if specified
        reassign_worker = None
        if reassign_to:
            reassign_data = resolve_worker(db, reassign_to)
            if not reassign_data:
                try:
                    reassign_worker = Worker.get(db, reassign_to)
                except (ValueError, KeyError, WorkerNotFound):
                    raise click.ClickException(
                        f"Reassignment target '{reassign_to}' not found.\n"
                        "Use 'qn org status' to see available workers."
                    )
            else:
                reassign_worker = Worker.get(db, reassign_data.id)

            if reassign_worker.id == target_worker.id:
                raise click.ClickException(
                    "Cannot reassign work to the worker being terminated."
                )

            if reassign_worker.lifecycle_status != "active":
                raise click.ClickException(
                    f"Cannot reassign to '{reassign_worker.name}' - not in active status."
                )

        # Check for hiring authority
        from cli.core.queries import get_delegations_by_delegator
        has_authority = bool(target_worker.hiring_authority_scope.allowed_roles)
        downstream_count = 0
        if has_authority:
            downstream = get_delegations_by_delegator(db, target_worker.id)
            downstream_count = len(downstream)

        # Show worker info
        click.echo(f"Worker: {target_worker.name} ({target_worker.role})")
        click.echo(f"  ID: {target_worker.id}")
        click.echo(f"  Status: {target_worker.lifecycle_status}")
        click.echo(f"  Authorized by: {auth_manager.name}")
        if target_worker.is_session_active:
            click.echo(f"  Session: Active ({target_worker.runtime_status})")
        else:
            click.echo("  Session: Inactive")
        if has_authority:
            if downstream_count > 0:
                click.echo(f"  Authority: Will be revoked (has {downstream_count} downstream delegation(s))")
            else:
                click.echo("  Authority: Will be revoked")
        click.echo(f"  Reason: {reason}")
        if reassign_worker:
            click.echo(f"  Reassign work to: {reassign_worker.name}")
        click.echo("")

        # Confirm unless forced
        if not force:
            if not click.confirm(f"Are you sure you want to fire {target_worker.name}?"):
                click.echo("Cancelled.")
                return

        # Perform termination
        click.echo(f"Terminating {target_worker.name}...")

        # Handle work reassignment first
        if reassign_worker:
            click.echo(f"  Reassigning pending work to {reassign_worker.name}...")
            _reassign_pending_work(db, org_path, target_worker.id, reassign_worker.id)
            click.echo("  Work reassigned.")

        # Stop session if active
        if target_worker.is_session_active:
            click.echo("  Stopping active session...")
            target_worker.terminate_session(force=True)
            click.echo("  Session stopped.")

        # Revoke hiring authority if present (cascade to downstream delegations)
        if has_authority:
            click.echo("  Revoking hiring authority...")
            try:
                auth_manager.revoke_authority(
                    delegate=target_worker,
                    cascade=True,
                    reason=f"Terminated: {reason}",
                )
                if downstream_count > 0:
                    click.echo(f"  Authority revoked from {downstream_count + 1} worker(s) (cascade).")
                else:
                    click.echo("  Authority revoked.")
            except Exception as e:
                click.echo(f"  Warning: Failed to revoke authority: {e}")

        # Lifecycle: active -> offboarding -> terminated
        # Must go through offboarding first (freezes storage, creates review bead)
        if target_worker.lifecycle_status == "active":
            click.echo("  Starting offboarding...")
            target_worker.start_offboarding()
            click.echo("  Worker in offboarding state.")

        # Terminate the worker (handles channels, org-chart update, status)
        target_worker.terminate()
        click.echo("  Worker terminated.")

        # Log the reason
        _log_termination(db, target_worker.id, reason, auth_manager.id)

        click.echo("")
        click.echo(f"Worker '{target_worker.name}' has been terminated.")
        click.echo(f"  Reason: {reason}")
        click.echo(f"  Authorized by: {auth_manager.name}")
        if has_authority:
            if downstream_count > 0:
                click.echo(f"  Hiring authority: Revoked (cascade to {downstream_count} worker(s))")
            else:
                click.echo("  Hiring authority: Revoked")

        if not keep_storage:
            from cli.core.storage import StorageManager
            storage = StorageManager(org_path, db)
            worker_path = storage.get_worker_path(target_worker.id)
            frozen_path = worker_path.parent / f"{worker_path.name}.frozen"

            click.echo("  Storage: Frozen for review")
            click.echo("")
            click.echo("To review and clean up storage:")
            click.echo(f"  ls {frozen_path}")
        else:
            click.echo("  Storage: Kept (--keep-storage was specified)")

    finally:
        db.close()


def _reassign_pending_work(db, org_path, from_worker_id: str, to_worker_id: str) -> int:
    """Reassign pending work from one worker to another.

    Uses beads CLI to update work item assignments.

    Args:
        db: Database connection
        org_path: Path to org folder
        from_worker_id: Worker being terminated
        to_worker_id: Worker to receive work

    Returns:
        Number of items reassigned
    """
    from cli.core.bd_wrapper import run_bd

    # List work assigned to the terminated worker
    result = run_bd(
        args=["list", f"--assignee={from_worker_id}", "--json", "--status=open"],
        org_path=org_path,
        capture_output=True,
        skip_permission_check=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return 0

    import json
    try:
        work_items = json.loads(result.stdout)
    except json.JSONDecodeError:
        return 0

    count = 0
    for item in work_items:
        item_id = item.get("id")
        if item_id:
            # Reassign to new worker
            reassign_result = run_bd(
                args=["update", item_id, f"--assignee={to_worker_id}"],
                org_path=org_path,
                capture_output=True,
                skip_permission_check=True,
                skip_lifecycle_check=True,
            )
            if reassign_result.returncode == 0:
                count += 1

    return count


def _log_termination(db, worker_id: str, reason: str, authorized_by: str) -> None:
    """Log termination event to database.

    Args:
        db: Database connection
        worker_id: Worker being terminated
        reason: Reason for termination
        authorized_by: Manager who authorized termination
    """
    from datetime import datetime
    import json

    # Log to events table if it exists
    try:
        db.execute(
            """INSERT INTO events (id, event_type, source_worker_id, target_worker_id, payload, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                f"evt-{worker_id}-term",
                "worker_terminated",
                authorized_by,
                worker_id,
                json.dumps({"reason": reason, "authorized_by": authorized_by}),
                datetime.now(),
            )
        )
        db.connection.commit()
    except sqlite3.Error as e:
        # Events table may not exist or logging failed - non-critical
        _logger.debug(f"Failed to log fire event (ignored): {e}")
        pass

    # Update worker's updated_at timestamp
    try:
        db.execute(
            """UPDATE workers SET updated_at = ? WHERE id = ?""",
            (datetime.now(), worker_id)
        )
        db.connection.commit()
    except sqlite3.Error as e:
        # Non-critical - timestamp update is best-effort
        _logger.debug(f"Failed to update worker timestamp (ignored): {e}")
        pass
