"""
qn org demote command.

Remove a worker's management authority (not the worker themselves).
"""

from typing import Optional

import click

from commands.context import pass_context, Context
from core.db import open_database, get_org_db_path
from core.worker import Worker
from core.queries import (
    get_worker_by_name,
    get_delegations_by_delegator,
)
from shared.exceptions import DelegationNotFoundError


@click.command("demote")
@click.argument("worker")
@click.option(
    "--by",
    "demoter_name",
    default=None,
    help="Who is authorizing the demotion (defaults to worker's manager).",
)
@click.option(
    "--reason",
    type=str,
    default="Demoted",
    help="Reason for audit trail.",
)
@click.option(
    "--cascade",
    is_flag=True,
    help="Also revoke from workers delegated by target.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation prompts.",
)
@pass_context
def demote_cmd(
    ctx: Context,
    worker: str,
    demoter_name: Optional[str],
    reason: str,
    cascade: bool,
    force: bool,
):
    """Remove a worker's management authority.

    The worker remains in the organization as an individual contributor.
    This is different from 'qn org fire' which terminates the worker.

    \b
    Examples:
      qn org demote alice --reason "Returning to IC role"
      qn org demote bob --cascade
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
        # Find worker
        worker_data = get_worker_by_name(db, worker)
        if not worker_data:
            raise click.ClickException(f"Worker '{worker}' not found.")

        target = Worker(db, worker_data.id)

        # Check if worker has authority
        if not target.hiring_authority_scope.allowed_roles:
            raise click.ClickException(
                f"Worker '{target.name}' has no management authority to revoke."
            )

        # Find demoter (default to worker's manager)
        if demoter_name:
            demoter_data = get_worker_by_name(db, demoter_name)
            if not demoter_data:
                raise click.ClickException(
                    f"Demoter '{demoter_name}' not found."
                )
            demoter = Worker(db, demoter_data.id)
        else:
            if target.manager_id:
                demoter = Worker(db, target.manager_id)
            else:
                # Worker has no manager (probably CEO)
                cursor = db.execute("SELECT id FROM workers WHERE role = 'CEO' LIMIT 1")
                ceo_row = cursor.fetchone()
                if not ceo_row:
                    raise click.ClickException("No manager found for worker.")
                demoter = Worker(db, ceo_row[0])

        # Check for direct reports
        cursor = db.execute(
            "SELECT COUNT(*) FROM workers WHERE manager_id = ? AND lifecycle_status != 'terminated'",
            (target.id,)
        )
        direct_reports_count = cursor.fetchone()[0]

        if direct_reports_count > 0:
            click.echo(
                f"\nWARNING: {target.name} has {direct_reports_count} direct report(s)."
            )
            click.echo(
                "Demotion will leave these workers without a manager."
            )
            click.echo(
                "\nConsider reassigning reports first using 'qn org fire --reassign'."
            )
            if not force:
                if not click.confirm("\nProceed anyway?"):
                    click.echo("Demotion cancelled.")
                    return

        # Check for downstream delegations
        downstream = get_delegations_by_delegator(db, target.id)
        if downstream and not cascade:
            click.echo(
                f"\n{target.name} has delegated authority to {len(downstream)} worker(s):"
            )
            for grant in downstream:
                delegate = Worker(db, grant.delegate_id)
                click.echo(f"  - {delegate.name} ({delegate.role})")

            click.echo(
                "\nCannot demote without handling downstream delegations."
            )
            click.echo("\nOptions:")
            click.echo("  1) Cancel - make no changes")
            click.echo(
                f"  2) Cascade - revoke {target.name} + {len(downstream)} downstream "
                f"worker{'s' if len(downstream) > 1 else ''}"
            )

            if not force:
                choice = click.prompt(
                    "\nEnter choice",
                    type=click.Choice(["1", "2"]),
                    default="1"
                )
                if choice == "1":
                    click.echo("Demotion cancelled.")
                    return
                elif choice == "2":
                    cascade = True
            else:
                raise click.ClickException(
                    f"Worker '{target.name}' has {len(downstream)} active delegations. "
                    "Use --cascade to revoke all downstream authority."
                )

        # Show preview
        click.echo(f"\nDemoting {target.name}...")
        click.echo(f"\nWorker: {target.name} ({target.role})")
        click.echo(f"  Current authority: {', '.join(target.hiring_authority_scope.allowed_roles)}")
        click.echo(f"  Will become: Individual Contributor (no hiring authority)")
        click.echo(f"  Authorized by: {demoter.name}")
        click.echo(f"  Reason: {reason}")

        if cascade and downstream:
            click.echo(f"\nCascade demotion will affect {len(downstream) + 1} worker(s):")
            click.echo(f"  - {target.name}")
            for grant in downstream:
                delegate = Worker(db, grant.delegate_id)
                click.echo(f"  - {delegate.name}")

        # Confirm (unless --force)
        if not force:
            if cascade and downstream:
                msg = f"\nWARNING: This will revoke authority from {len(downstream) + 1} worker(s).\n\nProceed?"
            else:
                msg = "\nProceed?"

            if not click.confirm(msg):
                click.echo("Demotion cancelled.")
                return

        # Perform demotion (revoke authority)
        try:
            target.revoke_authority(
                cascade=cascade,
                reason=f"Demoted: {reason}",
            )

            revoked_count = 1 + (len(downstream) if cascade else 0)

            click.echo("\nDemotion complete.")
            click.echo(
                f"{target.name} is now an individual contributor."
            )
            click.echo(f"Authority revoked from {revoked_count} worker(s).")

            if cascade and downstream:
                click.echo("\nAffected workers:")
                click.echo(f"  - {target.name}")
                for grant in downstream:
                    delegate = Worker(db, grant.delegate_id)
                    click.echo(f"  - {delegate.name}")

            if direct_reports_count > 0:
                click.echo(
                    f"\nNote: {target.name} still has {direct_reports_count} direct report(s). "
                    "They remain in the org but should be reassigned."
                )

        except DelegationNotFoundError as e:
            raise click.ClickException(f"Delegation not found: {e}")
        except Exception as e:
            raise click.ClickException(f"Demotion failed: {e}")

    finally:
        db.close()
