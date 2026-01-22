"""
qn wrkr get-work command.
"""

import os

import click

from commands.main import pass_context


@click.command()
@pass_context
def get_work_cmd(ctx):
    """Get next work item.

    Returns the next bead assigned to this worker, sorted by priority.
    """
    worker_id = os.environ.get("QUINN_WORKER_ID")
    if not worker_id:
        raise click.ClickException(
            "QUINN_WORKER_ID environment variable not set"
        )

    # TODO: Implement
    click.echo("qn wrkr get-work - not yet implemented")
