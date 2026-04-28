"""
qn wrkr report command.

Workers send status reports to their manager.
"""

import json
from typing import Optional, List

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.bd_wrapper import run_bd
from cli.core.queries import get_worker
from shared import WorkerNotFound


@click.command()
@click.option(
    "--to",
    "recipient",
    help="Manager to send report to. Defaults to your manager.",
)
@click.option(
    "--summary",
    required=True,
    help="Report summary.",
)
@click.option(
    "--link",
    "linked_tasks",
    multiple=True,
    help="Task IDs to link to this report (can specify multiple).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output as JSON.",
)
@pass_context
def report_cmd(
    ctx: Context,
    recipient: Optional[str],
    summary: str,
    linked_tasks: tuple,
    as_json: bool,
):
    """Send a status report to your manager.

    Creates a report message that summarizes work completed. Reports can
    be linked to completed task IDs for reference.

    \b
    Examples:
      qn wrkr report --summary "Completed feature X implementation"
      qn wrkr report --summary "Fixed bug in auth" --link beads-abc123
      qn wrkr report --to alice --summary "Weekly update" --link beads-1 --link beads-2
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
                    f"Worker must be active to send reports.\n"
                    f"Current status: {worker.lifecycle_status}"
                )
            return

        # Determine recipient
        if recipient:
            # Look up specified recipient
            recipient_data = get_worker(db, recipient)
            if not recipient_data:
                # Try by name
                from cli.core.queries import resolve_worker
                recipient_data = resolve_worker(db, recipient)
            if not recipient_data:
                if as_json:
                    click.echo(json.dumps({
                        "error": "recipient_not_found",
                        "recipient": recipient,
                    }))
                else:
                    raise click.ClickException(
                        f"Recipient '{recipient}' not found.\n"
                        "Use 'qn org status' to see available workers."
                    )
                return
            recipient_id = recipient_data.id
            recipient_name = recipient_data.name
        else:
            # Default to manager
            if not worker.manager_id:
                if as_json:
                    click.echo(json.dumps({
                        "error": "no_manager",
                        "message": "No manager assigned and no --to specified",
                    }))
                else:
                    raise click.ClickException(
                        "You have no manager assigned.\n"
                        "Specify a recipient with --to option."
                    )
                return
            recipient_id = worker.manager_id
            manager_data = get_worker(db, recipient_id)
            recipient_name = manager_data.name if manager_data else recipient_id

        # Build report content
        report_content = f"## Status Report from {worker.name}\n\n"
        report_content += f"{summary}\n"

        if linked_tasks:
            report_content += "\n### Related Tasks\n"
            for task_id in linked_tasks:
                report_content += f"- {task_id}\n"

        # Create report bead using bd
        try:
            # Create the report as a bead. The bundled bd binary's valid
            # types are bug|feature|task|epic|chore|merge-request|molecule|
            # gate|agent|role|convoy|event — no 'report' type. Use 'chore'
            # (low-cost informational work) and add a 'report' label for
            # filtering. Closes quinn-ai-ad95.
            bd_args = [
                "create",
                "--title", f"Report: {summary[:50]}{'...' if len(summary) > 50 else ''}",
                "--type", "chore",
                "--priority", "3",  # Low priority - informational
                "--labels", "report",
                f"--assignee={recipient_id}",
            ]

            # Add description
            bd_args.extend(["--description", report_content])

            result = run_bd(
                bd_args,
                org_path=org_path,
                worker_id=worker_id,
                capture_output=True,
            )

            report_id = None
            if result.returncode == 0 and result.stdout:
                # Try to extract bead ID from output
                output = result.stdout.strip()
                # bd create typically outputs the ID or a message containing it
                if output.startswith("beads-") or output.startswith("quinnai-"):
                    report_id = output.split()[0]  # Get just the ID part
                else:
                    # Look for ID in output
                    for word in output.split():
                        if word.startswith("beads-") or word.startswith("quinnai-"):
                            report_id = word
                            break

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Failed to create report"
                if as_json:
                    click.echo(json.dumps({
                        "error": "report_creation_failed",
                        "message": error_msg,
                    }))
                else:
                    raise click.ClickException(f"Failed to create report: {error_msg}")
                return

            # Link to related tasks if specified
            if linked_tasks and report_id:
                for task_id in linked_tasks:
                    link_result = run_bd(
                        ["dep", "add", report_id, task_id],
                        org_path=org_path,
                        worker_id=worker_id,
                        capture_output=True,
                        skip_permission_check=True,
                    )
                    # Link failure is non-critical

            # Success output
            if as_json:
                click.echo(json.dumps({
                    "success": True,
                    "report_id": report_id,
                    "to": recipient_name,
                    "to_id": recipient_id,
                    "summary": summary,
                    "linked_tasks": list(linked_tasks) if linked_tasks else [],
                }))
            else:
                click.echo(f"Report sent to {recipient_name}.")
                if report_id:
                    click.echo(f"  Report ID: {report_id}")
                click.echo(f"  Summary: {summary}")
                if linked_tasks:
                    click.echo(f"  Linked tasks: {', '.join(linked_tasks)}")
                click.echo("")
                click.echo(f"Your manager will be notified of this report.")

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
