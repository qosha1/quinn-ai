"""
qn org promote command.

Promote a worker to a management position with hiring authority.
"""

from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_worker_by_name
from cli.core.constants import DELEGATION_PRESETS
from shared.exceptions import CircularDelegationError, ConcurrentModificationError


@click.command("promote")
@click.argument("worker")
@click.option(
    "--to",
    "level",
    required=True,
    type=click.Choice(["team-lead", "director", "vp"], case_sensitive=False),
    help="Target management level.",
)
@click.option(
    "--by",
    "promoter_name",
    default=None,
    help="Who is authorizing the promotion (defaults to worker's manager).",
)
@click.option(
    "--reason",
    type=str,
    default="Promoted",
    help="Reason for audit trail.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation prompts.",
)
@pass_context
def promote_cmd(
    ctx: Context,
    worker: str,
    level: str,
    promoter_name: Optional[str],
    reason: str,
    force: bool,
):
    """Promote a worker to a management position.

    Grants hiring authority based on the target level. This is a
    convenience command that calls delegate-authority internally.

    \b
    Examples:
      qn org promote alice --to team-lead
      qn org promote bob --to director --reason "Team expansion"
      qn org promote carol --to vp --by ceo
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
        # Find worker to promote
        worker_data = get_worker_by_name(db, worker)
        if not worker_data:
            raise click.ClickException(f"Worker '{worker}' not found.")

        target = Worker(db, worker_data["id"])

        # Find promoter (default to worker's manager)
        if promoter_name:
            promoter_data = get_worker_by_name(db, promoter_name)
            if not promoter_data:
                raise click.ClickException(
                    f"Promoter '{promoter_name}' not found."
                )
            promoter = Worker(db, promoter_data["id"])
        else:
            if target.manager_id:
                promoter = Worker(db, target.manager_id)
            else:
                # Worker has no manager (probably CEO)
                cursor = db.execute("SELECT id FROM workers WHERE role = 'CEO' LIMIT 1")
                ceo_row = cursor.fetchone()
                if not ceo_row:
                    raise click.ClickException("No manager found for worker.")
                promoter = Worker(db, ceo_row[0])

        # Get preset for level
        preset = DELEGATION_PRESETS.get(level)
        if not preset:
            raise click.ClickException(
                f"Unknown level '{level}'. "
                f"Valid levels: {', '.join(DELEGATION_PRESETS.keys())}"
            )

        allowed_roles = preset["allowed_roles"]
        max_cost = preset["max_cost"]
        budget = preset["budget"]
        max_reports = preset.get("max_reports", 5)

        # Check if already has authority at or above this level
        current_scope = target.hiring_authority_scope
        if current_scope.allowed_roles:
            # Simple check: if they have "*" or equal/higher max_cost, they're already at/above level
            if "*" in current_scope.allowed_roles or current_scope.max_cost >= max_cost:
                if not force:
                    click.echo(
                        f"\nWARNING: {target.name} already has authority at or above '{level}' level."
                    )
                    click.echo(f"  Current max_cost: {current_scope.max_cost}")
                    click.echo(f"  Target max_cost: {max_cost}")
                    if not click.confirm("\nProceed anyway?"):
                        click.echo("Promotion cancelled.")
                        return

        # Show preview
        click.echo(f"\nPromoting {target.name} to {level}...")
        click.echo(f"\nWorker: {target.name} ({target.role})")
        if current_scope.allowed_roles:
            click.echo(f"  Current authority: {', '.join(current_scope.allowed_roles)}")
        else:
            click.echo("  Current authority: None")
        click.echo(f"  New authority:")
        click.echo(f"    Level: {level}")
        click.echo(f"    Allowed roles: {', '.join(allowed_roles)}")
        click.echo(f"    Max cost: {max_cost}")
        click.echo(f"    Hiring budget: {budget}")
        click.echo(f"    Max reports: {max_reports}")
        click.echo(f"\nAuthorized by: {promoter.name}")

        # Confirm (unless --force)
        if not force:
            if not click.confirm("\nProceed?"):
                click.echo("Promotion cancelled.")
                return

        # Perform delegation (promotion)
        try:
            promoter.delegate_authority(
                delegate_id=target.id,
                allowed_roles=allowed_roles,
                max_cost=max_cost,
                delegated_budget=budget,
                max_reports=max_reports,
                reason=f"Promoted to {level}: {reason}",
            )

            click.echo("\nPromotion complete.")
            click.echo(
                f"\n{target.name} is now a {level} with hiring authority:"
            )
            click.echo(f"  - Roles: {', '.join(allowed_roles)}")
            click.echo(f"  - Max cost: {max_cost}")
            click.echo(f"  - Direct reports limit: {max_reports}")
            click.echo(f"  - Hiring budget: {budget}")

            click.echo("\nNext steps:")
            click.echo(f"  qn org hire --name <name> --role <role> --manager {target.name}")
            click.echo(f"  qn org delegations --worker {target.name}")

        except CircularDelegationError as e:
            raise click.ClickException(f"Circular delegation detected: {e}")
        except ConcurrentModificationError as e:
            raise click.ClickException(
                f"Concurrent modification detected: {e}\n"
                "Another process modified this worker. Please try again."
            )
        except Exception as e:
            raise click.ClickException(f"Promotion failed: {e}")

    finally:
        db.close()
