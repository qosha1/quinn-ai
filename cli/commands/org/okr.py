"""
qn org okr command group.

Commands for managing OKRs (Objectives and Key Results) via beads.
OKRs are beads issues with type=okr.
"""

import json
import click
from typing import Optional

from cli.commands.context import pass_context, Context
from cli.core.bd_wrapper import run_bd
from cli.core.db import get_org_db_path


@click.group()
def okr_cmd():
    """Manage organization OKRs.

    OKRs are tracked as beads issues with type 'okr'.
    Work items link to OKRs via 'serves' dependency.
    """
    pass


@okr_cmd.command("list")
@click.option(
    "--status",
    type=click.Choice(["open", "in_progress", "closed"]),
    help="Filter by status",
)
@click.option(
    "--assignee",
    type=str,
    help="Filter by assignee/owner",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Include closed OKRs",
)
@pass_context
def list_cmd(ctx: Context, status: Optional[str], assignee: Optional[str], show_all: bool):
    """List all OKRs from the organization.

    Shows objective title, status, owner, and progress.

    \b
    Examples:
      qn org okr list                    # List open OKRs
      qn org okr list --all              # Include closed
      qn org okr list --status=in_progress
      qn org okr list --assignee=ceo
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Build bd list command
    args = ["list", "--type=okr", "--json"]

    if status:
        args.append(f"--status={status}")
    elif not show_all:
        # Default to open issues only
        args.append("--status=open")

    if assignee:
        args.append(f"--assignee={assignee}")

    if show_all:
        args.append("--all")

    # Run bd list
    result = run_bd(
        args,
        org_path=org_path,
        capture_output=True,
        skip_permission_check=True,
    )

    if result.returncode != 0:
        if "no issues found" in result.stderr.lower() or not result.stdout.strip():
            click.echo("No OKRs found.")
            return
        raise click.ClickException(f"Failed to list OKRs: {result.stderr}")

    # Parse JSON output
    try:
        okrs = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Might be empty or non-JSON output
        click.echo("No OKRs found.")
        return

    if not okrs:
        click.echo("No OKRs found.")
        return

    # Display OKRs
    for okr in okrs:
        click.echo("")
        click.echo(f"{'=' * 60}")
        click.echo(f"OKR: {okr.get('title', 'Untitled')}")
        click.echo(f"{'=' * 60}")
        click.echo(f"  ID: {okr.get('id', 'N/A')}")
        click.echo(f"  Status: {okr.get('status', 'N/A')}")
        click.echo(f"  Priority: P{okr.get('priority', 2)}")

        assignee_val = okr.get('assignee')
        if assignee_val:
            click.echo(f"  Owner: {assignee_val}")

        # Description (first 100 chars)
        desc = okr.get('description', '')
        if desc:
            click.echo(f"  Description: {desc.strip()[:100]}...")

        # Show labels
        labels = okr.get('labels', [])
        if labels:
            click.echo(f"  Labels: {', '.join(labels)}")

        # Created/Updated
        created = okr.get('created_at', '')
        if created:
            click.echo(f"  Created: {created[:10]}")

    click.echo("")


@okr_cmd.command("add")
@click.option(
    "--title",
    required=True,
    help="OKR objective title",
)
@click.option(
    "--description", "-d",
    help="OKR description with objective and key results",
)
@click.option(
    "--owner",
    default="ceo",
    help="Owner/assignee of the OKR (default: ceo)",
)
@click.option(
    "--priority", "-p",
    type=click.Choice(["0", "1", "2", "3", "4"]),
    default="1",
    help="Priority (0=critical, 1=high, 2=medium, 3=low, 4=backlog)",
)
@click.option(
    "--label", "-l",
    multiple=True,
    help="Labels to apply (can be used multiple times)",
)
@click.option(
    "--due",
    help="Due date (e.g., +3m, 2025-03-31, 'end of Q1')",
)
@pass_context
def add_cmd(
    ctx: Context,
    title: str,
    description: Optional[str],
    owner: str,
    priority: str,
    label: tuple,
    due: Optional[str],
):
    """Create a new OKR as a beads issue.

    Creates an OKR bead that work items can link to via 'serves' dependency.

    \b
    Examples:
      qn org okr add --title "Q1 Revenue Growth" --owner ceo
      qn org okr add --title "Launch MVP" -d "## Objective\\nLaunch by March" --due=+3m
      qn org okr add --title "Scale Team" -p 1 -l hiring -l growth

    \b
    OKR Description Format:
      ## Objective
      The qualitative goal being pursued

      ## Key Results
      - Singular, calculable metrics
      - Not subjective measures
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Build bd create command
    args = ["create", title, "--type=okr", f"--priority={priority}"]

    if description:
        args.extend(["--description", description])

    if owner:
        args.extend(["--assignee", owner])

    for lbl in label:
        args.extend(["--label", lbl])

    if due:
        args.extend(["--due", due])

    # Run bd create
    result = run_bd(
        args,
        org_path=org_path,
        capture_output=True,
        skip_permission_check=True,
    )

    if result.returncode != 0:
        raise click.ClickException(f"Failed to create OKR: {result.stderr}")

    # Extract created ID from output
    output = result.stdout.strip()
    click.echo(output)

    # Parse ID if in JSON mode or from text
    if "--json" in args:
        try:
            data = json.loads(output)
            okr_id = data.get("id")
        except json.JSONDecodeError:
            okr_id = None
    else:
        # Try to extract ID from "Created issue: xxx" output
        okr_id = None
        for line in output.split("\n"):
            if "Created" in line and "-" in line:
                # Find the ID (last word with a dash)
                words = line.split()
                for word in reversed(words):
                    if "-" in word and not word.startswith("-"):
                        okr_id = word.strip()
                        break
                break

    if okr_id:
        click.echo("")
        click.echo(f"Link work items to this OKR with:")
        click.echo(f"  bd dep add <work-id> {okr_id} --type serves")


