"""
qn org init command.
"""

import click

from commands.main import pass_context


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
def init_cmd(ctx, ceo_name: str, ceo_role: str):
    """Initialize a new organization.

    Creates the org folder structure, initializes the database,
    and creates the CEO worker.
    """
    # TODO: Implement
    click.echo("qn org init - not yet implemented")
