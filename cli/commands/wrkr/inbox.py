"""
qn wrkr inbox command.
"""

import os

import click

from commands.main import pass_context


@click.command()
@click.option(
    "--unread-only",
    is_flag=True,
    help="Show only unread messages.",
)
@pass_context
def inbox_cmd(ctx, unread_only: bool):
    """View inbox messages.

    Lists messages for this worker, with unread messages first.
    """
    worker_id = os.environ.get("QUINN_WORKER_ID")
    if not worker_id:
        raise click.ClickException(
            "QUINN_WORKER_ID environment variable not set"
        )

    # TODO: Implement
    click.echo("qn wrkr inbox - not yet implemented")
