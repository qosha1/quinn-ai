"""
qn org stop command.
"""

import click

from commands.main import pass_context


@click.command()
@pass_context
def stop_cmd(ctx):
    """Stop the organization.

    Gracefully stops all worker sessions and transitions org to stopped state.
    """
    # TODO: Implement
    click.echo("qn org stop - not yet implemented")
