"""
qn org status command.
"""

import click

from commands.main import pass_context


@click.command()
@pass_context
def status_cmd(ctx):
    """Show organization status.

    Displays org lifecycle state, worker count, and session count.
    """
    # TODO: Implement
    click.echo("qn org status - not yet implemented")
