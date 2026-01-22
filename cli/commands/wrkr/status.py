"""
qn wrkr status command.
"""

import os

import click

from commands.main import pass_context


@click.command()
@pass_context
def status_cmd(ctx):
    """Show worker status.

    Displays lifecycle status, runtime status, and current task.
    """
    worker_id = os.environ.get("QUINN_WORKER_ID")
    if not worker_id:
        raise click.ClickException(
            "QUINN_WORKER_ID environment variable not set"
        )

    # TODO: Implement
    click.echo("qn wrkr status - not yet implemented")
