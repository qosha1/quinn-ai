"""
qn org delegations command.

View delegation chains and authority grants.
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import (
    get_worker_by_name,
    get_delegation_audit,
    get_delegation_chain,
)


def _parse_dt(value) -> datetime:
    """Parse a datetime value that may be a string or datetime object."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Handle ISO format with or without microseconds
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    raise ValueError(f"Cannot parse datetime: {value!r}")


def format_delegation_tree(db, root_id: str, prefix: str = "", is_last: bool = True) -> List[str]:
    """Recursively format delegation tree with ASCII art."""
    from cli.core.queries import get_delegations_by_delegator

    lines = []
    worker = Worker(db, root_id)

    # Format current worker
    scope = worker.hiring_authority_scope
    if scope.allowed_roles:
        if "*" in scope.allowed_roles:
            roles_str = "all roles"
        else:
            roles_str = ",".join(scope.allowed_roles)
        budget_str = f"budget {worker.delegated_budget}" if worker.delegated_budget else "budget unlimited"
        info = f"{worker.name} ({worker.role}) [{roles_str}, cost {scope.max_cost}, {budget_str}]"
    else:
        info = f"{worker.name} ({worker.role}) [no authority]"

    lines.append(f"{prefix}{info}")

    # Get children (workers delegated by this worker)
    delegations = get_delegations_by_delegator(db, worker.id)

    for i, grant in enumerate(delegations):
        is_last_child = (i == len(delegations) - 1)
        child_prefix = prefix + ("    " if is_last else "│   ")
        connector = "└── " if is_last_child else "├── "

        child_lines = format_delegation_tree(
            db,
            grant.delegate_id,
            prefix=child_prefix + connector,
            is_last=is_last_child
        )

        # First line already has connector, rest need continuation
        lines.append(child_lines[0])
        for line in child_lines[1:]:
            lines.append(line)

    return lines


