"""
QuinnAI CLI entry point.

Provides the `qn` command with org and wrkr subcommand groups.
"""

import sys
import traceback
from pathlib import Path
from typing import Optional

import click

from cli.commands.context import Context, pass_context
from cli.core.logging import configure_enhanced_logging, get_logger
from cli.core.org_discovery import find_org_root


@click.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Falls back to $QUINN_ORG_PATH, then auto-detection from cwd.",
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

    Four command groups:

    \b
    qn org    - Organization management (human operator)
    qn wrkr   - Worker operations (AI worker in session)
    qn board  - Board oversight (human intervention when off-track)
    qn config - Top-level configuration (providers, environment validation)
    """
    # Set up global exception handler for logging
    def handle_exception(exc_type, exc_value, exc_traceback):
        """Log uncaught exceptions before exiting.

        Distinguishes three cases:
        - KeyboardInterrupt: pass to default handler (clean ^C exit)
        - Known business exception: print a clean one-line error, no
          stack trace, exit with status 1 (quinn-ai-qm1h)
        - Truly unexpected: log full traceback if log file exists, print
          a short FATAL ERROR + suggested next step

        The logger.critical(exc_info=...) call previously dumped a
        30-line traceback to stderr even for routine business errors,
        which buried the actionable message.
        """
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Lazy imports — keep top-of-module light + avoid import-cycle risk
        from cli.core.bd_wrapper import BeadPermissionError, OKRLinkRequiredError
        from cli.core.logging import get_log_file_path
        from shared.exceptions import (
            ActiveSessionExistsError,
            BudgetAllocationError,
            BudgetExhaustedError,
            CircularDelegationError,
            ConfigurationError,
            DelegationNotFoundError,
            InvalidOrgTransition,
            InvalidStateTransition,
            NoBudgetAllocationError,
            OrgNotFoundError,
            OrgStartError,
            StorageError,
            WorkerNotFound,
        )

        # Known business exceptions: print the message, no stack trace.
        known_business_excs = (
            ActiveSessionExistsError,
            BeadPermissionError,
            BudgetAllocationError,
            BudgetExhaustedError,
            CircularDelegationError,
            ConfigurationError,
            DelegationNotFoundError,
            InvalidOrgTransition,
            InvalidStateTransition,
            NoBudgetAllocationError,
            OKRLinkRequiredError,
            OrgNotFoundError,
            OrgStartError,
            StorageError,
            WorkerNotFound,
        )
        if issubclass(exc_type, known_business_excs):
            click.echo(f"Error: {exc_value}", err=True)
            if debug:
                click.echo("\nFull traceback:", err=True)
                traceback.print_exception(exc_type, exc_value, exc_traceback)
            sys.exit(1)

        # Truly unexpected: log to file if available, summarize to stderr.
        log_path = get_log_file_path()
        if log_path:
            logger = get_logger("cli.main")
            logger.critical(
                "Uncaught exception",
                exc_info=(exc_type, exc_value, exc_traceback)
            )

        click.echo(f"\nFATAL ERROR: {exc_type.__name__}: {exc_value}", err=True)
        if debug:
            click.echo("\nFull traceback:", err=True)
            traceback.print_exception(exc_type, exc_value, exc_traceback)

        if log_path:
            click.echo(f"\nFull error logged to: {log_path}", err=True)
        else:
            click.echo(
                "\nRe-run with --debug to see the full traceback.",
                err=True,
            )

    sys.excepthook = handle_exception

    ctx.ensure_object(Context)

    # Auto-detect org_path if not provided
    if not org_path:
        org_path = find_org_root()

    if org_path:
        ctx.obj.org_path = org_path

    # Configure logging - use enhanced JSON logging with per-component segregation
    if ctx.obj.org_path:
        configure_enhanced_logging(
            org_path=ctx.obj.org_path,
            component="cli",
            json_format=True,
            legacy_logging=True,  # Also write to aggregated quinn.log
            verbose=verbose,
            debug=debug,
        )
    else:
        # Fallback: console-only logging when no org_path
        # Import the basic configure_logging for console-only mode
        from cli.core.logging import configure_logging
        configure_logging(
            org_path=None,
            verbose=verbose,
            debug=debug,
            log_to_file=False,
        )


@qn.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Falls back to $QUINN_ORG_PATH, then auto-detection from cwd.",
)
@click.pass_context
def org(ctx, org_path: Optional[Path]):
    """Manage organization lifecycle.

    Commands for human operators to manage the org.
    """
    ctx.ensure_object(Context)

    # Auto-detect if not provided at group level
    if not org_path and not ctx.obj.org_path:
        org_path = find_org_root()

    if org_path:
        ctx.obj.org_path = org_path


@qn.group()
@click.option(
    "--org-path",
    type=click.Path(exists=False, path_type=Path),
    envvar="QUINN_ORG_PATH",
    help="Path to org folder. Falls back to $QUINN_ORG_PATH, then auto-detection from cwd.",
)
@click.option(
    "--worker-id",
    envvar="QUINN_WORKER_ID",
    help=(
        "Worker ID. Falls back to $QUINN_WORKER_ID, then auto-detection "
        "from cwd if it's inside <org>/storage/workers/<...>/<wrkr-id>/."
    ),
)
@click.pass_context
def wrkr(ctx, org_path: Optional[Path], worker_id: Optional[str]):
    """Worker operations.

    Commands for AI workers running in sessions.
    Resolution: --worker-id > $QUINN_WORKER_ID > cwd auto-detect.
    """
    ctx.ensure_object(Context)
    if org_path:
        ctx.obj.org_path = org_path
    if worker_id:
        ctx.obj.worker_id = worker_id
    elif ctx.obj.org_path:
        # cwd fallback: walk cwd to find <org>/storage/workers/<...>/<wrkr-id>.
        # Mirrors msgr's resolution order so a worker whose env got scrubbed
        # but is running in its own storage dir still works (quinn-ai-3gwh).
        from cli.core.org_discovery import find_worker_id_from_cwd
        inferred = find_worker_id_from_cwd(ctx.obj.org_path)
        if inferred:
            ctx.obj.worker_id = inferred


# Import and register subcommands
from cli.commands.org import (
    init_cmd,
    start_cmd,
    stop_cmd,
    restart_cmd,
    status_cmd,
    cleanup_cmd,
    logs_cmd,
    observe_cmd,
    okr_cmd,
    budget_cmd,
    chart_cmd,
    hire_cmd,
    hire_team_cmd,
    templates_cmd,
    fire_cmd,
    delegate_authority_cmd,
    revoke_authority_cmd,
    promote_cmd,
    demote_cmd,
    delegations_cmd,
    provider_cmd,
    watch,
    rules_cmd,
)

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
org.add_command(hire_team_cmd, name="hire-team")
org.add_command(templates_cmd, name="templates")
org.add_command(fire_cmd, name="fire")
org.add_command(delegate_authority_cmd, name="delegate-authority")
org.add_command(revoke_authority_cmd, name="revoke-authority")
org.add_command(promote_cmd, name="promote")
org.add_command(demote_cmd, name="demote")
org.add_command(delegations_cmd, name="delegations")
org.add_command(provider_cmd, name="provider")
org.add_command(watch, name="watch")
org.add_command(rules_cmd, name="rules")

from cli.commands.wrkr import get_work_cmd, search_cmd, status_cmd as wrkr_status_cmd, delegate_cmd, report_cmd, cleanup_cmd as wrkr_cleanup_cmd, restart_cmd

wrkr.add_command(get_work_cmd, name="get-work")
wrkr.add_command(search_cmd, name="search")
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
    help="Path to org folder. Falls back to $QUINN_ORG_PATH, then auto-detection from cwd.",
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


from cli.commands.board import ui_cmd, status_cmd as board_status_cmd, health_cmd, alerts_cmd, pause_cmd, resume_cmd, fire_cmd

board.add_command(ui_cmd, name="ui")
board.add_command(board_status_cmd, name="status")
board.add_command(health_cmd, name="health")
board.add_command(alerts_cmd, name="alerts")
board.add_command(pause_cmd, name="pause")
board.add_command(resume_cmd, name="resume")
board.add_command(fire_cmd, name="fire")


# Config commands - configuration validation
from cli.commands.config import config as config_group

qn.add_command(config_group, name="config")


# qn-bd — rules-evaluated beads wrapper for workers
from cli.commands.qn_bd import _evaluate_qn_bd_action
from cli.core.bd_wrapper import BeadPermissionError, run_bd
from cli.core.lifecycle import LifecycleError as _LifecycleError


@qn.command(
    name="qn-bd",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_context
def qn_bd_cmd(ctx: Context, args: tuple[str, ...]) -> None:
    """Run bd (beads) with rules-engine evaluation and org-scoped permissions."""
    import os as _os
    bd_args = list(args)
    worker_id = _os.environ.get("QUINN_WORKER_ID")

    rule_exit = _evaluate_qn_bd_action(
        bd_args=bd_args,
        org_path=ctx.org_path,
        worker_id=worker_id,
    )
    if rule_exit is not None:
        raise SystemExit(rule_exit)

    try:
        # Rules engine already evaluated access — skip the separate beads
        # permission table check which is redundant for the worker-facing surface.
        result = run_bd(
            args=bd_args,
            org_path=ctx.org_path,
            worker_id=worker_id,
            skip_permission_check=True,
        )
        raise SystemExit(result.returncode)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
    except BeadPermissionError as e:
        click.echo(f"Permission denied: {e}", err=True)
        raise SystemExit(1)
    except _LifecycleError as e:
        click.echo(f"Lifecycle error: {e}", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    qn()
