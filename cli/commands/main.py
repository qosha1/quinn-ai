"""
QuinnAI CLI entry point.

Provides the `qn` command with org and wrkr subcommand groups.
"""

from pathlib import Path
from typing import Optional

import click

from cli.commands.context import Context, pass_context


@click.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Defaults to QUINN_ORG_PATH env var.",
)
@click.pass_context
def qn(ctx, org_path: Optional[Path]):
    """QuinnAI organization management CLI.

    Three command groups for three actors:

    \b
    qn org   - Organization management (human operator)
    qn wrkr  - Worker operations (AI worker in session)
    qn board - Board oversight (human intervention when off-track)
    """
    ctx.ensure_object(Context)
    if org_path:
        ctx.obj.org_path = org_path
    elif ctx.obj.org_path is None:
        # Default to current directory
        ctx.obj.org_path = Path.cwd()


@qn.group()
def org():
    """Manage organization lifecycle.

    Commands for human operators to manage the org.
    """
    pass


@qn.group()
@click.option(
    "--worker-id",
    envvar="QUINN_WORKER_ID",
    help="Worker ID. Defaults to QUINN_WORKER_ID env var.",
)
@click.pass_context
def wrkr(ctx, worker_id: Optional[str]):
    """Worker operations.

    Commands for AI workers running in sessions.
    Requires --worker-id option or QUINN_WORKER_ID environment variable.
    """
    ctx.ensure_object(Context)
    if worker_id:
        ctx.obj.worker_id = worker_id


# Import and register subcommands
from cli.commands.org import init_cmd, start_cmd, stop_cmd, status_cmd, cleanup_cmd, logs_cmd, observe_cmd, okr_cmd, budget_cmd, chart_cmd

org.add_command(init_cmd, name="init")
org.add_command(start_cmd, name="start")
org.add_command(stop_cmd, name="stop")
org.add_command(status_cmd, name="status")
org.add_command(cleanup_cmd, name="cleanup")
org.add_command(logs_cmd, name="logs")
org.add_command(observe_cmd, name="observe")
org.add_command(okr_cmd, name="okr")
org.add_command(budget_cmd, name="budget")
org.add_command(chart_cmd, name="chart")

from cli.commands.wrkr import get_work_cmd, inbox_cmd, send_cmd, status_cmd as wrkr_status_cmd

wrkr.add_command(get_work_cmd, name="get-work")
wrkr.add_command(inbox_cmd, name="inbox")
wrkr.add_command(send_cmd, name="send")
wrkr.add_command(wrkr_status_cmd, name="status")


# Board commands - human oversight when org is off-track
@qn.group()
def board():
    """Board oversight commands.

    Commands for human intervention when the org is off-track.
    Per CLAUDE.md: "Board = Gutterguards. Humans intervene only when
    org is off-track. Not required for daily operation."
    """
    pass


from cli.commands.board import status_cmd as board_status_cmd, alerts_cmd, pause_cmd, resume_cmd, fire_cmd

board.add_command(board_status_cmd, name="status")
board.add_command(alerts_cmd, name="alerts")
board.add_command(pause_cmd, name="pause")
board.add_command(resume_cmd, name="resume")
board.add_command(fire_cmd, name="fire")


if __name__ == "__main__":
    qn()