@okr_cmd.command("show")
@click.argument("okr_id")
@pass_context
def show_cmd(ctx: Context, okr_id: str):
    """Show detailed OKR information.

    Displays the OKR objective, key results, and linked work items.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Show the OKR
    result = run_bd(
        ["show", okr_id],
        org_path=org_path,
        capture_output=True,
        skip_permission_check=True,
    )

    if result.returncode != 0:
        raise click.ClickException(f"OKR not found: {okr_id}")

    click.echo(result.stdout)

    # Show work items that serve this OKR
    click.echo("")
    click.echo("Work items serving this OKR:")
    click.echo("-" * 40)

    # List issues with serves dependency to this OKR
    dep_result = run_bd(
        ["list", "--json", f"--serves={okr_id}"],
        org_path=org_path,
        capture_output=True,
        skip_permission_check=True,
    )

    if dep_result.returncode == 0 and dep_result.stdout.strip():
        try:
            work_items = json.loads(dep_result.stdout)
            if work_items:
                for item in work_items:
                    status = item.get("status", "open")
                    title = item.get("title", "Untitled")
                    item_id = item.get("id", "?")
                    click.echo(f"  [{status}] {item_id}: {title}")
            else:
                click.echo("  No linked work items yet.")
        except json.JSONDecodeError:
            click.echo("  No linked work items yet.")
    else:
        click.echo("  No linked work items yet.")


@okr_cmd.command("link")
@click.argument("work_id")
@click.argument("okr_id")
@pass_context
def link_cmd(ctx: Context, work_id: str, okr_id: str):
    """Link a work item to an OKR.

    Creates a 'serves' dependency from the work item to the OKR,
    indicating that completing the work item serves the OKR objective.

    \b
    Example:
      qn org okr link task-abc okr-xyz
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Add serves dependency
    result = run_bd(
        ["dep", "add", work_id, okr_id, "--type", "serves"],
        org_path=org_path,
        capture_output=True,
        skip_permission_check=True,
    )

    if result.returncode != 0:
        raise click.ClickException(f"Failed to link: {result.stderr}")

    click.echo(f"Linked {work_id} -> {okr_id} (serves)")
    click.echo(f"Work item '{work_id}' now serves OKR '{okr_id}'")