@click.command("delegations")
@click.option(
    "--worker",
    type=str,
    help="Show delegations for specific worker.",
)
@click.option(
    "--tree",
    is_flag=True,
    help="Display as ASCII tree.",
)
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Output as JSON.",
)
@click.option(
    "--include-revoked",
    is_flag=True,
    help="Include revoked delegations in output.",
)
@pass_context
def delegations_cmd(
    ctx: Context,
    worker: Optional[str],
    tree: bool,
    json_output: bool,
    include_revoked: bool,
):
    """View hiring authority delegations.

    Shows who has hiring authority and who delegated it to them.
    Use --tree for a hierarchical view of the delegation chain.

    \b
    Examples:
      qn org delegations
      qn org delegations --worker alice
      qn org delegations --tree
      qn org delegations --json-output
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
        if worker:
            # Show specific worker's delegation chain
            worker_data = get_worker_by_name(db, worker)
            if not worker_data:
                raise click.ClickException(f"Worker '{worker}' not found.")

            target = Worker(db, worker_data.id)

            if json_output:
                # JSON output for worker
                from cli.core.queries import get_delegations_by_delegator, get_delegation_grant

                grant = get_delegation_grant(db, target.id)
                downstream = get_delegations_by_delegator(db, target.id)

                output = {
                    "worker": {
                        "id": target.id,
                        "name": target.name,
                        "role": target.role,
                    },
                    "authority": {
                        "allowed_roles": list(target.hiring_authority_scope.allowed_roles),
                        "max_cost": target.hiring_authority_scope.max_cost,
                        "budget": target.delegated_budget,
                        "max_reports": target.max_reports,
                    },
                    "delegated_by": None,
                    "delegated_to": [],
                }

                if grant:
                    delegator = Worker(db, grant.delegator_id)
                    output["delegated_by"] = {
                        "id": delegator.id,
                        "name": delegator.name,
                        "granted_at": _parse_dt(grant.granted_at).isoformat(),
                    }

                for d in downstream:
                    delegate = Worker(db, d.delegate_id)
                    output["delegated_to"].append({
                        "id": delegate.id,
                        "name": delegate.name,
                        "role": delegate.role,
                        "granted_at": _parse_dt(d.granted_at).isoformat(),
                    })

                click.echo(json.dumps(output, indent=2))
                return

            # Text output for worker
            click.echo(f"\nDELEGATION CHAIN: {target.name}\n")
            click.echo(f"{target.name} ({target.role})")

            # Show who delegated to this worker
            from cli.core.queries import get_delegation_grant
            grant = get_delegation_grant(db, target.id)
            if grant:
                delegator = Worker(db, grant.delegator_id)
                click.echo(f"  Delegated by: {delegator.name} ({_parse_dt(grant.granted_at).strftime('%Y-%m-%d %H:%M:%S')})")
            else:
                click.echo("  Delegated by: None (root authority)")

            # Show authority
            scope = target.hiring_authority_scope
            if scope.allowed_roles:
                if "*" in scope.allowed_roles:
                    click.echo("  Can hire: all roles")
                else:
                    click.echo(f"  Can hire: {', '.join(scope.allowed_roles)}")
                click.echo(f"  Max cost: {scope.max_cost}")
                click.echo(f"  Budget: {target.delegated_budget}")
                click.echo(f"  Max reports: {target.max_reports}")
            else:
                click.echo("  Authority: None")

            # Show downstream delegations
            from cli.core.queries import get_delegations_by_delegator
            downstream = get_delegations_by_delegator(db, target.id)
            if downstream:
                click.echo(f"\n  Delegated to:")
                for d in downstream:
                    delegate = Worker(db, d.delegate_id)
                    click.echo(
                        f"    {delegate.name} ({delegate.role}) - "
                        f"{_parse_dt(d.granted_at).strftime('%Y-%m-%d %H:%M:%S')}"
                    )
            else:
                click.echo("\n  Delegated to: None")

        elif tree:
            # Show full delegation tree
            click.echo("\nDELEGATION TREE\n")

            # Find CEO as root
            cursor = db.execute("SELECT id FROM workers WHERE role = 'CEO' LIMIT 1")
            ceo_row = cursor.fetchone()
            if not ceo_row:
                click.echo("No CEO found in organization.")
                return

            tree_lines = format_delegation_tree(db, ceo_row[0])
            for line in tree_lines:
                click.echo(line)

        else:
            # List all delegations
            from cli.core.queries import get_delegation_audit

            audit_records = get_delegation_audit(db)

            if include_revoked:
                # Show all records including revoked
                active = [r for r in audit_records if r.event_type == "granted"]
                revoked = [r for r in audit_records if r.event_type in ("revoked", "cascade_revoked", "terminated_revoked")]

                if json_output:
                    output = {
                        "active": [],
                        "revoked": [],
                    }

                    for record in active:
                        delegator = Worker(db, record.delegator_id)
                        delegate = Worker(db, record.delegate_id)
                        output["active"].append({
                            "delegator": delegator.name,
                            "delegate": delegate.name,
                            "granted_at": _parse_dt(record.timestamp).isoformat(),
                        })

                    for record in revoked:
                        delegator = Worker(db, record.delegator_id)
                        delegate = Worker(db, record.delegate_id)
                        output["revoked"].append({
                            "delegator": delegator.name,
                            "delegate": delegate.name,
                            "revoked_at": _parse_dt(record.timestamp).isoformat(),
                            "reason": record.reason,
                        })

                    click.echo(json.dumps(output, indent=2))
                    return

                click.echo(f"\nDELEGATIONS ({len(active)} active, {len(revoked)} revoked)\n")
                click.echo(
                    f"{'Delegator':<15} {'Delegate':<15} {'Status':<10} {'Date':<20}"
                )
                click.echo("-" * 65)

                for record in active:
                    delegator = Worker(db, record.delegator_id)
                    delegate = Worker(db, record.delegate_id)
                    click.echo(
                        f"{delegator.name:<15} {delegate.name:<15} "
                        f"{'active':<10} {_parse_dt(record.timestamp).strftime('%Y-%m-%d %H:%M:%S')}"
                    )

                for record in revoked:
                    delegator = Worker(db, record.delegator_id)
                    delegate = Worker(db, record.delegate_id)
                    click.echo(
                        f"{delegator.name:<15} {delegate.name:<15} "
                        f"{'revoked':<10} {_parse_dt(record.timestamp).strftime('%Y-%m-%d %H:%M:%S')}"
                    )

            else:
                # Show only active delegations
                from cli.core.queries import get_delegations_by_delegator

                # Get all workers with authority
                cursor = db.execute("""
                    SELECT id FROM workers
                    WHERE hiring_authority_scope IS NOT NULL
                    AND hiring_authority_scope != '{}'
                    AND hiring_authority_scope != '{"allowed_roles": []}'
                    AND status != 'terminated'
                """)
                workers_with_authority = cursor.fetchall()

                all_grants = []
                for (worker_id,) in workers_with_authority:
                    from cli.core.queries import get_delegation_grant
                    grant = get_delegation_grant(db, worker_id)
                    if grant:
                        all_grants.append(grant)

                if json_output:
                    output = []
                    for grant in all_grants:
                        delegator = Worker(db, grant.delegator_id)
                        delegate = Worker(db, grant.delegate_id)
                        output.append({
                            "delegator": delegator.name,
                            "delegate": delegate.name,
                            "granted_at": _parse_dt(grant.granted_at).isoformat(),
                        })
                    click.echo(json.dumps(output, indent=2))
                    return

                click.echo(f"\nDELEGATIONS ({len(all_grants)} active)\n")

                if not all_grants:
                    click.echo("No active delegations found.")
                    return

                click.echo(
                    f"{'Delegator':<15} {'Delegate':<15} {'Granted':<20}"
                )
                click.echo("-" * 55)

                for grant in all_grants:
                    delegator = Worker(db, grant.delegator_id)
                    delegate = Worker(db, grant.delegate_id)
                    click.echo(
                        f"{delegator.name:<15} {delegate.name:<15} "
                        f"{_parse_dt(grant.granted_at).strftime('%Y-%m-%d %H:%M:%S')}"
                    )

    finally:
        db.close()
