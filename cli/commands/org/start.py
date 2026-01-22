"""
qn org start command.
"""

import click

from cli.commands.main import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from shared import InvalidOrgTransition


@click.command()
@pass_context
def start_cmd(ctx: Context):
    """Start the organization.

    Transitions org to running state. If starting from initialized state,
    also activates the CEO worker.
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

        if org.status == "running":
            click.echo("Organization is already running.")
            return

        try:
            org.start()
        except InvalidOrgTransition as e:
            raise click.ClickException(str(e))

        click.echo(f"Organization started at {org_path}")
        click.echo(f"Status: {org.status}")

        if org.ceo:
            click.echo(f"CEO: {org.ceo.name} ({org.ceo.lifecycle_status})")

    finally:
        db.close()
