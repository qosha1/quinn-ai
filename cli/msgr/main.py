"""
msgr CLI entry point.

Provides the `msgr` command for QuinnAI messaging operations.
"""

import sys
from pathlib import Path
from typing import Optional

import click

from cli.core.org_discovery import find_org_root
from cli.msgr.context import MsgrContext


@click.group()
@click.option(
    "--org-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Defaults to QUINN_ORG_PATH env var or discovery.",
)
@click.option(
    "--worker-id",
    envvar="QUINN_WORKER_ID",
    help="Worker ID. Defaults to QUINN_WORKER_ID env var.",
)
@click.pass_context
def msgr(ctx, org_path: Optional[Path], worker_id: Optional[str]):
    """msgr - QuinnAI messaging CLI.

    Simple tool for workers to communicate:

    \b
    msgr inbox              - Check notifications
    msgr send #general 'hi' - Send message to channel
    msgr channels           - List available channels
    """
    # Skip context setup if showing help or no subcommand
    if not ctx.invoked_subcommand or ctx.resilient_parsing or "--help" in sys.argv:
        return

    # Discover org path if not provided
    if org_path is None:
        org_path = find_org_root()
        if org_path is None:
            click.echo("Error: Could not find org root. Set QUINN_ORG_PATH or run from org directory.", err=True)
            sys.exit(1)

    # Require worker ID for actual commands
    if worker_id is None:
        click.echo("Error: QUINN_WORKER_ID not set. Are you running in a worker session?", err=True)
        sys.exit(1)

    # Create context
    ctx.obj = MsgrContext(org_path, worker_id)

    # Ensure cleanup on exit
    ctx.call_on_close(ctx.obj.close)


# Register commands explicitly
from cli.msgr.commands.inbox import inbox
from cli.msgr.commands.send import send
from cli.msgr.commands.channels import channels
from cli.msgr.commands.read import read

msgr.add_command(inbox)
msgr.add_command(send)
msgr.add_command(channels)
msgr.add_command(read)


if __name__ == "__main__":
    msgr()
