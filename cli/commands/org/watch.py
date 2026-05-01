"""qn org watch — persistent monitor that keeps workers continuously triggered.

Starts the ContinuationEngine and keeps it running until interrupted (Ctrl-C).
Use this alongside a running org to ensure workers receive ongoing work-cycle
prompts even when the Board UI is not open.

Usage:
    qn org watch
    qn org watch --interval=60  # prompt interval in seconds (default: 30)
"""

import signal
import time
from pathlib import Path
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.continuation_engine import ContinuationEngine
from cli.core.db import open_database, get_org_db_path


def _get_org_path(ctx: Context) -> Path:
    return ctx._require_org_path()


def start_watch_loop(
    org_path: Path,
    poll_seconds: int = 30,
    max_iterations: Optional[int] = None,
) -> None:
    """Start ContinuationEngine and loop until interrupted or max_iterations reached.

    Args:
        org_path: Path to the org directory
        poll_seconds: Seconds between engine poll cycles
        max_iterations: Stop after this many iterations (None = run forever, for testing)
    """
    db = open_database(get_org_db_path(org_path))
    engine = ContinuationEngine(db=db, org_path=org_path)

    stopped = False

    def _handle_signal(sig, frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        engine.start()
        iterations = 0
        while not stopped:
            if max_iterations is not None and iterations >= max_iterations:
                break
            time.sleep(poll_seconds)
            iterations += 1
    finally:
        if engine.is_running():
            engine.stop()
        db.close()


@click.command("watch")
@click.option(
    "--interval",
    default=30,
    show_default=True,
    help="Seconds between engine poll cycles.",
)
@pass_context
def watch(ctx: Context, interval: int) -> None:
    """Watch a running org and continuously trigger workers.

    Starts the ContinuationEngine which sends workers periodic work-cycle
    prompts (check inbox, pick up ready work). Runs until Ctrl-C.

    Use this when running an org from the CLI without the Board UI.
    """
    org_path = _get_org_path(ctx)
    click.echo(f"Watching org at {org_path} (interval: {interval}s). Press Ctrl-C to stop.")
    try:
        start_watch_loop(org_path, poll_seconds=interval)
    except Exception as e:
        raise click.ClickException(str(e))
    click.echo("Watch stopped.")
