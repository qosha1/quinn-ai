"""
QuinnAI CLI entry point.

Provides the `qn` command with org and wrkr subcommand groups.
"""

from pathlib import Path
from typing import Optional

import click

from cli.commands.context import Context, pass_context
from cli.core.logging import configure_logging


@click.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Defaults to QUINN_ORG_PATH env var.",
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose output (INFO level logging).",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug output (DEBUG level logging).",
)
@click.pass_context
def qn(ctx, org_path: Optional[Path], verbose: bool, debug: bool):
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
    # Note: org_path may be None here - validated in subcommands that need it

    # Configure logging only if org_path is available
    if ctx.obj.org_path:
        configure_logging(
            org_path=ctx.obj.org_path,
            verbose=verbose,
            debug=debug,
        )


@qn.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Defaults to QUINN_ORG_PATH env var.",
)
@click.pass_context
def org(ctx, org_path: Optional[Path]):
    """Manage organization lifecycle.

    Commands for human operators to manage the org.
    """
    ctx.ensure_object(Context)
    if org_path:
        ctx.obj.org_path = org_path


@qn.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Defaults to QUINN_ORG_PATH env var.",
)
@click.option(
    "--worker-id",
    envvar="QUINN_WORKER_ID",
    help="Worker ID. Defaults to QUINN_WORKER_ID env var.",
)
@click.pass_context
def wrkr(ctx, org_path: Optional[Path], worker_id: Optional[str]):
    """Worker operations.

    Commands for AI workers running in sessions.
    Requires --worker-id option or QUINN_WORKER_ID environment variable.
    """
    ctx.ensure_object(Context)
    if org_path:
        ctx.obj.org_path = org_path
    if worker_id:
        ctx.obj.worker_id = worker_id


# Import and register subcommands
from cli.commands.org import init_cmd, start_cmd, stop_cmd, restart_cmd, status_cmd, cleanup_cmd, logs_cmd, observe_cmd, okr_cmd, budget_cmd, chart_cmd, hire_cmd, fire_cmd

org.add_command(init_cmd, name="init")
org.add_command(start_cmd, name="start")
org.add_command(stop_cmd, name="stop")
org.add_command(restart_cmd, name="restart")
org.add_command(status_cmd, name="status")
org.add_command(cleanup_cmd, name="cleanup")
org.add_command(logs_cmd, name="logs")
org.add_command(observe_cmd, name="observe")
org.add_command(okr_cmd, name="okr")
org.add_command(budget_cmd, name="budget")
org.add_command(chart_cmd, name="chart")
org.add_command(hire_cmd, name="hire")
org.add_command(fire_cmd, name="fire")

from cli.commands.wrkr import get_work_cmd, inbox_cmd, search_cmd, send_cmd, status_cmd as wrkr_status_cmd, delegate_cmd, report_cmd, cleanup_cmd as wrkr_cleanup_cmd, restart_cmd

wrkr.add_command(get_work_cmd, name="get-work")
wrkr.add_command(inbox_cmd, name="inbox")
wrkr.add_command(search_cmd, name="search")
wrkr.add_command(send_cmd, name="send")
wrkr.add_command(wrkr_status_cmd, name="status")
wrkr.add_command(delegate_cmd, name="delegate")
wrkr.add_command(report_cmd, name="report")
wrkr.add_command(wrkr_cleanup_cmd, name="cleanup")
wrkr.add_command(restart_cmd, name="restart")


# Board commands - human oversight when org is off-track
@qn.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Defaults to QUINN_ORG_PATH env var.",
)
@click.pass_context
def board(ctx, org_path: Optional[Path]):
    """Board oversight commands.

    Commands for human intervention when the org is off-track.
    Per CLAUDE.md: "Board = Gutterguards. Humans intervene only when
    org is off-track. Not required for daily operation."
    """
    ctx.ensure_object(Context)
    if org_path:
        ctx.obj.org_path = org_path


from cli.commands.board import ui_cmd, status_cmd as board_status_cmd, alerts_cmd, pause_cmd, resume_cmd, fire_cmd

board.add_command(ui_cmd, name="ui")
board.add_command(board_status_cmd, name="status")
board.add_command(alerts_cmd, name="alerts")
board.add_command(pause_cmd, name="pause")
board.add_command(resume_cmd, name="resume")
board.add_command(fire_cmd, name="fire")


# Config commands - configuration validation
from cli.commands.config import config as config_group

qn.add_command(config_group, name="config")


if __name__ == "__main__":
    qn()
