"""
qn org status command.
"""

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org


@click.command()
@pass_context
def status_cmd(ctx: Context):
    """Show organization status.

    Displays org lifecycle state, worker count, and session count.
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
        org = Org.load(db)

        click.echo(f"Organization: {org_path}")
        click.echo(f"Status: {org.status}")
        click.echo("")

        # Count workers with hiring authority
        cursor = db.execute("""
            SELECT COUNT(*) FROM workers
            WHERE status != 'terminated'
            AND hiring_authority_scope IS NOT NULL
            AND hiring_authority_scope != '{}'
            AND hiring_authority_scope != '{"allowed_roles": []}'
        """)
        managers_count = cursor.fetchone()[0]

        # Worker stats
        click.echo("Workers:")
        click.echo(f"  Total: {org.worker_count}")
        click.echo(f"  Active: {org.active_worker_count}")
        click.echo(f"  Sessions: {org.active_session_count}")
        if managers_count > 0:
            click.echo(f"  Managers: {managers_count}")

        # CEO info
        if org.ceo:
            click.echo("")
            click.echo("CEO:")
            click.echo(f"  Name: {org.ceo.name}")
            click.echo(f"  Role: {org.ceo.role}")
            click.echo(f"  Lifecycle: {org.ceo.lifecycle_status}")
            if org.ceo.runtime_status:
                click.echo(f"  Runtime: {org.ceo.runtime_status}")

            # Show CEO's hiring authority
            scope = org.ceo.hiring_authority_scope
            if scope.allowed_roles:
                if "*" in scope.allowed_roles:
                    click.echo("  Authority: Full (all roles)")
                else:
                    click.echo(f"  Authority: {', '.join(scope.allowed_roles)}")

        # Timestamps
        if org.started_at:
            click.echo("")
            click.echo(f"Started: {org.started_at}")
        if org.stopped_at:
            click.echo(f"Stopped: {org.stopped_at}")

    finally:
        db.close()
