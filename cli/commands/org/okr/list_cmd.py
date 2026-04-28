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
        hidden=True,
        help="(deprecated) Same as default — both views are now merged.",
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

        Shows objective title, status, owner, key results, and progress
        in a single unified view. Beads is the canonical source for
        status/labels/assignee; the SQLite mirror provides key results
        and progress data.

        \b
        Examples:
          qn org okr list                    # List open OKRs (merged view)
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

        _list_unified(org_path, db_path, status, assignee, show_all)

    return list_cmd


def _list_unified(
    org_path,
    db_path,
    status: Optional[str],
    assignee: Optional[str],
    show_all: bool,
) -> None:
    """Unified OKR list: beads for canonical metadata + filters, db for KRs + progress.

    For each beads OKR, look up the SQLite mirror by id; if present, layer
    in key results and progress. If the mirror is missing (legacy/unsynced
    OKR), display beads-only fields with no KR section.
    """
    from cli.core.queries import get_okr

    beads_okrs = _fetch_beads_okrs(org_path, status, assignee, show_all)

    if not beads_okrs:
        click.echo("No OKRs found.")
        return

    db = open_database(db_path)
    try:
        for beads_okr in beads_okrs:
            okr_id = beads_okr.get("id")
            db_okr = get_okr(db, okr_id) if okr_id else None
            _render_okr(beads_okr, db_okr)
    finally:
        db.close()

    click.echo("")


def _fetch_beads_okrs(
    org_path,
    status: Optional[str],
    assignee: Optional[str],
    show_all: bool,
) -> list:
    """Query beads for OKR ids/metadata. Returns list of dicts (possibly empty)."""
    args = ["list", "--label=okr", "--json"]

    if status:
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
            return []
        raise click.ClickException(
            f"Failed to list OKRs: {result.stderr}\n"
            "Ensure beads is properly configured for this organization."
        )

    try:
        return json.loads(result.stdout) or []
    except json.JSONDecodeError:
        return []


def _render_okr(beads_okr: dict, db_okr) -> None:
    """Render one OKR block, preferring db_okr fields when available."""
    title = beads_okr.get("title") or (db_okr.title if db_okr else "Untitled")

    # Status: prefer the OKR-specific db status (active/completed/draft/cancelled).
    # Fall back to beads issue status (open/closed) when the mirror is missing.
    status_val = db_okr.status if db_okr else beads_okr.get("status", "N/A")

    owner = beads_okr.get("assignee") or (db_okr.owner_worker_id if db_okr else None)
    description = (db_okr.description if db_okr and db_okr.description else
                   beads_okr.get("description", ""))
    priority = beads_okr.get("priority", 2)
    labels = beads_okr.get("labels", [])
    created = beads_okr.get("created_at", "")

    click.echo("")
    click.echo("=" * 60)
    click.echo(f"OKR: {title}")
    click.echo("=" * 60)
    click.echo(f"  ID: {beads_okr.get('id', 'N/A')}")
    click.echo(f"  Status: {status_val}")
    click.echo(f"  Priority: P{priority}")
    if owner:
        click.echo(f"  Owner: {owner}")
    if description:
        click.echo(f"  Description: {description.strip()[:100]}...")
    if labels:
        click.echo(f"  Labels: {', '.join(labels)}")

    if db_okr and db_okr.key_results:
        click.echo("  Key Results:")
        for kr in db_okr.key_results:
            progress = kr.progress()
            icon = "✓" if kr.is_met() else "○"
            click.echo(
                f"    {icon} {kr.metric}: {kr.current}/{kr.target} {kr.unit} ({progress:.0f}%)"
            )
        click.echo(f"  Overall Progress: {db_okr.progress():.0f}%")

    if db_okr and db_okr.due_date:
        click.echo(f"  Due: {db_okr.due_date}")

    if created:
        click.echo(f"  Created: {created[:10]}")
