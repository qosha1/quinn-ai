"""qn org okr {set, add, link, close} — create, link, or finalize OKRs."""

from typing import Optional

import click

from cli.commands.context import Context, pass_context
from cli.core.db import get_org_db_path, open_database

from . import _helpers
from ._helpers import _create_okr


def register(okr_group):
    @okr_group.command("set")
    @click.option("--title", required=True, help="OKR objective title")
    @click.option("--description", "-d", help="OKR description with objective and key results")
    @click.option("--owner", default="ceo", help="Owner/assignee of the OKR (default: ceo)")
    @click.option(
        "--priority",
        "-p",
        type=click.Choice(["0", "1", "2", "3", "4"]),
        default="1",
        help="Priority (0=critical, 1=high, 2=medium, 3=low, 4=backlog)",
    )
    @click.option("--label", "-l", multiple=True, help="Labels to apply (can be used multiple times)")
    @click.option("--due", help="Due date (e.g., +3m, 2025-03-31)")
    @click.option("--parent", help="Parent OKR ID for hierarchy (creates child OKR)")
    @pass_context
    def set_cmd(
        ctx: Context,
        title: str,
        description: Optional[str],
        owner: str,
        priority: str,
        label: tuple,
        due: Optional[str],
        parent: Optional[str],
    ):
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

    @okr_group.command("add")
    @click.option("--title", required=True, help="OKR objective title")
    @click.option("--description", "-d", help="OKR description")
    @click.option("--owner", default="ceo", help="Owner (default: ceo)")
    @click.option("--priority", "-p", type=click.Choice(["0", "1", "2", "3", "4"]), default="1")
    @click.option("--label", "-l", multiple=True, help="Labels")
    @click.option("--due", help="Due date")
    @click.option("--parent", help="Parent OKR ID")
    @pass_context
    def add_cmd(
        ctx: Context,
        title: str,
        description: Optional[str],
        owner: str,
        priority: str,
        label: tuple,
        due: Optional[str],
        parent: Optional[str],
    ):
        """Alias for 'set'. Create a new OKR."""
        _create_okr(ctx, title, description, owner, priority, label, due, parent)

    @okr_group.command("link")
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

        result = _helpers.run_bd(
            ["dep", "add", work_id, okr_id, "--type", "serves"],
            org_path=org_path,
            capture_output=True,
            skip_permission_check=True,
        )

        if result.returncode != 0:
            raise click.ClickException(
                f"Failed to link work item to OKR: {result.stderr}\n"
                f"Verify both '{work_id}' and '{okr_id}' exist."
            )

        click.echo(f"Linked {work_id} -> {okr_id} (serves)")

    @okr_group.command("close")
    @click.argument("okr_id")
    @click.option(
        "--status",
        type=click.Choice(["completed", "cancelled"], case_sensitive=False),
        default="completed",
        help="Final status (default: completed). Use 'cancelled' for OKRs being abandoned.",
    )
    @click.option("--reason", help="Optional close reason (passed to bd close).")
    @pass_context
    def close_cmd(ctx: Context, okr_id: str, status: str, reason: Optional[str]):
        """Close an OKR — updates BOTH the bead and the SQLite mirror.

        Workers expect 'bd close <okr-id>' to work because OKR ids share the
        beads format, but bd close alone leaves the SQLite okrs row stuck on
        'active' (qn-ai-kljb). This command does both: closes the bead AND
        flips the SQLite row's status to completed/cancelled so
        'qn org okr list --from-db' reflects reality.

        \b
        Examples:
          qn org okr close myorg-abc
          qn org okr close myorg-abc --status=cancelled --reason="superseded by Q2 plan"
        """
        from cli.core.queries import get_okr, update_okr_status

        org_path = ctx.org_path
        db_path = get_org_db_path(org_path)

        if not db_path.exists():
            raise click.ClickException(
                f"Organization not initialized at {org_path}\n"
                "Run 'qn org init' first."
            )

        # 1. Close the bead so 'bd list' / 'bd ready' / serves graph see it closed.
        bd_args = ["close", okr_id]
        if reason:
            bd_args += ["--reason", reason]
        result = _helpers.run_bd(
            bd_args,
            org_path=org_path,
            capture_output=True,
            skip_permission_check=True,
        )
        if result.returncode != 0:
            raise click.ClickException(
                f"Failed to close OKR bead {okr_id!r}: {result.stderr.strip()}\n"
                "Use 'qn org okr list' to see available OKRs."
            )

        # 2. Mirror to the SQLite okrs table so qn-side queries reflect closure.
        # Tolerate missing mirror row (legacy OKRs created via direct bd) — the
        # bead-close above is the source of truth.
        db = open_database(db_path)
        try:
            if get_okr(db, okr_id) is not None:
                update_okr_status(db, okr_id, status.lower())
        finally:
            db.close()

        click.echo(f"Closed OKR {okr_id} ({status.lower()}).")

    return set_cmd, add_cmd, link_cmd, close_cmd
