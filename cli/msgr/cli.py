"""msgr CLI group definition."""

import click


@click.group()
@click.option(
    "--org-path",
    type=click.Path(exists=True, file_okay=False, path_type=click.Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Defaults to QUINN_ORG_PATH env var or discovery.",
)
@click.option(
    "--worker-id",
    envvar="QUINN_WORKER_ID",
    help="Worker ID. Defaults to QUINN_WORKER_ID env var.",
)
@click.pass_context
def msgr(ctx, org_path, worker_id):
    """msgr - QuinnAI messaging CLI.

    Simple tool for workers to communicate:

    \b
    msgr inbox              - Check notifications
    msgr send #general 'hi' - Send message to channel
    msgr channels           - List available channels
    """
    # Context setup is handled in main.py
    pass
