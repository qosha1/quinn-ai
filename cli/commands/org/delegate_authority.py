"""
qn org delegate-authority command.

Grant hiring authority to a direct report.
"""

import json
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import get_worker_by_name
from cli.core.constants import DELEGATION_PRESETS
from shared.exceptions import (
    CircularDelegationError,
    ConcurrentModificationError,
    WorkerNotFound,
)


@click.command("delegate-authority")
@click.option(
    "--to",
    "delegate_name",
    required=True,
    help="Worker to delegate authority to (name or ID).",
)
@click.option(
    "--from",
    "delegator_name",
    default=None,
    help="Delegator worker (defaults to CEO).",
)
@click.option(
    "--level",
    type=click.Choice(["team-lead", "director", "vp"], case_sensitive=False),
    help="Preset authority level.",
)
@click.option(
    "--roles",
    type=str,
    help="Comma-separated allowed roles (e.g., 'engineer,analyst').",
)
@click.option(
    "--max-cost",
    type=int,
    help="Maximum cost per hire (0-100).",
)
@click.option(
    "--budget",
    type=int,
    help="Total hiring budget to delegate.",
)
@click.option(
    "--max-reports",
    type=int,
    help="Maximum direct reports allowed.",
)
@click.option(
    "--copy-from",
    type=str,
    help="Copy authority from another worker.",
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
def delegate_authority_cmd(
    ctx: Context,
    delegate_name: str,
    delegator_name: Optional[str],
    level: Optional[str],
    roles: Optional[str],
    max_cost: Optional[int],
    budget: Optional[int],
    max_reports: Optional[int],
    copy_from: Optional[str],
    force: bool,
    dry_run: bool,
):
    """Grant hiring authority to a direct report.

    Allows the target worker to hire new workers within the specified
    constraints. The delegator (manager) must have sufficient authority
    to grant the requested scope.

    \b
    Examples:
      qn org delegate-authority --to alice --level team-lead
      qn org delegate-authority --to bob --roles "engineer,qa" --max-cost 40
      qn org delegate-authority --from ceo --to carol --level director
      qn org delegate-authority --to dave --copy-from alice
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Validate: must specify one of --level, --roles, or --copy-from
    spec_count = sum([level is not None, roles is not None, copy_from is not None])
    if spec_count == 0:
        raise click.ClickException(
            "Must specify one of: --level, --roles, or --copy-from"
        )
    if spec_count > 1:
        raise click.ClickException(
            "Cannot combine --level, --roles, and --copy-from. Choose one."
        )

    db = open_database(db_path)

    try:
        # Find delegate worker
        delegate_data = get_worker_by_name(db, delegate_name)
        if not delegate_data:
            raise click.ClickException(
                f"Worker '{delegate_name}' not found. "
                "Use 'qn org status' to see available workers."
            )

        delegate = Worker(db, delegate_data["id"])

        # Find delegator (default to CEO if not specified)
        if delegator_name:
            delegator_data = get_worker_by_name(db, delegator_name)
            if not delegator_data:
                raise click.ClickException(
                    f"Delegator '{delegator_name}' not found."
                )
            delegator = Worker(db, delegator_data["id"])
        else:
            # Find CEO
            cursor = db.execute("SELECT id FROM workers WHERE role = 'CEO' LIMIT 1")
            ceo_row = cursor.fetchone()
            if not ceo_row:
                raise click.ClickException("No CEO found in organization.")
            delegator = Worker(db, ceo_row[0])

        # Determine delegation scope
        if level:
            # Use preset
            preset = DELEGATION_PRESETS.get(level)
            if not preset:
                raise click.ClickException(
                    f"Unknown delegation level '{level}'. "
                    f"Valid levels: {', '.join(DELEGATION_PRESETS.keys())}"
                )
            allowed_roles = preset["allowed_roles"]
            final_max_cost = preset["max_cost"]
            final_budget = preset["budget"]
            final_max_reports = preset.get("max_reports", 5)

        elif roles:
            # Custom role-based
            allowed_roles = [r.strip() for r in roles.split(",")]
            final_max_cost = max_cost or 50
            final_budget = budget or 100
            final_max_reports = max_reports or 5

        elif copy_from:
            # Copy from another worker
            source_data = get_worker_by_name(db, copy_from)
            if not source_data:
                raise click.ClickException(
                    f"Source worker '{copy_from}' not found."
                )
            source = Worker(db, source_data["id"])
            scope = source.hiring_authority_scope
            if not scope.allowed_roles:
                raise click.ClickException(
                    f"Worker '{copy_from}' has no hiring authority to copy."
                )
            allowed_roles = scope.allowed_roles
            final_max_cost = scope.max_cost
            final_budget = source.delegated_budget
            final_max_reports = source.max_reports

        else:
            raise click.ClickException("Internal error: no delegation scope specified")

        # Validate cost range
        if final_max_cost < 0 or final_max_cost > 100:
            raise click.ClickException("Max cost must be between 0 and 100.")

        # Show preview
        click.echo(f"\nDelegating authority to {delegate.name}...")
        click.echo(f"\nWorker: {delegate.name} ({delegate.role})")
        if delegate.hiring_authority_scope.allowed_roles:
            click.echo(f"  Current authority: {', '.join(delegate.hiring_authority_scope.allowed_roles)}")
        else:
            click.echo("  Current authority: None")
        click.echo(f"  New authority:")
        click.echo(f"    Allowed roles: {', '.join(allowed_roles)}")
        click.echo(f"    Max cost: {final_max_cost}")
        click.echo(f"    Hiring budget: {final_budget}")
        click.echo(f"    Max reports: {final_max_reports}")
        click.echo(f"\nAuthorized by: {delegator.name}")

        # Check for existing authority
        if delegate.hiring_authority_scope.allowed_roles and not force:
            click.echo(
                f"\nWARNING: {delegate.name} already has hiring authority. "
                "This will overwrite the existing authority."
            )

        # Dry run exit
        if dry_run:
            click.echo("\n[DRY RUN] No changes made.")
            return

        # Confirm (unless --force)
        if not force:
            if not click.confirm("\nProceed?"):
                click.echo("Delegation cancelled.")
                return

        # Perform delegation
        try:
            delegator.delegate_authority(
                delegate_id=delegate.id,
                allowed_roles=allowed_roles,
                max_cost=final_max_cost,
                delegated_budget=final_budget,
                max_reports=final_max_reports,
                reason=f"Delegated via CLI by {delegator.name}",
            )

            click.echo("\nDelegation complete.")
            click.echo(
                f"\n{delegate.name} can now hire workers with:"
            )
            click.echo(f"  - Roles: {', '.join(allowed_roles)}")
            click.echo(f"  - Max cost: {final_max_cost}")
            click.echo(f"  - Direct reports limit: {final_max_reports}")
            click.echo(f"  - Hiring budget: {final_budget}")

            click.echo("\nNext steps:")
            click.echo(f"  qn org hire --name <name> --role <role> --manager {delegate.name}")
            click.echo(f"  qn org delegations --worker {delegate.name}")

        except CircularDelegationError as e:
            raise click.ClickException(f"Circular delegation detected: {e}")
        except ConcurrentModificationError as e:
            raise click.ClickException(
                f"Concurrent modification detected: {e}\n"
                "Another process modified this worker. Please try again."
            )
        except Exception as e:
            raise click.ClickException(f"Delegation failed: {e}")

    finally:
        db.close()
