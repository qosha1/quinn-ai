"""
msgr CLI entry point.

Provides the `msgr` command for QuinnAI messaging operations.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from cli.core.org_discovery import find_org_root, find_worker_id_from_cwd
from cli.msgr.context import MsgrContext


_TMUX_SESSION_PATTERN = re.compile(r"^qn-(wrkr-[a-zA-Z0-9_-]+)$")


def _find_worker_id_from_tmux() -> Optional[str]:
    """Resolve the calling worker's id from the surrounding tmux session.

    Every QuinnAI worker session is created via tmux_spawner with name
    'qn-{worker_id}'. When claude's Bash tool runs msgr, the bash subprocess
    inherits $TMUX, and `tmux display-message -p '#S'` returns the session
    name regardless of cwd or other env vars. Robust against env scrubbing
    by intermediate shells (quinn-ai-3gwh).

    Returns None when not running inside a tmux session, or when the session
    name doesn't follow the qn-wrkr-XXX pattern.
    """
    if not os.environ.get("TMUX"):
        return None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True, text=True, timeout=2,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    match = _TMUX_SESSION_PATTERN.match(name)
    return match.group(1) if match else None


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

    # Resolve worker_id, in order:
    #   1. --worker-id flag (Click handles it explicitly)
    #   2. QUINN_WORKER_ID env (Click envvar=)
    #   3. cwd inside <org>/storage/workers/<...>/<wrkr-id>/
    #   4. tmux session name (qn-wrkr-XXXX)  ← real fix for quinn-ai-3gwh
    #
    # The tmux fallback is bullet-proof: every QuinnAI worker session is
    # named 'qn-wrkr-XXXX' by tmux_spawner, so when claude's Bash tool
    # spawns msgr — even with a scrubbed env and a cwd outside the worker
    # storage tree — `tmux display-message -p '#S'` still gives us the
    # worker id reliably as long as the bash subprocess inherits $TMUX.
    if worker_id is None:
        worker_id = find_worker_id_from_cwd(org_path)
    if worker_id is None:
        worker_id = _find_worker_id_from_tmux()

    if worker_id is None:
        click.echo(
            "Error: worker identity unknown. msgr needs to know which worker is calling.\n"
            "Resolution order:\n"
            "  1. --worker-id <wrkr-id>  (explicit, always works)\n"
            "  2. QUINN_WORKER_ID env var (set by qn org start / qn org hire)\n"
            "  3. cwd inside <org>/storage/workers/<...>/<wrkr-id>/  (auto-detect)\n"
            "  4. tmux session name 'qn-wrkr-XXXX' (auto-detect via $TMUX)\n"
            "If none of the above work, pass --worker-id explicitly.",
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
