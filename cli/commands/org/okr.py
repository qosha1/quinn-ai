"""
qn org okr command group.

Commands for managing OKRs (Objectives and Key Results) via beads.
OKRs are beads epic issues with the 'okr' label.
"""

import json
import logging
import sqlite3
import click
from typing import Optional

from commands.context import pass_context, Context
from core.bd_wrapper import run_bd
from core.constants import BEAD_TYPE_EPIC
from core.db import get_org_db_path, open_database

_logger = logging.getLogger(__name__)


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
    type=click.Choice(["open", "in_progress", "closed", "active", "completed", "cancelled", "draft"]),
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
@click.option(
    "--from-db",
    "from_db",
    is_flag=True,
    help="Read from database instead of beads (shows key results progress)",
)
@pass_context
def list_cmd(ctx: Context, status: Optional[str], assignee: Optional[str], show_all: bool, from_db: bool):
    """List all OKRs from the organization.

    Shows objective title, status, owner, and progress.

    \b
    Examples:
      qn org okr list                    # List open OKRs from beads
      qn org okr list --from-db          # List from database with progress
      qn org okr list --all              # Include closed
      qn org okr list --status=in_progress
      qn org okr list --assignee=ceo
    """
    from core.queries import list_okrs, get_worker_by_name

    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    if from_db:
        # Read from database - shows key results and progress
        db = open_database(db_path)
        try:
            # Map beads status to db status
            db_status = None
            if status:
                status_map = {
                    "open": "active",
                    "in_progress": "active",
                    "closed": "completed",
                    "active": "active",
                    "completed": "completed",
                    "cancelled": "cancelled",
                    "draft": "draft",
                }
                db_status = status_map.get(status, status)

            # Resolve assignee to worker ID
            owner_id = None
            if assignee:
                worker = get_worker_by_name(db, assignee)
                if worker:
                    owner_id = worker.id
                else:
                    owner_id = assignee

            okrs = list_okrs(db, status=db_status, owner_id=owner_id, include_closed=show_all)

            if not okrs:
                click.echo("No OKRs found in database.")
                return

            for okr in okrs:
                click.echo("")
                click.echo(f"{'=' * 60}")
                click.echo(f"OKR: {okr.title}")
                click.echo(f"{'=' * 60}")
                click.echo(f"  ID: {okr.id}")
                click.echo(f"  Status: {okr.status}")
                click.echo(f"  Owner: {okr.owner_worker_id}")

                if okr.description:
                    click.echo(f"  Description: {okr.description[:100]}...")

                if okr.due_date:
                    click.echo(f"  Due: {okr.due_date}")

                # Show key results with progress
                if okr.key_results:
                    click.echo("  Key Results:")
                    for kr in okr.key_results:
                        progress = kr.progress()
                        status_icon = "✓" if kr.is_met() else "○"
                        click.echo(f"    {status_icon} {kr.metric}: {kr.current}/{kr.target} {kr.unit} ({progress:.0f}%)")
                    click.echo(f"  Overall Progress: {okr.progress():.0f}%")

                if okr.created_at:
                    created_str = okr.created_at.strftime('%Y-%m-%d') if hasattr(okr.created_at, 'strftime') else str(okr.created_at)[:10]
                    click.echo(f"  Created: {created_str}")
                else:
                    click.echo(f"  Created: N/A")

            click.echo("")
        finally:
            db.close()
        return

    # Default: Read from beads
    # Build bd list command - use label since 'okr' is not a valid beads type
    args = ["list", "--label=okr", "--json"]

    if status:
        # Map database statuses to beads statuses
        beads_status = status
        if status in ("active", "draft"):
            beads_status = "open"
        elif status in ("completed", "cancelled"):
            beads_status = "closed"
        args.append(f"--status={beads_status}")
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
        raise click.ClickException(
                f"Failed to list OKRs: {result.stderr}\n"
                "Ensure beads is properly configured for this organization."
            )

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


