"""
qn org stop command.
"""

import click

from cli.commands.main import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from shared import InvalidOrgTransition


@click.command()
@pass_context
def stop_cmd(ctx: Context):
    """Stop the organization.

    Gracefully stops the organization and transitions to stopped state.
    Worker sessions should be stopped before calling this.
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

        if org.status == "stopped":
            click.echo("Organization is already stopped.")
            return

        if org.status != "running":
            raise click.ClickException(
                f"Cannot stop organization in '{org.status}' state.\n"
                "Organization must be running to stop."
            )

        try:
            org.stop()
        except InvalidOrgTransition as e:
            raise click.ClickException(str(e))

        click.echo(f"Organization stopped at {org_path}")
        click.echo(f"Status: {org.status}")

    finally:
        db.close()
