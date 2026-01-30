"""
qn org init command.
"""

from pathlib import Path

import click

from commands.context import pass_context, Context
from core.org_init import OrgInitConfig, init_org


@click.command()
@click.option(
    "--ceo-name",
    default="CEO",
    help="Name for the CEO worker.",
)
@click.option(
    "--ceo-role",
    default="CEO",
    help="Role title for the CEO.",
)
@pass_context
def init_cmd(ctx: Context, ceo_name: str, ceo_role: str):
    """Initialize a new organization.

    Creates the org folder structure, copies default config templates,
    initializes the database, and creates the CEO worker.
    """
    org_path = ctx.org_path

    # Create config for initialization
    config = OrgInitConfig(
        path=org_path,
        name=org_path.name,
        ceo_name=ceo_name,
        ceo_role=ceo_role,
    )

    # Initialize the org
    result = init_org(config)

    if not result.success:
        raise click.ClickException(result.error or "Failed to initialize organization")

    click.echo(f"Initialized organization at {result.org_path}")
    click.echo(f"Created CEO: {result.ceo_name} ({result.ceo_role})")
    click.echo(f"Database: {result.db_path}")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  1. Configure providers in config/providers.yaml")
    click.echo("  2. Run 'qn org start' to start the organization")
