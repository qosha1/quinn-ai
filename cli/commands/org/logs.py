"""
qn org logs command.

View worker session scrollback history without attaching.
"""

import subprocess
import time
from typing import Optional

import click

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.worker import Worker
from cli.core.queries import resolve_worker
from cli.core.constants import TMUX_SESSION_PREFIX, LOG_TAIL_POLL_INTERVAL
from shared.exceptions import WorkerNotFound


def get_tmux_session_name(worker_id: str) -> str:
    """Get the tmux session name for a worker.

    Args:
        worker_id: Worker ID

    Returns:
        tmux session name (format: {TMUX_SESSION_PREFIX}{worker_id})
    """
    return f"{TMUX_SESSION_PREFIX}{worker_id}"


def session_exists(session_name: str) -> bool:
    """Check if a tmux session exists.

    Args:
        session_name: tmux session name

    Returns:
        True if session exists
    """
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def capture_tmux_scrollback(session_name: str, lines: Optional[int] = None) -> str:
    """Capture scrollback buffer from a tmux session.

    Args:
        session_name: tmux session name
        lines: Optional number of lines to capture from the end (None = all)

    Returns:
        Captured output text

    Raises:
        click.ClickException: If session doesn't exist or capture fails
    """
    if not session_exists(session_name):
        raise click.ClickException(
            f"No active session found for worker.\n"
            f"Session '{session_name}' does not exist."
        )

    # Capture scrollback
    # -p: print to stdout
    # -S -: start from beginning of history
    cmd = ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-"]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise click.ClickException(
            f"Failed to capture session output: {result.stderr}"
        )

    output = result.stdout

    # Limit to last N lines if specified
    if lines is not None and output:
        output_lines = output.splitlines()
        if len(output_lines) > lines:
            output_lines = output_lines[-lines:]
        output = "\n".join(output_lines)
        if output:
            output += "\n"

    return output


@click.command()
@click.argument("worker")
@click.option(
    "-n", "--lines",
    type=int,
    default=None,
    help="Limit to last N lines (default: all history).",
)
@click.option(
    "-f", "--follow",
    is_flag=True,
    help="Continuously stream new output (poll every 0.5s).",
)
@pass_context
def logs_cmd(ctx: Context, worker: str, lines: Optional[int], follow: bool):
    """View worker session logs.

    Retrieves the scrollback buffer from a worker's tmux session
    without attaching to it. Similar to 'docker logs'.

    WORKER can be the worker name or worker ID.

    Examples:

    \b
      qn org logs alice         # Show all logs for worker 'alice'
      qn org logs alice -n 100  # Show last 100 lines
      qn org logs alice -f      # Follow mode (stream new output)
      qn org logs wrkr-abc123   # Use worker ID
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        # Resolve selector (id, name, or role); 'ceo' resolves to the
        # unique CEO regardless of the human-readable name (quinn-ai-f1ct).
        worker_data = resolve_worker(db, worker)
        worker_id = worker_data.id if worker_data else worker

        # Use Worker class to validate and check session state
        try:
            w = Worker.get(db, worker_id)
        except (ValueError, KeyError, WorkerNotFound):
            # ValueError: invalid worker ID format
            # KeyError: worker not found in database
            # WorkerNotFound: worker ID doesn't exist
            raise click.ClickException(
                f"Worker '{worker}' not found.\n"
                "Use 'qn org status' to see available workers."
            )

        # Check if worker has active session
        if not w.is_session_active:
            raise click.ClickException(
                f"Worker '{w.name}' does not have an active session.\n"
                f"Current runtime status: {w.runtime_status or 'none'}\n"
                "Start the worker first with 'qn org start'."
            )

        # Get tmux session name
        session_name = get_tmux_session_name(w.id)

        if follow:
            # Follow mode: continuously stream new output
            last_line_count = 0
            try:
                while True:
                    output = capture_tmux_scrollback(session_name)
                    current_lines = output.splitlines()
                    current_line_count = len(current_lines)

                    # Print only new lines
                    if current_line_count > last_line_count:
                        new_lines = current_lines[last_line_count:]
                        for line in new_lines:
                            click.echo(line)
                        last_line_count = current_line_count

                    time.sleep(LOG_TAIL_POLL_INTERVAL)
            except KeyboardInterrupt:
                # Graceful exit on Ctrl+C
                pass
        else:
            # Normal mode: capture and display logs
            output = capture_tmux_scrollback(session_name, lines)

            if not output.strip():
                click.echo(f"No output captured for {w.name}.")
            else:
                click.echo(output, nl=False)

    finally:
        db.close()