def _create_okr(
    ctx: Context,
    title: str,
    description: Optional[str],
    owner: str,
    priority: str,
    label: tuple,
    due: Optional[str],
    parent: Optional[str],
):
    """Shared implementation for set/add commands."""
    from core.queries import get_worker_by_name, create_okr

    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Build bd create command
    # Use epic type with okr label since 'okr' is not a valid beads type
    args = ["create", title, f"--type={BEAD_TYPE_EPIC}", f"--priority={priority}", "--label=okr"]

    if description:
        args.extend(["--description", description])

    if owner:
        args.extend(["--assignee", owner])

    for lbl in label:
        args.extend(["--label", lbl])

    if due:
        args.extend(["--due", due])

    if parent:
        args.extend(["--parent", parent])

    # Run bd create
    result = run_bd(
        args,
        org_path=org_path,
        capture_output=True,
        skip_permission_check=True,
    )

    if result.returncode != 0:
        raise click.ClickException(
            f"Failed to create OKR: {result.stderr}\n"
            "Check beads configuration and try again."
        )

    # Extract created ID from output
    output = result.stdout.strip()
    click.echo(output)

    # Try to extract ID from "Created issue: xxx" output
    okr_id = None
    for line in output.split("\n"):
        if "Created" in line and "-" in line:
            words = line.split()
            for word in reversed(words):
                if "-" in word and not word.startswith("-"):
                    okr_id = word.strip()
                    break
            break

    # Also store OKR in database for querying
    if okr_id:
        db = open_database(db_path)
        try:
            # Resolve owner name to worker ID
            owner_id = owner
            if owner:
                worker = get_worker_by_name(db, owner)
                if worker:
                    owner_id = worker.id
                else:
                    # Use owner as-is if not found (might be a worker ID)
                    owner_id = owner

            # Parse due date if provided
            due_date = None
            if due:
                from datetime import date, timedelta
                import re
                # Handle relative dates like +3m
                if due.startswith("+"):
                    match = re.match(r"\+(\d+)([dwmy])", due)
                    if match:
                        num = int(match.group(1))
                        unit = match.group(2)
                        today = date.today()
                        if unit == "d":
                            due_date = today + timedelta(days=num)
                        elif unit == "w":
                            due_date = today + timedelta(weeks=num)
                        elif unit == "m":
                            due_date = date(today.year, today.month + num, today.day)
                        elif unit == "y":
                            due_date = date(today.year + num, today.month, today.day)
                else:
                    # Try ISO format
                    try:
                        due_date = date.fromisoformat(due)
                    except ValueError:
                        pass

            create_okr(
                db=db,
                title=title,
                owner_id=owner_id,
                parent_id=parent,
                description=description,
                status="active",
                okr_id=okr_id,
                due_date=due_date,
            )
        except sqlite3.Error as e:
            # Database storage is secondary - don't fail if it errors
            _logger.warning(f"Failed to store OKR in database (ignored): {e}")
            pass
        finally:
            db.close()

        click.echo("")
        click.echo(f"Link work items to this OKR with:")
        click.echo(f"  bd dep add <work-id> {okr_id} --type serves")


@okr_cmd.command("set")
@click.option("--title", required=True, help="OKR objective title")
@click.option("--description", "-d", help="OKR description with objective and key results")
@click.option("--owner", default="ceo", help="Owner/assignee of the OKR (default: ceo)")
@click.option("--priority", "-p", type=click.Choice(["0", "1", "2", "3", "4"]), default="1",
              help="Priority (0=critical, 1=high, 2=medium, 3=low, 4=backlog)")
@click.option("--label", "-l", multiple=True, help="Labels to apply (can be used multiple times)")
@click.option("--due", help="Due date (e.g., +3m, 2025-03-31)")
@click.option("--parent", help="Parent OKR ID for hierarchy (creates child OKR)")
@pass_context
def set_cmd(ctx: Context, title: str, description: Optional[str], owner: str,
            priority: str, label: tuple, due: Optional[str], parent: Optional[str]):
    """Create or update an OKR.

    Creates an OKR bead that work items can link to via 'serves' dependency.

    \b
    Examples:
      qn org okr set --title "Q1 Revenue Growth" --owner ceo
      qn org okr set --title "Launch MVP" --due=+3m --parent=okr-abc
      qn org okr set --title "Scale Team" -p 1 -l hiring -l growth

    \b
    OKR Description Format:
      ## Objective
      The qualitative goal being pursued

      ## Key Results
      - Singular, calculable metrics
      - Not subjective measures
    """
    _create_okr(ctx, title, description, owner, priority, label, due, parent)


