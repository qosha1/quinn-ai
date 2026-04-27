"""qn org okr list — list OKRs from beads or the SQLite mirror."""

import json
from typing import Optional

import click

from cli.commands.context import Context, pass_context
from cli.core.db import get_org_db_path, open_database

from . import _helpers


def register(okr_group):
    @okr_group.command("list")
    @click.option(
        "--status",
        type=click.Choice(
            ["open", "in_progress", "closed", "active", "completed", "cancelled", "draft"]
        ),
        help="Filter by status",
    )
    @click.option("--assignee", type=str, help="Filter by assignee/owner")
    @click.option("--all", "show_all", is_flag=True, help="Include closed OKRs")
    @click.option(
        "--from-db",
        "from_db",
        is_flag=True,
        help="Read from database instead of beads (shows key results progress)",
    )
    @pass_context
    def list_cmd(
        ctx: Context,
        status: Optional[str],
        assignee: Optional[str],
        show_all: bool,
        from_db: bool,
    ):
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
        from cli.core.queries import get_worker_by_name, list_okrs

        org_path = ctx.org_path
        db_path = get_org_db_path(org_path)

        if not db_path.exists():
            raise click.ClickException(
                f"Organization not initialized at {org_path}\n"
                "Run 'qn org init' first."
            )

        if from_db:
            _list_from_db(db_path, status, assignee, show_all, list_okrs, get_worker_by_name)
            return

        _list_from_beads(org_path, status, assignee, show_all)

    return list_cmd


def _list_from_db(
    db_path,
    status: Optional[str],
    assignee: Optional[str],
    show_all: bool,
    list_okrs,
    get_worker_by_name,
) -> None:
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

        owner_id = None
        if assignee:
            worker = get_worker_by_name(db, assignee)
            owner_id = worker.id if worker else assignee

        okrs = list_okrs(db, status=db_status, owner_id=owner_id, include_closed=show_all)

        if not okrs:
            click.echo("No OKRs found in database.")
            return

        for okr in okrs:
            click.echo("")
            click.echo("=" * 60)
            click.echo(f"OKR: {okr.title}")
            click.echo("=" * 60)
            click.echo(f"  ID: {okr.id}")
            click.echo(f"  Status: {okr.status}")
            click.echo(f"  Owner: {okr.owner_worker_id}")
            if okr.description:
                click.echo(f"  Description: {okr.description[:100]}...")
            if okr.due_date:
                click.echo(f"  Due: {okr.due_date}")
            if okr.key_results:
                click.echo("  Key Results:")
                for kr in okr.key_results:
                    progress = kr.progress()
                    icon = "✓" if kr.is_met() else "○"
                    click.echo(
                        f"    {icon} {kr.metric}: {kr.current}/{kr.target} {kr.unit} ({progress:.0f}%)"
                    )
                click.echo(f"  Overall Progress: {okr.progress():.0f}%")
            if okr.created_at:
                created_str = (
                    okr.created_at.strftime("%Y-%m-%d")
                    if hasattr(okr.created_at, "strftime")
                    else str(okr.created_at)[:10]
                )
                click.echo(f"  Created: {created_str}")
            else:
                click.echo("  Created: N/A")
        click.echo("")
    finally:
        db.close()


def _list_from_beads(org_path, status: Optional[str], assignee: Optional[str], show_all: bool) -> None:
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
        args.append("--status=open")

    if assignee:
        args.append(f"--assignee={assignee}")
    if show_all:
        args.append("--all")

    result = _helpers.run_bd(
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

    try:
        okrs = json.loads(result.stdout)
    except json.JSONDecodeError:
        click.echo("No OKRs found.")
        return

    if not okrs:
        click.echo("No OKRs found.")
        return

    for okr in okrs:
        click.echo("")
        click.echo("=" * 60)
        click.echo(f"OKR: {okr.get('title', 'Untitled')}")
        click.echo("=" * 60)
        click.echo(f"  ID: {okr.get('id', 'N/A')}")
        click.echo(f"  Status: {okr.get('status', 'N/A')}")
        click.echo(f"  Priority: P{okr.get('priority', 2)}")

        assignee_val = okr.get("assignee")
        if assignee_val:
            click.echo(f"  Owner: {assignee_val}")

        desc = okr.get("description", "")
        if desc:
            click.echo(f"  Description: {desc.strip()[:100]}...")

        labels = okr.get("labels", [])
        if labels:
            click.echo(f"  Labels: {', '.join(labels)}")

        created = okr.get("created_at", "")
        if created:
            click.echo(f"  Created: {created[:10]}")

    click.echo("")
