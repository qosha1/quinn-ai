"""qn org okr {cascade, show, progress, update-kr} — read/inspect OKRs."""

import json
from typing import Optional

import click

from cli.commands.context import Context, pass_context
from cli.core.db import get_org_db_path, open_database

from . import _helpers


def register(okr_group):
    @okr_group.command("cascade")
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
            result = _helpers.run_bd(
                ["dep", "tree", root],
                org_path=org_path,
                capture_output=True,
                skip_permission_check=True,
            )
            if result.returncode != 0:
                raise click.ClickException(
                    f"Failed to show OKR tree: {result.stderr}\n"
                    f"Verify the OKR ID '{root}' is correct."
                )
            click.echo(f"OKR Cascade from {root}:")
            click.echo("=" * 50)
            click.echo(result.stdout)
            return

        # Show full tree
        result = _helpers.run_bd(
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

        children_map: dict[str, list] = {}
        roots = []
        for okr in okrs:
            parent_id = okr.get("parent_id")
            if parent_id:
                children_map.setdefault(parent_id, []).append(okr)
            else:
                roots.append(okr)

        def print_okr(okr: dict, indent: int = 0):
            prefix = "  " * indent
            status = okr.get("status", "open")
            title = okr.get("title", "Untitled")
            okr_id = okr.get("id", "?")
            assignee = okr.get("assignee", "")
            icon = "✓" if status == "closed" else "○" if status == "open" else "▶"
            owner_str = f" ({assignee})" if assignee else ""
            click.echo(f"{prefix}{icon} {okr_id}: {title}{owner_str}")
            for child in children_map.get(okr_id, []):
                print_okr(child, indent + 1)

        for root_okr in roots:
            print_okr(root_okr)
        click.echo("")

    @okr_group.command("show")
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

        result = _helpers.run_bd(
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

        click.echo("")
        click.echo("Work items serving this OKR:")
        click.echo("-" * 40)

        dep_result = _helpers.run_bd(
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

    @okr_group.command("progress")
    @click.argument("okr_id")
    @pass_context
    def progress_cmd(ctx: Context, okr_id: str):
        """Show OKR progress including key results.

        \b
        Example:
          qn org okr progress okr-abc
        """
        from cli.core.queries import get_okr

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
                    icon = "✓" if kr.is_met() else "○"
                    click.echo(
                        f"  {icon} {kr.metric}: {kr.current}/{kr.target} {kr.unit} "
                        f"({progress_pct:.0f}%)"
                    )
                click.echo("")
                click.echo(f"Overall Progress: {okr.progress():.0f}%")
                if okr.all_key_results_met():
                    click.echo("All key results met!")
            else:
                click.echo("No key results defined for this OKR.")
                click.echo(
                    "Add key results with: qn org okr update-kr <okr-id> --metric=... --target=..."
                )
        finally:
            db.close()

    @okr_group.command("update-kr")
    @click.argument("okr_id")
    @click.option("--metric", "-m", required=True, help="Key result metric name")
    @click.option("--current", "-c", type=float, help="Current value (updates existing)")
    @click.option("--target", "-t", type=float, help="Target value (for new key result)")
    @click.option("--unit", "-u", default="count", help="Unit of measurement (default: count)")
    @pass_context
    def update_kr_cmd(
        ctx: Context,
        okr_id: str,
        metric: str,
        current: Optional[float],
        target: Optional[float],
        unit: str,
    ):
        """Update or add a key result for an OKR.

        \b
        Examples:
          qn org okr update-kr okr-abc --metric="test_coverage" --target=80 --unit="%"
          qn org okr update-kr okr-abc --metric="test_coverage" --current=72
          qn org okr update-kr okr-abc --metric="bugs_fixed" --target=10 --current=3 --unit="count"
        """
        from cli.core.queries import (
            add_okr_key_result,
            get_okr,
            update_okr_key_result,
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
            okr = get_okr(db, okr_id)
            if not okr:
                raise click.ClickException(
                    f"OKR '{okr_id}' not found.\n"
                    "Run 'qn org okr list' to see available OKRs."
                )

            existing_kr = next((kr for kr in okr.key_results if kr.metric == metric), None)

            if existing_kr:
                if current is None:
                    raise click.ClickException(
                        f"Key result '{metric}' exists. Use --current to update its value."
                    )
                update_okr_key_result(db, okr_id, metric, current)
                click.echo(
                    f"Updated {metric}: {current}/{existing_kr.target} {existing_kr.unit}"
                )
            else:
                if target is None:
                    raise click.ClickException(
                        f"Key result '{metric}' does not exist. Use --target to create it."
                    )
                initial = current if current is not None else 0.0
                add_okr_key_result(db, okr_id, metric, target, unit, initial)
                click.echo(f"Added key result: {metric} (target: {target} {unit})")

            okr = get_okr(db, okr_id)
            click.echo(f"OKR Progress: {okr.progress():.0f}%")
        finally:
            db.close()

    return cascade_cmd, show_cmd, progress_cmd, update_kr_cmd
