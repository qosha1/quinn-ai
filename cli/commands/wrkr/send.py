"""
qn wrkr send command.
"""

import os

import click

from commands.main import pass_context


@click.command()
@click.option(
    "--to",
    "to_channel",
    required=True,
    help="Channel or worker to send to.",
)
@click.argument("message")
@pass_context
def send_cmd(ctx, to_channel: str, message: str):
    """Send a message.

    Sends a message to the specified channel or worker.
    """
    worker_id = os.environ.get("QUINN_WORKER_ID")
    if not worker_id:
        raise click.ClickException(
            "QUINN_WORKER_ID environment variable not set"
        )

    # TODO: Implement
    click.echo("qn wrkr send - not yet implemented")
