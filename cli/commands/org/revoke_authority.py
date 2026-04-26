"""
qn org revoke-authority command.

Remove hiring authority from a worker.
"""

from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import (
    get_worker_by_name,
    get_delegations_by_delegator,
)
from shared.exceptions import DelegationNotFoundError


@click.command("revoke-authority")
@click.argument("worker")
@click.option(
    "--by",
    "revoker_name",
    default=None,
    help="Who is authorizing the revocation (defaults to worker's manager).",
)
@click.option(
    "--reason",
    type=str,
    default="Authority revoked",
    help="Reason for audit trail.",
)
@click.option(
    "--cascade",
    is_flag=True,
    help="Also revoke from all workers delegated by target.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation prompts.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview changes without applying.",
)
@pass_context
def revoke_authority_cmd(
    ctx: Context,
    worker: str,
    revoker_name: Optional[str],
    reason: str,
    cascade: bool,
    force: bool,
    dry_run: bool,
):
    """Remove hiring authority from a worker.

    By default, revocation is blocked if the worker has delegated authority
    to others. Use --cascade to revoke all downstream authority.

    \b
    Examples:
      qn org revoke-authority alice
      qn org revoke-authority alice --cascade --reason "Team restructure"
      qn org revoke-authority alice --cascade --dry-run
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
                f"Worker '{target.name}' has no hiring authority to revoke."
            )

        # Find revoker (default to worker's manager)
        if revoker_name:
            revoker_data = get_worker_by_name(db, revoker_name)
            if not revoker_data:
                raise click.ClickException(
                    f"Revoker '{revoker_name}' not found."
                )
            revoker = Worker(db, revoker_data.id)
        else:
            if target.manager_id:
                revoker = Worker(db, target.manager_id)
            else:
                # Worker has no manager (probably CEO), only CEO can revoke
                cursor = db.execute("SELECT id FROM workers WHERE role = 'CEO' LIMIT 1")
                ceo_row = cursor.fetchone()
                if not ceo_row:
                    raise click.ClickException("No manager found for worker.")
                revoker = Worker(db, ceo_row[0])

        # Check for downstream delegations
        downstream = get_delegations_by_delegator(db, target.id)
        if downstream and not cascade:
            click.echo(
                f"\n{target.name} has {len(downstream)} active delegation(s):"
            )
            for grant in downstream:
                delegate = Worker(db, grant.delegate_id)
                click.echo(f"  - {delegate.name} ({delegate.role})")

            click.echo(
                "\nCannot revoke without handling downstream delegations."
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
                    click.echo("Revocation cancelled.")
                    return
                elif choice == "2":
                    cascade = True
            else:
                raise click.ClickException(
                    f"Worker '{target.name}' has {len(downstream)} active delegations. "
                    "Use --cascade to revoke all downstream authority."
                )

        # Show preview
        click.echo(f"\nRevoking authority from {target.name}...")
        click.echo(f"\nWorker: {target.name} ({target.role})")
        click.echo(f"  Current authority: {', '.join(target.hiring_authority_scope.allowed_roles)}")
        click.echo(f"  Authorized by: {revoker.name}")
        click.echo(f"  Reason: {reason}")

        if cascade and downstream:
            click.echo(f"\nCascade revocation will affect {len(downstream) + 1} worker(s):")
            click.echo(f"  - {target.name}")
            for grant in downstream:
                delegate = Worker(db, grant.delegate_id)
                click.echo(f"  - {delegate.name}")

        # Dry run exit
        if dry_run:
            click.echo("\n[DRY RUN] No changes made.")
            if cascade and downstream:
                click.echo(
                    f"Would revoke authority from {len(downstream) + 1} worker(s)."
                )
            return

        # Confirm (unless --force)
        if not force:
            if cascade and downstream:
                msg = f"\nWARNING: This will revoke authority from {len(downstream) + 1} worker(s).\n\nProceed?"
            else:
                msg = "\nProceed?"

            if not click.confirm(msg):
                click.echo("Revocation cancelled.")
                return

        # Perform revocation
        try:
            revoker.revoke_authority(
                delegate=target,
                cascade=cascade,
                reason=reason,
            )

            revoked_count = 1 + (len(downstream) if cascade else 0)

            click.echo("\nRevocation complete.")
            click.echo(f"Authority revoked from {revoked_count} worker(s).")

            if cascade and downstream:
                click.echo("\nAffected workers:")
                click.echo(f"  - {target.name}")
                for grant in downstream:
                    delegate = Worker(db, grant.delegate_id)
                    click.echo(f"  - {delegate.name}")

            click.echo(f"\nAudit log updated with reason: {reason}")

        except DelegationNotFoundError as e:
            raise click.ClickException(f"Delegation not found: {e}")
        except Exception as e:
            raise click.ClickException(f"Revocation failed: {e}")

    finally:
        db.close()
