"""
qn org start command.
"""

import click

from commands.main import pass_context


@click.command()
@pass_context
def start_cmd(ctx):
    """Start the organization.

    Transitions org to running state and spawns CEO session.
    """
    # TODO: Implement
    click.echo("qn org start - not yet implemented")