# Alias: 'add' -> 'set'
@okr_cmd.command("add")
@click.option("--title", required=True, help="OKR objective title")
@click.option("--description", "-d", help="OKR description")
@click.option("--owner", default="ceo", help="Owner (default: ceo)")
@click.option("--priority", "-p", type=click.Choice(["0", "1", "2", "3", "4"]), default="1")
@click.option("--label", "-l", multiple=True, help="Labels")
@click.option("--due", help="Due date")
@click.option("--parent", help="Parent OKR ID")
@pass_context
def add_cmd(ctx: Context, title: str, description: Optional[str], owner: str,
            priority: str, label: tuple, due: Optional[str], parent: Optional[str]):
    """Alias for 'set'. Create a new OKR."""
    _create_okr(ctx, title, description, owner, priority, label, due, parent)


@okr_cmd.command("cascade")
@click.option("--root", help="Root OKR ID to start from (default: show all)")
@pass_context
def cascade_cmd(ctx: Context, root: Optional[str]):
    """Show OKR hierarchy tree.

    Displays OKRs in a tree structure showing parent-child relationships.
    Board -> CEO -> Directors -> Managers -> Workers

    \b
    Examples:
      qn org okr cascade              # Show full OKR tree
      qn org okr cascade --root=okr-abc  # Start from specific OKR
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    if root:
        # Show tree from specific OKR
        result = run_bd(
            ["dep", "tree", root],
            org_path=org_path,
            capture_output=True,
            skip_permission_check=True,
        )

        if result.returncode != 0:
            raise click.ClickException(
                f"Failed to show OKR tree: {result.stderr}\n"
                "Verify the OKR ID '{root}' is correct."
            )

        click.echo(f"OKR Cascade from {root}:")
        click.echo("=" * 50)
        click.echo(result.stdout)
    else:
        # List all OKRs and show hierarchy
        result = run_bd(
            ["list", "--label=okr", "--json", "--all"],
            org_path=org_path,
            capture_output=True,
            skip_permission_check=True,
        )

        if result.returncode != 0:
            if not result.stdout.strip():
                click.echo("No OKRs found.")
                return
            raise click.ClickException(
                f"Failed to list OKRs: {result.stderr}\n"
                "Ensure beads is properly configured for this organization."
            )

        try:
            okrs = json.loads(result.stdout)
        except json.JSONDecodeError:
            click.echo("No OKRs found.")
            return

        if not okrs:
            click.echo("No OKRs found.")
            return

        click.echo("OKR Cascade:")
        click.echo("=" * 50)

        # Build parent-child map
        children_map: dict[str, list] = {}
        roots = []

        for okr in okrs:
            okr_id = okr.get("id", "")
            parent_id = okr.get("parent_id")

            if parent_id:
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(okr)
            else:
                roots.append(okr)

        def print_okr(okr: dict, indent: int = 0):
            """Recursively print OKR and children."""
            prefix = "  " * indent
            status = okr.get("status", "open")
            title = okr.get("title", "Untitled")
            okr_id = okr.get("id", "?")
            assignee = okr.get("assignee", "")

            status_icon = "✓" if status == "closed" else "○" if status == "open" else "▶"
            owner_str = f" ({assignee})" if assignee else ""

            click.echo(f"{prefix}{status_icon} {okr_id}: {title}{owner_str}")

            # Print children
            for child in children_map.get(okr_id, []):
                print_okr(child, indent + 1)

        # Print from roots
        for root_okr in roots:
            print_okr(root_okr)

        click.echo("")


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
        raise click.ClickException(
            f"OKR '{okr_id}' not found.\n"
            "Run 'qn org okr list' to see available OKRs."
        )

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


@okr_cmd.command("progress")
@click.argument("okr_id")
@pass_context
def progress_cmd(ctx: Context, okr_id: str):
    """Show OKR progress including key results.

    Displays progress percentage and status of each key result.

    \b
    Example:
      qn org okr progress okr-abc
    """
    from core.db import open_database
    from core.queries import get_okr

    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)
    try:
        okr = get_okr(db, okr_id)
        if not okr:
            raise click.ClickException(
                f"OKR '{okr_id}' not found.\n"
                "Run 'qn org okr list' to see available OKRs."
            )

        click.echo(f"OKR: {okr.title}")
        click.echo(f"ID: {okr.id}")
        click.echo(f"Status: {okr.status}")
        click.echo(f"Owner: {okr.owner_worker_id}")
        if okr.due_date:
            click.echo(f"Due: {okr.due_date}")
        click.echo("")

        if okr.key_results:
            click.echo("Key Results:")
            click.echo("-" * 50)
            for kr in okr.key_results:
                progress_pct = kr.progress()
                status_icon = "✓" if kr.is_met() else "○"
                click.echo(
                    f"  {status_icon} {kr.metric}: {kr.current}/{kr.target} {kr.unit} "
                    f"({progress_pct:.0f}%)"
                )
            click.echo("")
            click.echo(f"Overall Progress: {okr.progress():.0f}%")
            if okr.all_key_results_met():
                click.echo("All key results met!")
        else:
            click.echo("No key results defined for this OKR.")
            click.echo("Add key results with: qn org okr update-kr <okr-id> --metric=... --target=...")

    finally:
        db.close()


@okr_cmd.command("update-kr")
@click.argument("okr_id")
@click.option("--metric", "-m", required=True, help="Key result metric name")
@click.option("--current", "-c", type=float, help="Current value (updates existing)")
@click.option("--target", "-t", type=float, help="Target value (for new key result)")
@click.option("--unit", "-u", default="count", help="Unit of measurement (default: count)")
@pass_context
def update_kr_cmd(ctx: Context, okr_id: str, metric: str, current: Optional[float],
                  target: Optional[float], unit: str):
    """Update or add a key result for an OKR.

    To add a new key result, specify --metric, --target, and optionally --current.
    To update an existing key result, specify --metric and --current.

    \b
    Examples:
      # Add new key result
      qn org okr update-kr okr-abc --metric="test_coverage" --target=80 --unit="%"

      # Update existing key result progress
      qn org okr update-kr okr-abc --metric="test_coverage" --current=72

      # Add with initial value
      qn org okr update-kr okr-abc --metric="bugs_fixed" --target=10 --current=3 --unit="count"
    """
    from core.db import open_database
    from core.queries import get_okr, update_okr_key_result, add_okr_key_result

    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)
    try:
        okr = get_okr(db, okr_id)
        if not okr:
            raise click.ClickException(
                f"OKR '{okr_id}' not found.\n"
                "Run 'qn org okr list' to see available OKRs."
            )

        # Check if key result exists
        existing_kr = next((kr for kr in okr.key_results if kr.metric == metric), None)

        if existing_kr:
            # Update existing
            if current is None:
                raise click.ClickException(
                    f"Key result '{metric}' exists. Use --current to update its value."
                )
            update_okr_key_result(db, okr_id, metric, current)
            click.echo(f"Updated {metric}: {current}/{existing_kr.target} {existing_kr.unit}")
        else:
            # Add new
            if target is None:
                raise click.ClickException(
                    f"Key result '{metric}' does not exist. Use --target to create it."
                )
            initial = current if current is not None else 0.0
            add_okr_key_result(db, okr_id, metric, target, unit, initial)
            click.echo(f"Added key result: {metric} (target: {target} {unit})")

        # Show updated progress
        okr = get_okr(db, okr_id)
        click.echo(f"OKR Progress: {okr.progress():.0f}%")

    finally:
        db.close()


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
        raise click.ClickException(
            f"Failed to link work item to OKR: {result.stderr}\n"
            "Verify both '{work_id}' and '{okr_id}' exist."
        )

    click.echo(f"Linked {work_id} -> {okr_id} (serves)")
    click.echo(f"Work item '{work_id}' now serves OKR '{okr_id}'")
