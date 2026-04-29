"""
msgr CLI entry point.

Provides the `msgr` command for QuinnAI messaging operations.
"""

import sys
from pathlib import Path
from typing import Optional

import click

from cli.core.org_discovery import find_org_root, find_worker_id_from_cwd
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

    # Resolve worker_id: explicit flag > QUINN_WORKER_ID env > infer from cwd.
    # The cwd fallback covers the case where env propagation through a child
    # process didn't carry QUINN_WORKER_ID but the worker is running from
    # inside its own storage dir (quinn-ai-3gwh). msgr's flag and envvar
    # handling already cover the first two via Click; this adds the cwd path.
    if worker_id is None:
        worker_id = find_worker_id_from_cwd(org_path)

    if worker_id is None:
        click.echo(
            "Error: worker identity unknown. msgr needs to know which worker is calling.\n"
            "Resolution order:\n"
            "  1. --worker-id <wrkr-id>  (explicit, always works)\n"
            "  2. QUINN_WORKER_ID env var (set by qn org start / qn org hire)\n"
            "  3. cwd inside <org>/storage/workers/<...>/<wrkr-id>/  (auto-detect)\n"
            "If you're an AI worker whose env was scrubbed (e.g., env didn't\n"
            "propagate through a child shell), pass --worker-id explicitly.",
            err=True,
        )
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
