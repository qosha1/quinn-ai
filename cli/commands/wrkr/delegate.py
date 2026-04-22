"""
qn wrkr delegate command.

Workers with direct reports can delegate tasks to subordinates.
"""

import json
from typing import Optional

import click

from commands.context import pass_context, Context
from core.db import open_database, get_org_db_path
from core.worker import Worker
from core.bd_wrapper import run_bd
from core.queries import get_workers_by_manager
from core.permissions import (
    PermissionLevel,
    can_worker_access_bead,
)
from shared import WorkerNotFound


@click.command()
@click.argument("task_id")
@click.option(
    "--to",
    "target_worker",
    required=True,
    help="Worker name or ID to delegate to.",
)
@click.option(
    "--reason",
    type=str,
    default="",
    help="Reason for delegation (logged in task history).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON.",
)
@pass_context
def delegate_cmd(
    ctx: Context,
    task_id: str,
    target_worker: str,
    reason: str,
    as_json: bool,
):
    """Delegate a task to a subordinate worker.

    Reassigns a task to a direct report. Only workers with direct reports
    (managers) can delegate tasks. The target must be a subordinate of
    the delegating worker.

    TASK_ID is the beads issue ID to delegate.

    \b
    Examples:
      qn wrkr delegate beads-abc123 --to alice
      qn wrkr delegate beads-xyz789 --to bob --reason "Better fit for their skills"
    """
    worker_id = ctx.worker_id
    if not worker_id:
        raise click.ClickException(
            "Worker ID not specified.\n"
            "Use --worker-id option or set QUINN_WORKER_ID environment variable."
        )

    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        # Verify calling worker exists
        try:
            worker = Worker.get(db, worker_id)
        except WorkerNotFound:
            raise click.ClickException(
                f"Worker '{worker_id}' not found.\n"
                "Run 'qn org status' to see available workers."
            )

        # Check if worker is active
        if worker.lifecycle_status != "active":
            if as_json:
                click.echo(json.dumps({
                    "error": "worker_not_active",
                    "lifecycle": worker.lifecycle_status,
                }))
            else:
                raise click.ClickException(
                    f"Worker must be active to delegate tasks.\n"
                    f"Current status: {worker.lifecycle_status}"
                )
            return

        # Get direct reports to verify delegation authority
        direct_reports = get_workers_by_manager(db, worker_id)
        if not direct_reports:
            if as_json:
                click.echo(json.dumps({
                    "error": "no_authority",
                    "message": "No direct reports - cannot delegate",
                }))
            else:
                raise click.ClickException(
                    "You have no direct reports.\n"
                    "Only managers can delegate tasks to subordinates."
                )
            return

        # Find target worker among direct reports
        target = None
        for report in direct_reports:
            if report.name.lower() == target_worker.lower() or report.id == target_worker:
                target = Worker.get(db, report.id)
                break

        if target is None:
            # Target not found in direct reports
            report_names = ", ".join(r.name for r in direct_reports)
            if as_json:
                click.echo(json.dumps({
                    "error": "not_subordinate",
                    "target": target_worker,
                    "direct_reports": [r.name for r in direct_reports],
                }))
            else:
                raise click.ClickException(
                    f"'{target_worker}' is not your direct report.\n"
                    f"You can only delegate to: {report_names}"
                )
            return

        # Check target worker is active
        if target.lifecycle_status != "active":
            if as_json:
                click.echo(json.dumps({
                    "error": "target_not_active",
                    "target": target.name,
                    "lifecycle": target.lifecycle_status,
                }))
            else:
                raise click.ClickException(
                    f"Cannot delegate to '{target.name}' - not in active status.\n"
                    f"Current status: {target.lifecycle_status}"
                )
            return

        # Verify caller has permission on the task
        if not can_worker_access_bead(db, worker_id, task_id, PermissionLevel.WRITE):
            if as_json:
                click.echo(json.dumps({
                    "error": "no_permission",
                    "task_id": task_id,
                    "permission_required": "delegate",
                }))
            else:
                raise click.ClickException(
                    f"You don't have permission to delegate task '{task_id}'.\n"
                    "You can only delegate tasks you own or manage."
                )
            return

        # Perform delegation using beads
        comment_text = f"Delegated by {worker.name}"
        if reason:
            comment_text += f": {reason}"

        try:
            # Update assignee
            result = run_bd(
                [
                    "update",
                    task_id,
                    f"--assignee={target.id}",
                ],
                org_path=org_path,
                worker_id=worker_id,
                capture_output=True,
                skip_permission_check=True,  # Already checked above
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Failed to update task"
                if as_json:
                    click.echo(json.dumps({
                        "error": "delegation_failed",
                        "message": error_msg,
                    }))
                else:
                    raise click.ClickException(f"Delegation failed: {error_msg}")
                return

            # Add comment about delegation
            comment_result = run_bd(
                [
                    "comment",
                    task_id,
                    comment_text,
                ],
                org_path=org_path,
                worker_id=worker_id,
                capture_output=True,
                skip_permission_check=True,
            )
            # Comment failure is non-critical, continue

            # Success output
            if as_json:
                click.echo(json.dumps({
                    "success": True,
                    "task_id": task_id,
                    "delegated_to": target.name,
                    "delegated_to_id": target.id,
                    "reason": reason or None,
                }))
            else:
                click.echo(f"Task '{task_id}' delegated to {target.name}.")
                if reason:
                    click.echo(f"  Reason: {reason}")
                click.echo("")
                click.echo(f"The task is now assigned to {target.name}.")
                click.echo(f"Use 'qn wrkr get-work' as {target.name} to see their work queue.")

        except FileNotFoundError:
            if as_json:
                click.echo(json.dumps({
                    "error": "beads_not_found",
                    "message": "Beads binary not found. Run 'scripts/build-beads.sh' to bundle it.",
                }))
            else:
                raise click.ClickException(
                    "Beads binary not found.\n"
                    "Run 'scripts/build-beads.sh' to bundle it."
                )

        except ValueError as e:
            if as_json:
                click.echo(json.dumps({
                    "error": "config_error",
                    "message": str(e),
                }))
            else:
                raise click.ClickException(f"Configuration error: {e}")

    finally:
        db.close()
